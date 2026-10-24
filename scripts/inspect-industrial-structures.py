#!/usr/bin/env python3
"""Written by AI, gpt-6-astra, 2026-10-24. Rebuild the bounded AHN source comparison.

Requires a Nix Python environment with laspy, lazrs, requests, numpy, scipy,
scikit-image and Pillow. Outputs remain in ignored work/, never browser assets.
"""
import argparse
import json
import struct
from pathlib import Path
from urllib.request import urlopen

import laspy
import numpy as np
from laspy.copc import Bounds
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter
from skimage.measure import marching_cubes

PROJECT = Path(__file__).resolve().parents[1]


def acquire_sample(config, point_path, ground_path):
    if not point_path.exists():
        point_path.parent.mkdir(parents=True, exist_ok=True)
        with laspy.CopcReader.open(config['source'], http_num_threads=4) as reader:
            points = reader.query(
                bounds=Bounds(*[np.array(values) for values in config['boundsRD_NAP']]),
                resolution=config['queryResolutionMetres'],
            )
            header = reader.header.copy()
            header.vlrs = [record for record in header.vlrs if record.user_id != 'copc']
            laspy.LasData(header, points=points).write(point_path)
    if not ground_path.exists():
        ground_path.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(config['groundSource']) as response:
            ground_path.write_bytes(response.read())


def selected_points(config, point_path, ground_path):
    cloud = laspy.read(point_path)
    keep = ((np.asarray(cloud.classification) == config['retainedClass']) &
            (np.asarray(cloud.point_source_id) == config['pointSourceId']))
    points = np.stack([cloud.x, cloud.y, cloud.z], axis=1)[keep]
    ground_image = Image.open(ground_path)
    ground_raster = np.asarray(ground_image)
    left, top = ground_image.tag_v2[33922][3:5]
    cell_size = ground_image.tag_v2[33550][0]
    rows = np.floor((top - points[:, 1]) / cell_size).astype(int)
    columns = np.floor((points[:, 0] - left) / cell_size).astype(int)
    ground = ground_raster[rows.clip(0, ground_raster.shape[0] - 1),
                           columns.clip(0, ground_raster.shape[1] - 1)]
    minimum_height = np.where(ground != -9999,
                              ground + config['groundClearanceMetres'],
                              config['unknownGroundMinimumNAP'])
    return points[points[:, 2] > minimum_height]


def local_surface(points, config):
    cell_size = config['voxelMetres']
    occupied = np.unique(np.floor(points / cell_size).astype(np.int32), axis=0)
    padding = int(np.ceil(config['gaussianSigmaMetres'] *
                          config['gaussianTruncate'] / cell_size)) + 2
    lower = occupied.min(axis=0) - padding
    local = occupied - lower
    field = np.zeros(local.max(axis=0) + padding + 1, dtype=np.float32)
    field[tuple(local.T)] = 1
    field = gaussian_filter(field, sigma=config['gaussianSigmaMetres'] / cell_size,
                            truncate=config['gaussianTruncate'])
    vertices, faces, _, _ = marching_cubes(
        field, level=config['isoLevel'], spacing=[cell_size] * 3,
        allow_degenerate=False,
    )
    vertices += lower * cell_size + cell_size / 2
    return vertices, faces, len(occupied)


