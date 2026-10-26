"""Written by AI on 2026-10-26 by model GPT-6 Astra.

Prepare one evidence-only street elevation. Semantic selection stays in a data
file; source triangles, UVs and the metric projection stay traceable. No model
calls or scene writes occur here.
"""
import os
os.environ['OPENBLAS_NUM_THREADS'] = '1'

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates
from shapely import union_all
from shapely.geometry import Polygon, mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'buildings'))
from build import accessor, unpack_glb

ROOT = Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
TILE = os.environ.get('ASSET_TILE', 'x90250_y436000')  # other tiles: set ASSET_TILE


def walls_from_tile(path):
    raw = path.read_bytes()
    document, binary = unpack_glb(raw)
    features = document['extras']['features']
    groups, images = defaultdict(list), {}
    for primitive_index, primitive in enumerate(document.get('meshes', [{}])[0].get('primitives', [])):
        attributes = primitive['attributes']
        local = accessor(document, binary, attributes['POSITION']).reshape(-1, 3, 3).astype(float)
        identifiers = accessor(document, binary, attributes['_FEATURE_ID_0']).reshape(-1, 3)[:, 0].astype(int)
        uvs = accessor(document, binary, attributes['TEXCOORD_0']).reshape(-1, 3, 2)
        material = document['materials'][primitive['material']]['pbrMetallicRoughness']
        texture = material.get('baseColorTexture')
        image_index = document['textures'][texture['index']]['source'] if texture else None
        if image_index is not None and image_index not in images:
            view = document['bufferViews'][document['images'][image_index]['bufferView']]
            start = view.get('byteOffset', 0)
            images[image_index] = np.asarray(Image.open(io.BytesIO(binary[start:start + view['byteLength']])).convert('RGB'))
        cross = np.cross(local[:, 1] - local[:, 0], local[:, 2] - local[:, 0])
        lengths = np.linalg.norm(cross, axis=1)
        normals = cross / np.maximum(lengths[:, None], 1e-20)
        for index in np.flatnonzero((np.abs(normals[:, 1]) < .2) & (lengths > .01)):
            feature_index = int(identifiers[index])
            if features[feature_index]['kind'] != 'building':
                continue
            normal = normals[index].copy()
            normal[1] = 0
            normal /= np.linalg.norm(normal)
            if normal[0] < 0 or (abs(normal[0]) < 1e-8 and normal[2] < 0):
                normal *= -1
            key = (feature_index, *np.rint(normal[[0, 2]] * 100).astype(int), round(float(local[index, 0] @ normal) * 4))
            rd = np.column_stack((90250 + local[index, :, 0], 436000 - local[index, :, 2], local[index, :, 1]))
            uv = uvs[index]
            edges = uv[1:] - uv[0]
            uv_valid = abs(float(np.linalg.det(edges))) > 2e-10
            groups[key].append({'rd': rd, 'uv': uv, 'normal_rd': np.array([normal[0], -normal[2], 0]),
                                'image_index': image_index if uv_valid else None,
                                'area_m2': float(lengths[index] / 2), 'primitive_index': primitive_index,
                                'triangle_index': int(index)})
    walls = []
    for key, triangles in groups.items():
        feature = features[key[0]]
        area = sum(triangle['area_m2'] for triangle in triangles)
        center = sum(triangle['rd'].mean(axis=0) * triangle['area_m2'] for triangle in triangles) / area
        normal = sum(triangle['normal_rd'] * triangle['area_m2'] for triangle in triangles)
        normal /= np.linalg.norm(normal)
        walls.append({'feature_index': key[0], 'bag_id': feature['bag_id'], 'plane_key': list(map(int, key[1:])),
                      'triangles': triangles, 'center': center, 'normal': normal, 'area_m2': area,
                      'source_url': feature['source_url']})
    return walls, images, hashlib.sha256(raw).hexdigest(), features


