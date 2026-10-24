#!/usr/bin/env python3
"""Written by AI, gpt-6-astra, 2026-10-24. Build measured industrial forms as 3D Tiles.

Dependencies: Nix Python with laspy, lazrs, numpy, scipy, scikit-image, pyproj,
Shapely, Pillow. Acquisition/flight choices are explicit input records.
"""
import argparse
import gzip
import hashlib
import json
import struct
from pathlib import Path

import laspy
import numpy as np
from PIL import Image
from pyproj import Transformer
from scipy.ndimage import maximum_filter, minimum_filter, binary_fill_holes, label
from shapely import contains_xy
from shapely.geometry import shape, box
from shapely.ops import transform
from skimage.color import rgb2lab, rgb2hsv, hsv2rgb

PROJECT = Path(__file__).resolve().parents[1]
PALETTE = ['#c2c9b9', '#a4bbc0', '#709193', '#617c85', '#77816c', '#a49265',
           '#b67b59', '#ad6859', '#8a7770', '#6d7672', '#d5c8ae']
PALETTE_RGB = np.array([[int(color[i:i + 2], 16) for i in (1, 3, 5)] for color in PALETTE]) / 255
RD_TO_GEOGRAPHIC = Transformer.from_crs(28992, 4326, always_xy=True)
GEOGRAPHIC_TO_RD = Transformer.from_crs(4326, 28992, always_xy=True)
ORIGIN_LATITUDE, ORIGIN_LONGITUDE = 51.915, 4.49
LAT, LON = np.radians([ORIGIN_LATITUDE, ORIGIN_LONGITUDE])
EAST = np.array([-np.sin(LON), np.cos(LON), 0])
UP = np.array([np.cos(LAT) * np.cos(LON), np.cos(LAT) * np.sin(LON), np.sin(LAT)])
SOUTH = np.array([np.sin(LAT) * np.cos(LON), np.sin(LAT) * np.sin(LON), -np.cos(LAT)])


def earth_positions(longitude, latitude, height):
    latitude, longitude = np.radians(latitude), np.radians(longitude)
    radius = 6378137 / np.sqrt(1 - .00669437999014 * np.sin(latitude) ** 2)
    return np.stack([(radius + height) * np.cos(latitude) * np.cos(longitude),
                     (radius + height) * np.cos(latitude) * np.sin(longitude),
                     (radius * (1 - .00669437999014) + height) * np.sin(latitude)], axis=-1)


EARTH_ORIGIN = earth_positions(ORIGIN_LONGITUDE, ORIGIN_LATITUDE, 0)
ROOT_TRANSFORM = np.eye(4)
ROOT_TRANSFORM[:3, :3] = np.stack([EAST, -SOUTH, UP], axis=1)
ROOT_TRANSFORM[:3, 3] = EARTH_ORIGIN


def load_crane_rails():
    collection = json.loads(gzip.decompress((PROJECT / 'source-data/industrial-ground.geojson.gz').read_bytes()))
    return [(feature['properties']['lokaal_id'], transform(GEOGRAPHIC_TO_RD.transform, shape(feature['geometry'])))
            for feature in collection['features'] if feature['properties'].get('plus_functie') == '(haven)kraan']


def terminal_orientation(crane_rails, bounds):
    selection = box(bounds[0][0], bounds[0][1], bounds[1][0], bounds[1][1])
    angles, lengths, identities = [], [], []
    for identity, geometry in crane_rails:
        clipped = geometry.intersection(selection)
        if clipped.is_empty:
            continue
        identities.append(identity)
        lines = list(clipped.geoms) if clipped.geom_type == 'MultiLineString' else [clipped]
        for line in lines:
            if line.geom_type != 'LineString':
                continue
            delta = np.diff(np.asarray(line.coords), axis=0)
            angles.extend(np.arctan2(delta[:, 1], delta[:, 0]))
            lengths.extend(np.linalg.norm(delta, axis=1))
    angles, lengths = np.array(angles), np.array(lengths)
    orientation = np.arctan2(np.sum(np.sin(4 * angles) * lengths),
                             np.sum(np.cos(4 * angles) * lengths)) / 4
    return float(orientation), identities