def write_glb(vertices, faces, output, config):
    origin = config['localOriginRD']
    positions = np.stack([vertices[:, 0] - origin[0], vertices[:, 2],
                          origin[1] - vertices[:, 1]], axis=1).astype('<f4')
    indices = faces[:, [0, 2, 1]].astype('<u4')
    position_bytes, index_bytes = positions.tobytes(), indices.tobytes()
    binary = position_bytes + index_bytes
    document = {
        'asset': {'version': '2.0', 'generator': '010 source comparison'},
        'scene': 0, 'scenes': [{'nodes': [0]}], 'nodes': [{'mesh': 0}],
        'meshes': [{'primitives': [{'attributes': {'POSITION': 0},
                                    'indices': 1, 'material': 0}]}],
        'materials': [{'pbrMetallicRoughness': {
            'baseColorFactor': [.43, .51, .53, 1], 'metallicFactor': 0,
            'roughnessFactor': 1}, 'doubleSided': True}],
        'buffers': [{'byteLength': len(binary)}],
        'bufferViews': [
            {'buffer': 0, 'byteOffset': 0, 'byteLength': len(position_bytes), 'target': 34962},
            {'buffer': 0, 'byteOffset': len(position_bytes),
             'byteLength': len(index_bytes), 'target': 34963}],
        'accessors': [
            {'bufferView': 0, 'componentType': 5126, 'count': len(positions),
             'type': 'VEC3', 'min': positions.min(axis=0).tolist(),
             'max': positions.max(axis=0).tolist()},
            {'bufferView': 1, 'componentType': 5125, 'count': indices.size, 'type': 'SCALAR'}],
        'extras': {
            'originRD': origin, 'axes': 'X east, Y up NAP, Z south',
            'sourcePointSourceId': config['pointSourceId'],
            'surveyTimeUTC': config['surveyTimeUTC'],
            'interpretation': 'Local occupied surface; no infill below returns. Comparison only.'},
    }
    encoded = json.dumps(document, separators=(',', ':')).encode()
    encoded += b' ' * (-len(encoded) % 4)
    output.write_bytes(
        struct.pack('<4sII', b'glTF', 2, 28 + len(encoded) + len(binary)) +
        struct.pack('<I4s', len(encoded), b'JSON') + encoded +
        struct.pack('<I4s', len(binary), b'BIN\0') + binary)


def render_preview(vertices, faces, output, config):
    points = vertices[faces] - np.array(config['localOriginRD'])
    normals = np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0])
    normals /= np.maximum(np.linalg.norm(normals, axis=1), 1e-9)[:, None]
    angle = np.radians(25)
    horizontal = (points[:, :, 0] + points[:, :, 1]) / np.sqrt(2)
    depth = (points[:, :, 0] - points[:, :, 1]) / np.sqrt(2)
    vertical = points[:, :, 2] * np.cos(angle) - depth * np.sin(angle)
    depth = depth * np.cos(angle) + points[:, :, 2] * np.sin(angle)
    width, height = 1800, 1200
    scale = min((width - 100) / np.ptp(horizontal), (height - 160) / np.ptp(vertical))
    screen = np.stack([
        (horizontal - (horizontal.min() + horizontal.max()) / 2) * scale + width / 2,
        -(vertical - (vertical.min() + vertical.max()) / 2) * scale + height / 2 + 30,
    ], axis=-1)
    light = np.array([-.3, -.5, 1.])
    light /= np.linalg.norm(light)
    shade = .65 + .35 * np.abs(normals @ light)
    colors = (np.array([112, 131, 135]) * shade[:, None]).astype(np.uint8)
    canvas = Image.new('RGB', (width, height), '#bacdcc')
    draw = ImageDraw.Draw(canvas)
    for index in np.argsort(depth.mean(axis=1)):
        draw.polygon([tuple(point) for point in screen[index]], fill=tuple(colors[index]))
    draw.rectangle((0, 0, width, 66), fill='#eee9da')
    draw.text((20, 20), 'AHN single-flight local surface comparison; no vertical infill', fill='#263b3d')
    canvas.save(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample', type=Path, default=PROJECT / 'source-data/industrial-structures/sample.json')
    parser.add_argument('--output', type=Path, default=PROJECT / 'work/source-quality/height/single-flight-rebuilt')
    parser.add_argument('--fetch-only', action='store_true')
    arguments = parser.parse_args()
    config = json.loads(arguments.sample.read_text())
    point_path, ground_path = PROJECT / config['rawPointCloudCache'], PROJECT / config['rawGroundCache']
    acquire_sample(config, point_path, ground_path)
    if arguments.fetch_only:
        return
    points = selected_points(config, point_path, ground_path)
    vertices, faces, occupied_count = local_surface(points, config)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    write_glb(vertices, faces, arguments.output.with_suffix('.glb'), config)
    render_preview(vertices, faces, arguments.output.with_suffix('.png'), config)
    report = {'sourcePointSourceId': config['pointSourceId'], 'points': len(points),
              'occupiedCells': occupied_count, 'vertices': len(vertices), 'triangles': len(faces)}
    arguments.output.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