def select_row(walls, selection):
    wanted = set(selection['bag_ids'])
    direction = np.array(selection['facing_normal_rd'], dtype=float)
    direction /= np.linalg.norm(direction)
    cosine = np.cos(np.radians(selection['max_angle_deg']))
    candidates = [wall for wall in walls if wall['bag_id'] in wanted and float(wall['normal'] @ direction) >= cosine]
    # The water-facing plane is furthest towards the quay, rather than the
    # largest party wall. Selection supplies the evidenced facing direction.
    row = []
    for identifier in selection['bag_ids']:
        choices = [wall for wall in candidates if wall['bag_id'] == identifier and wall['area_m2'] >= 2]
        if not choices:
            raise ValueError(f'No matching facade plane for BAG {identifier}')
        row.append(max(choices, key=lambda wall: float(wall['center'] @ direction)))
    total_area = sum(wall['area_m2'] for wall in row)
    normal = sum(wall['normal'] * wall['area_m2'] for wall in row) / total_area
    normal /= np.linalg.norm(normal)
    tangent = np.cross([0., 0., 1.], normal)
    origin = sum(wall['center'] * wall['area_m2'] for wall in row) / total_area
    row.sort(key=lambda wall: float(wall['center'] @ tangent))
    last_end = None
    for wall in row:
        vertices = np.concatenate([triangle['rd'] for triangle in wall['triangles']])
        deviation = float(np.max(np.abs((vertices - origin) @ normal)))
        if deviation > selection['max_plane_deviation_m']:
            raise ValueError(f'Facade {wall["bag_id"]} deviates {deviation:.3f}m from elevation plane')
        along = (vertices - origin) @ tangent
        if last_end is not None and float(along.min()) - last_end > selection['max_gap_m']:
            raise ValueError('Selected facade row is not spatially contiguous')
        last_end = float(along.max())
        wall['plane_deviation_m'] = deviation
    return row, origin, normal, tangent


def rasterize_triangle(projected, uv, image, width, height):
    x0, y0 = np.maximum(0, np.floor(projected.min(axis=0)).astype(int))
    x1, y1 = np.minimum([width, height], np.ceil(projected.max(axis=0)).astype(int))
    if x0 >= x1 or y0 >= y1:
        return None
    yy, xx = np.mgrid[y0:y1, x0:x1]
    matrix = (projected[1:] - projected[0]).T
    if abs(np.linalg.det(matrix)) < 1e-8:
        return None
    barycentric = (np.stack((xx + .5, yy + .5), axis=-1) - projected[0]) @ np.linalg.inv(matrix).T
    inside = (barycentric.min(axis=-1) >= -1e-7) & (barycentric.sum(axis=-1) <= 1.0000001)
    pixels, photographed = None, np.zeros_like(inside)
    if image is not None:
        texture = uv[0] + barycentric @ (uv[1:] - uv[0])
        photographed = inside & (texture.min(axis=-1) >= 0) & (texture.max(axis=-1) <= 1)
        coords = [texture[:, :, 1] * (image.shape[0] - 1), texture[:, :, 0] * (image.shape[1] - 1)]
        pixels = np.stack([map_coordinates(image[:, :, channel].astype(float), coords, order=1, mode='nearest') for channel in range(3)], axis=-1)
        pixels = np.rint(pixels).astype(np.uint8)
    return (x0, y0, x1, y1), inside, photographed, pixels