def source_returns(config):
    cloud = laspy.read(PROJECT / config['rawPointCloudCache'])
    keep = ((np.asarray(cloud.classification) == 1) &
            (np.asarray(cloud.point_source_id) == config['pointSourceId']))
    if 'gpsDay' in config:
        keep &= np.floor(np.asarray(cloud.gps_time) / 86400).astype(int) == config['gpsDay']
    points = np.stack([cloud.x, cloud.y, cloud.z], axis=1)[keep]
    colors = np.stack([cloud.red, cloud.green, cloud.blue], axis=1)[keep] / 65280
    image = Image.open(PROJECT / config['rawGroundCache'])
    ground = np.asarray(image)
    left, top = image.tag_v2[33922][3:5]
    cell = image.tag_v2[33550][0]
    rows = np.floor((top - points[:, 1]) / cell).astype(int).clip(0, ground.shape[0] - 1)
    columns = np.floor((points[:, 0] - left) / cell).astype(int).clip(0, ground.shape[1] - 1)
    heights = ground[rows, columns]
    minimum = np.where(heights != -9999, heights + config['groundClearanceMetres'],
                       config['unknownGroundMinimumNAP'])
    keep = points[:, 2] > minimum
    if 'selectionMask' in config:
        selection = shape(json.loads((PROJECT / config['selectionMask']).read_text())['geometry'])
        keep &= contains_xy(selection, points[:, 0], points[:, 1])
    if 'exclusionCache' in config:
        exclusions = shape(json.loads((PROJECT / config['exclusionCache']).read_text())['geometryRD'])
        keep &= ~contains_xy(exclusions, points[:, 0], points[:, 1])
    return points[keep], colors[keep]


def exposed_rectangles(occupied):
    lower = occupied.min(axis=0)
    local = occupied - lower + 1
    occupancy = np.zeros(local.max(axis=0) + 2, dtype=bool)
    occupancy[tuple(local.T)] = True
    rectangles = []
    for axis in range(3):
        across = [index for index in range(3) if index != axis]
        for side in [-1, 1]:
            neighbors = local.copy()
            neighbors[:, axis] += side
            exposed = local[~occupancy[tuple(neighbors.T)]]
            for level in np.unique(exposed[:, axis]):
                plane = exposed[exposed[:, axis] == level][:, across]
                mask = np.zeros([occupancy.shape[index] for index in across], dtype=bool)
                mask[tuple(plane.T)] = True
                for row in range(mask.shape[0]):
                    while mask[row].any():
                        column = int(np.flatnonzero(mask[row])[0])
                        end = column + 1
                        while end < mask.shape[1] and mask[row, end]:
                            end += 1
                        last = row + 1
                        while last < mask.shape[0] and mask[last, column:end].all():
                            last += 1
                        mask[row:last, column:end] = False
                        corners = np.zeros((4, 3), dtype=np.int32)
                        corners[:, axis] = level + (side == 1)
                        corners[:, across] = [[row, column], [last, column], [last, end], [row, end]]
                        corners += lower - 1
                        normal = np.cross(corners[1] - corners[0], corners[2] - corners[0])
                        if normal[axis] * side < 0:
                            corners = corners[[0, 3, 2, 1]]
                        rectangles.append(corners)
    return np.array(rectangles)


def measured_forms(points, colors, orientation, cell_size, origin):
    origin = np.array(origin)
    rotation = np.array([[np.cos(orientation), -np.sin(orientation), 0],
                         [np.sin(orientation), np.cos(orientation), 0], [0, 0, 1]])
    local_points = (points - origin) @ rotation
    indices = np.floor(local_points / cell_size).astype(np.int32)
    lower = indices.min(axis=0) - 4
    local = indices - lower
    occupancy = np.zeros(local.max(axis=0) + 5, dtype=bool)
    occupancy[tuple(local.T)] = True
    closed = minimum_filter(maximum_filter(occupancy, size=3, mode='constant'), size=3, mode='constant')
    solid = binary_fill_holes(closed)
    components, component_count = label(solid)
    sizes = np.bincount(components.ravel())
    solid &= (components > 0) & (sizes[components] >= max(4, int(6 / cell_size ** 3)))
    rectangles = exposed_rectangles(np.argwhere(solid) + lower)
    source_components = components[tuple(local.T)]
    weight = np.bincount(source_components, minlength=component_count + 1)
    component_colors = np.stack([
        np.bincount(source_components, weights=colors[:, channel], minlength=component_count + 1) /
        np.maximum(weight, 1) for channel in range(3)], axis=1)
    hsv = rgb2hsv(component_colors)
    hsv[:, 1] *= .8
    hsv[:, 2] = np.maximum(hsv[:, 2], .73)
    component_colors = hsv2rgb(hsv)
    palette_ids = np.argmin(np.sum((rgb2lab(component_colors)[:, None, :] -
                                    rgb2lab(PALETTE_RGB)[None, :, :]) ** 2, axis=2), axis=1)
    normals = np.sign(np.cross(rectangles[:, 1] - rectangles[:, 0], rectangles[:, 2] - rectangles[:, 0]))
    interior = np.floor(rectangles.mean(axis=1) - normals * .01 - lower).astype(int)
    face_components = components[tuple(interior.T)]
    face_colors = PALETTE_RGB[palette_ids[face_components]]
    world = (rectangles * cell_size) @ rotation.T + origin
    return world, face_colors, {'sourceOccupiedCells': int(occupancy.sum()),
                               'solidCells': int(solid.sum()), 'components': int(np.unique(face_components).size),
                               'triangles': len(rectangles) * 2}


def encode_glb(rectangles, face_colors, path, config, cell_size):
    vertices = rectangles.reshape(-1, 3)
    longitude, latitude = RD_TO_GEOGRAPHIC.transform(vertices[:, 0], vertices[:, 1])
    earth = earth_positions(longitude, latitude, vertices[:, 2]) - EARTH_ORIGIN
    positions = earth @ np.stack([EAST, UP, SOUTH], axis=1)
    bounds = [positions.min(axis=0), positions.max(axis=0)]
    scale = float(np.max(bounds[1] - bounds[0]) / 65535)
    quantized = np.rint((positions - bounds[0]) / scale).astype('<u2')
    linear = np.where(face_colors <= .04045, face_colors / 12.92, ((face_colors + .055) / 1.055) ** 2.4)
    colors = np.concatenate([np.repeat(np.rint(linear * 255).astype(np.uint8), 4, axis=0),
                             np.full((len(positions), 1), 255, dtype=np.uint8)], axis=1)
    vertex_type = np.dtype({'names': ['position', 'color'],
                           'formats': [('<u2', 3), ('u1', 4)],
                           'offsets': [0, 8], 'itemsize': 12})
    records = np.zeros(len(positions), dtype=vertex_type)
    records['position'], records['color'] = quantized, colors
    records, inverse = np.unique(records, return_inverse=True)
    original_indices = (np.arange(len(rectangles))[:, None] * 4 + np.array([0, 1, 2, 0, 2, 3]))
    indices = inverse[original_indices].astype('<u2' if len(records) <= 65535 else '<u4')
    vertex_bytes, index_bytes = records.tobytes(), indices.tobytes()
    binary = vertex_bytes + index_bytes
    binary += b'\0' * (-len(binary) % 4)
    extras = {'sourceLayer': 'industrial-structures', 'surfaceKind': 'measured-industrial',
              'sourcePointSourceId': config['pointSourceId'], 'surveyTimeUTC': config['surveyTimeUTC'],
              'displayCellMetres': cell_size}
    document = {
        'asset': {'version': '2.0', 'generator': '010 measured industrial forms'},
        'extensionsUsed': ['KHR_mesh_quantization'], 'extensionsRequired': ['KHR_mesh_quantization'],
        'scene': 0, 'scenes': [{'nodes': [0]}], 'nodes': [{'mesh': 0, 'translation': bounds[0].tolist(),
            'scale': [scale] * 3, 'extras': extras}],
        'meshes': [{'name': 'measured-industrial', 'extras': extras, 'primitives': [{
            'attributes': {'POSITION': 0, 'COLOR_0': 1}, 'indices': 2, 'material': 0}]}],
        'materials': [{'name': 'industrial-source-palette', 'pbrMetallicRoughness': {
            'baseColorFactor': [1, 1, 1, 1], 'metallicFactor': 0, 'roughnessFactor': .94}, 'doubleSided': False}],
        'buffers': [{'byteLength': len(binary)}],
        'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': len(vertex_bytes), 'byteStride': 12, 'target': 34962},
                        {'buffer': 0, 'byteOffset': len(vertex_bytes), 'byteLength': len(index_bytes), 'target': 34963}],
        'accessors': [
            {'bufferView': 0, 'byteOffset': 0, 'componentType': 5123, 'count': len(records), 'type': 'VEC3',
             'min': records['position'].min(axis=0).tolist(), 'max': records['position'].max(axis=0).tolist()},
            {'bufferView': 0, 'byteOffset': 8, 'componentType': 5121, 'count': len(records), 'type': 'VEC4', 'normalized': True},
            {'bufferView': 1, 'componentType': 5123 if indices.dtype.itemsize == 2 else 5125,
             'count': indices.size, 'type': 'SCALAR'}],
    }
    encoded = json.dumps(document, separators=(',', ':')).encode()
    encoded += b' ' * (-len(encoded) % 4)
    output = (struct.pack('<4sII', b'glTF', 2, 28 + len(encoded) + len(binary)) +
              struct.pack('<I4s', len(encoded), b'JSON') + encoded +
              struct.pack('<I4s', len(binary), b'BIN\0') + binary)
    path.write_bytes(output)
    return bounds, len(output)