def prepare(selection_path, output_root, row_data=None):
    selection = json.loads(selection_path.read_text())
    if selection['tile'] != TILE:
        raise ValueError('This first pass is restricted to x90250_y436000')
    source = ROOT / 'scene/v1/tiles' / TILE / 'buildings.glb'
    if row_data is None:
        walls, images, source_hash, features = walls_from_tile(source)
        row, origin, normal, tangent = select_row(walls, selection)
    else:
        row, origin, normal, tangent, images, source_hash, features = row_data
    vertices = np.concatenate([triangle['rd'] for wall in row for triangle in wall['triangles']])
    scale = 20.
    along = (vertices - origin) @ tangent
    left = np.floor(along.min() * scale) / scale
    right = np.ceil(along.max() * scale) / scale
    bottom = np.floor(vertices[:, 2].min() * scale) / scale
    top = np.ceil(vertices[:, 2].max() * scale) / scale
    width, height = int(round((right - left) * scale)), int(round((top - bottom) * scale))
    image_origin = origin + left * tangent
    image_origin[2] = top
    canvas = np.full((height, width, 3), 160, dtype=np.uint8)
    wall_ids = np.zeros((height, width), dtype=np.uint16)
    photo_mask = np.zeros((height, width), dtype=np.uint8)
    records = []
    for wall_index, wall in enumerate(row, 1):
        polygons, triangle_records = [], []
        geometry_pixels, photo_pixels = np.zeros((height, width), bool), np.zeros((height, width), bool)
        for triangle in wall['triangles']:
            rd = triangle['rd']
            projected = np.column_stack(((rd - image_origin) @ tangent * scale, (top - rd[:, 2]) * scale))
            polygons.append(Polygon(projected))
            image = images.get(triangle['image_index'])
            raster = rasterize_triangle(projected, triangle['uv'], image, width, height)
            if raster is not None:
                (x0, y0, x1, y1), inside, photographed, pixels = raster
                geometry_pixels[y0:y1, x0:x1] |= inside
                photo_pixels[y0:y1, x0:x1] |= photographed
                if pixels is not None:
                    canvas[y0:y1, x0:x1][photographed] = pixels[photographed]
            triangle_records.append({'primitive_index': triangle['primitive_index'], 'triangle_index': triangle['triangle_index'],
                                     'rd_nap_vertices': rd.tolist(), 'pixel_vertices': projected.tolist(),
                                     'source_uv': triangle['uv'].tolist(), 'source_image_index': triangle['image_index']})
        polygon = union_all(polygons)
        wall_ids[geometry_pixels] = wall_index
        photo_mask[photo_pixels] = 255
        x0, y0, x1, y1 = polygon.bounds
        records.append({'wall_id': wall.get('wall_id', f'{wall["bag_id"]}:quay-front'), 'bag_id': wall['bag_id'], 'feature_index': wall['feature_index'],
                        'mask_value': wall_index, 'rectangle_px': [x0, y0, x1, y1], 'polygon_px': mapping(polygon),
                        'wall_plane_rd_nap': {'point': wall['center'].tolist(), 'normal': wall['normal'].tolist()},
                        'max_elevation_plane_deviation_m': wall['plane_deviation_m'], 'geometry_area_m2': wall['area_m2'],
                        'geometry_pixels': int(geometry_pixels.sum()), 'photo_pixels': int(photo_pixels.sum()),
                        'interpreted': not bool(photo_pixels.any()), 'triangles': triangle_records,
                        'evidence': [f'{source}#features/{wall["feature_index"]}', wall['source_url']]})
    output = output_root / 'elevations' / selection['id']
    output.mkdir(parents=True, exist_ok=True)
    image_path = output / 'reference.png'
    if image_path.exists():
        raise FileExistsError(f'Preserve existing evidence; choose a new selection id: {image_path}')
    Image.fromarray(canvas).save(image_path)
    Image.fromarray(wall_ids).save(output / 'wall-ids.png')
    Image.fromarray(photo_mask).save(output / 'photo-mask.png')
    metadata = {'written_by': 'AI, GPT-6 Astra, 2026-10-26', 'stage': 'elevation-evidence-v1', 'date': datetime.now(timezone.utc).isoformat(),
                'id': selection['id'], 'tile': TILE, 'image': str(image_path), 'image_size_px': [width, height],
                'pixel_size_m': .05, 'crs': {'horizontal': 'EPSG:28992', 'vertical': 'NAP'},
                'elevation_plane_rd_nap': {'point': origin.tolist(), 'outward_normal': normal.tolist(), 'right_axis': tangent.tolist(), 'up_axis': [0, 0, 1]},
                'pixel_transform': {'pixel_corner_origin_rd_nap': image_origin.tolist(), 'u_axis_m_per_px': (tangent / scale).tolist(), 'v_axis_m_per_px': [0, 0, -.05], 'sample': 'pixel centres'},
                'absent_evidence_rgb': [160, 160, 160], 'outside_wall_geometry_rgb': [160, 160, 160],
                'wall_ids_mask': str(output / 'wall-ids.png'), 'photo_coverage_mask': str(output / 'photo-mask.png'),
                'source': {'path': str(source), 'sha256': source_hash, 'image_sha256': hashlib.sha256(image_path.read_bytes()).hexdigest()},
                'selection': selection, 'selection_sha256': hashlib.sha256(selection_path.read_bytes()).hexdigest(),
                'code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'notes': ['Five-centimetre output sampling does not increase the original photograph resolution.',
                          'Raw photographed shadows, trees and other occlusions remain in the evidence.',
                          'Slightly bent terrace walls are projected onto the common elevation plane; actual planes and vertices are retained.',
                          'An absent photo gets an unchanged grey slot covering its real mesh polygon.'], 'walls': records,
                'tile_feature_counts': {'buildings': sum(f['kind'] == 'building' for f in features), 'bridges': sum(f['kind'] == 'bridge' for f in features)}}
    sidecar = output / 'reference.json'
    sidecar.write_text(json.dumps(metadata, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'image': str(image_path), 'sidecar': str(sidecar), 'size_px': [width, height], 'walls': len(row)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'assets/v1')
    args = parser.parse_args()
    prepare(args.selection, args.output)