def bounding_box(bounds):
    centre = (bounds[0] + bounds[1]) / 2
    half = (bounds[1] - bounds[0]) / 2
    return [centre[0], -centre[2], centre[1], half[0], 0, 0, 0, half[2], 0, 0, 0, half[1]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample', type=Path, default=PROJECT / 'source-data/industrial-structures/sample.json')
    parser.add_argument('--output', type=Path, default=PROJECT / 'public/data/industrial-structures')
    arguments = parser.parse_args()
    configs = json.loads(arguments.sample.read_text())
    configs = configs if isinstance(configs, list) else [configs]
    rails = load_crane_rails()
    arguments.output.mkdir(parents=True, exist_ok=True)
    tiles, reports, all_bounds = [], [], []
    for sample_index, config in enumerate(configs):
        points, colors = source_returns(config)
        if len(points) < 10:
            print(json.dumps({'selection': sample_index, 'retainedPoints': len(points), 'status': 'no industrial geometry after exclusions'}), flush=True)
            continue
        orientation_bounds = config['boundsRD_NAP']
        origin = [points[:, 0].mean(), points[:, 1].mean(), 0]
        if 'selectionMask' in config:
            selection = shape(json.loads((PROJECT / config['selectionMask']).read_text())['geometry'])
            a, b, c, d = selection.bounds
            orientation_bounds = [[a, b, 0], [c, d, 0]]
            origin = [selection.centroid.x, selection.centroid.y, 0]
        orientation, rail_ids = terminal_orientation(rails, orientation_bounds)
        levels, level_bounds = [], []
        for cell_size in [1., 1.5]:
            rectangles, face_colors, report = measured_forms(points, colors, orientation, cell_size, origin)
            filename = f'{sample_index}-{config["pointSourceId"]}-{cell_size:g}m.glb'
            bounds, size = encode_glb(rectangles, face_colors, arguments.output / filename, config, cell_size)
            all_bounds.extend(bounds)
            level_bounds.extend(bounds)
            report.update({'uri': filename, 'cellMetres': cell_size, 'bytes': size})
            levels.append({'boundingVolume': {'box': bounding_box(bounds)}, 'geometricError': 0,
                           'content': {'uri': filename}})
            reports.append(report)
            print(json.dumps(report), flush=True)
        fine, coarse = levels
        coarse.update({'geometricError': 2, 'refine': 'REPLACE', 'children': [fine],
                       'boundingVolume': {'box': bounding_box([np.min(level_bounds, axis=0), np.max(level_bounds, axis=0)])}})
        tiles.append(coarse)
        config = dict(config)
        config.update({'displayOriginRD': origin, 'orientationDegrees': float(np.degrees(orientation)), 'orientationSourceRailIds': rail_ids,
                       'retainedPoints': len(points), 'retainedBoundsRD_NAP': [points.min(axis=0).tolist(), points.max(axis=0).tolist()]})
        configs[sample_index] = config
    bounds = [np.min(all_bounds, axis=0), np.max(all_bounds, axis=0)]
    tileset = {'asset': {'version': '1.1', 'gltfUpAxis': 'Y'}, 'geometricError': 1e6, 'root': {
        'transform': ROOT_TRANSFORM.T.reshape(-1).tolist(), 'boundingVolume': {'box': bounding_box(bounds)},
        'geometricError': 1e6, 'refine': 'REPLACE', 'children': tiles}}
    (arguments.output / 'tileset.json').write_text(json.dumps(tileset, separators=(',', ':')))
    manifest = {'source': configs, 'paletteSRGB': PALETTE, 'sourceInputSha256': hashlib.sha256(arguments.sample.read_bytes()).hexdigest(),
                'reconstruction': 'One flight per selection; terminal-axis occupied cells; 3x3x3 closing; fill enclosed cavities; exposed faces only.',
                'colour': 'One source RGB average per connected form, lifted shadows, reduced saturation, nearest muted palette.',
                'heightConvention': 'RD horizontal transformed to WGS84; NAP heights used as model heights, matching existing municipal rendering convention.',
                'coverage': 'Only retained selected-pass returns; no other flight inserted into missing areas.', 'tiles': reports}
    (arguments.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
