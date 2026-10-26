"""Written by AI on 2026-10-26 by model GPT-6 Astra.

Prepare exterior elevations for the one authorised tile, without model calls.
Shared wall triangles hidden below an adjacent mesh roof retain original material.
"""
import os
os.environ['OPENBLAS_NUM_THREADS'] = '1'
import argparse
from collections import defaultdict
from pathlib import Path
import json
import multiprocessing
import itertools
from PIL import Image
import numpy as np
from shapely import STRtree, union_all
from shapely.geometry import Point, Polygon
from elevations import ROOT, TILE, accessor, unpack_glb, walls_from_tile, prepare


def roof_geometry(source):
    document, binary = unpack_glb(source.read_bytes())
    by_feature = defaultdict(list)
    for primitive in document['meshes'][0]['primitives']:
        attributes = primitive['attributes']
        points = accessor(document, binary, attributes['POSITION']).reshape(-1, 3, 3).astype(float)
        identifiers = accessor(document, binary, attributes['_FEATURE_ID_0']).reshape(-1, 3)[:, 0].astype(int)
        for triangle, feature in zip(points, identifiers):
            rd = np.column_stack((90250 + triangle[:, 0], 436000 - triangle[:, 2], triangle[:, 1]))
            polygon = Polygon(rd[:, :2])
            if polygon.area > .01:
                by_feature[int(feature)].append((polygon, rd))
    footprints = {feature: union_all([p for p, _ in triangles]) for feature, triangles in by_feature.items()}
    return by_feature, footprints


def roof_height_at(point, roof_triangles):
    maximum = -np.inf
    for polygon, vertices in roof_triangles:
        if not polygon.buffer(.08).covers(Point(point)):
            continue
        matrix = (vertices[1:, :2] - vertices[0, :2]).T
        if abs(np.linalg.det(matrix)) < 1e-8:
            continue
        barycentric = np.linalg.solve(matrix, point - vertices[0, :2])
        if min(barycentric) >= -.03 and sum(barycentric) <= 1.03:
            maximum = max(maximum, vertices[0, 2] + barycentric @ (vertices[1:, 2] - vertices[0, 2]))
    return maximum


def exposed_walls(walls, roof_triangles, footprints, accepted_triangles):
    identifiers = list(footprints)
    tree = STRtree([footprints[index].buffer(.08) for index in identifiers])
    kept, excluded = [], []
    weights = np.array([[1/3, 1/3, 1/3], [.8, .1, .1], [.1, .8, .1], [.1, .1, .8]])
    for wall_index, wall in enumerate(walls):
        visible = []
        for triangle in wall['triangles']:
            key = (triangle['primitive_index'], triangle['triangle_index'])
            if key in accepted_triangles:
                continue
            samples = weights @ triangle['rd']
            neighbour_ids = [identifiers[int(i)] for i in tree.query(Point(samples[0, :2])) if identifiers[int(i)] != wall['feature_index']]
            covering = []
            for neighbour in neighbour_ids:
                if all(footprints[neighbour].buffer(.08).covers(Point(sample[:2])) and roof_height_at(sample[:2], roof_triangles[neighbour]) >= sample[2] + .05 for sample in samples):
                    covering.append(neighbour)
            if covering:
                excluded.append({'primitive_index': key[0], 'triangle_index': key[1], 'feature_index': wall['feature_index'], 'bag_id': wall['bag_id'], 'area_m2': triangle['area_m2'], 'reason': 'shared_wall_below_adjacent_existing_mesh_roof', 'covering_feature_indices': covering})
            else:
                visible.append(triangle)
        if visible:
            wall = dict(wall, triangles=visible, wall_id=f"{wall['bag_id']}:plane-{wall_index:04d}")
            wall['area_m2'] = sum(t['area_m2'] for t in visible)
            wall['center'] = sum(t['rd'].mean(axis=0) * t['area_m2'] for t in visible) / wall['area_m2']
            wall['vertices'] = np.concatenate([t['rd'] for t in visible])
            footprint = footprints.get(wall['feature_index'])
            if footprint is not None:
                for distance in [.2, .5, 1, 2]:
                    positive = footprint.covers(Point((wall['center'] + distance * wall['normal'])[:2]))
                    negative = footprint.covers(Point((wall['center'] - distance * wall['normal'])[:2]))
                    if positive != negative:
                        if positive:
                            wall['normal'] = -wall['normal']
                        break
            kept.append(wall)
    return kept, excluded


def row_plane(row):
    area = sum(wall['area_m2'] for wall in row)
    normal = sum(wall['normal'] * wall['area_m2'] for wall in row) / area
    normal /= np.linalg.norm(normal)
    origin = sum(wall['center'] * wall['area_m2'] for wall in row) / area
    tangent = np.cross([0., 0., 1.], normal)
    return origin, normal, tangent


def grouped_rows(walls):
    remaining = set(range(len(walls)))
    rows = []
    cosine = np.cos(np.deg2rad(8))
    while remaining:
        seed = max(remaining, key=lambda index: walls[index]['area_m2'])
        remaining.remove(seed)
        members = [seed]
        changed = True
        while changed:
            changed = False
            row = [walls[index] for index in members]
            origin, normal, tangent = row_plane(row)
            along = np.concatenate([(wall['vertices'] - origin) @ tangent for wall in row])
            eligible = []
            for index in remaining:
                wall = walls[index]
                if wall['normal'] @ normal < cosine:
                    continue
                deviation = np.max(np.abs((wall['vertices'] - origin) @ normal))
                if deviation > 1:
                    continue
                span = (wall['vertices'] - origin) @ tangent
                gap = max(span.min() - along.max(), along.min() - span.max(), 0)
                if gap > 1.25:
                    continue
                proposed = row + [wall]
                candidate_origin, candidate_normal, _ = row_plane(proposed)
                if max(np.max(np.abs((member['vertices'] - candidate_origin) @ candidate_normal)) for member in proposed) > 1:
                    continue
                eligible.append((gap, deviation, index))
            if eligible:
                index = min(eligible)[2]
                remaining.remove(index)
                members.append(index)
                changed = True
        row = [walls[index] for index in members]
        origin, normal, tangent = row_plane(row)
        row.sort(key=lambda wall: wall['center'] @ tangent)
        for wall in row:
            wall['plane_deviation_m'] = float(np.max(np.abs((wall['vertices'] - origin) @ normal)))
        rows.append((row, origin, normal, tangent))
    return sorted(rows, key=lambda item: (-sum(w['area_m2'] for w in item[0]), item[1][0], item[1][1]))


SHARED_TILE_DATA = None


def prepare_job(job):
    path, output, row, origin, normal, tangent = job
    images, source_hash, features = SHARED_TILE_DATA
    prepare(path, output, (row, origin, normal, tangent, images, source_hash, features))


def packed_layout(entries, gap=64, margin=32):
    best = None
    for ordered in itertools.permutations(entries):
        for columns in range(1, len(ordered) + 1):
            rows = (len(ordered) + columns - 1) // columns
            widths = [max(ordered[index]['image_size_px'][0] for index in range(column, len(ordered), columns)) for column in range(columns)]
            heights = [max(entry['image_size_px'][1] for entry in ordered[row * columns:(row + 1) * columns]) for row in range(rows)]
            width = sum(widths) + gap * (columns - 1) + 2 * margin
            height = sum(heights) + gap * (rows - 1) + 2 * margin
            aspect = max(width / height, height / width)
            score = width * height * max(1, aspect / 2) ** 3 * max(1, max(width, height) / 4096) ** 2
            if best is None or score < best[0]:
                rectangles = []
                for index, entry in enumerate(ordered):
                    column, row = index % columns, index // columns
                    x = margin + sum(widths[:column]) + column * gap
                    y = margin + sum(heights[:row]) + row * gap
                    w, h = entry['image_size_px']
                    rectangles.append({'elevation_id': entry['id'], 'reference_image': entry['reference_image'], 'reference_sidecar': entry['reference_sidecar'], 'rectangle_px': [x, y, x + w, y + h], 'original_size_px': [w, h]})
                best = score, [width, height], rectangles
    return best[1:]


def plan_model_batches(output, target_share=.85):
    tile_directory = output / 'tiles' / TILE
    inventory_path = tile_directory / 'elevations-inventory.json'
    inventory = json.loads(inventory_path.read_text())
    entries = inventory['elevations']
    for entry in entries:
        if 'area_m2' not in entry:
            reference = json.loads(Path(entry['reference_sidecar']).read_text())
            entry['area_m2'] = sum(wall['geometry_area_m2'] for wall in reference['walls'])
    total_area = sum(entry['area_m2'] for entry in entries)
    accepted = [entry for entry in entries if entry.get('existing_accepted')]
    selected = list(accepted)
    selected_area = sum(entry['area_m2'] for entry in selected)
    for entry in sorted((entry for entry in entries if not entry.get('existing_accepted')), key=lambda entry: -entry['area_m2']):
        if selected_area >= target_share * total_area:
            break
        selected.append(entry)
        selected_area += entry['area_m2']
    selected_ids = {entry['id'] for entry in selected}
    protected = {'aelbrechtskolk-quay-first-v1', f'{TILE}-elevation-001'}
    # Fixed membership keeps crop rectangles and batch IDs stable on a resume.
    pending = [entry for entry in selected if entry['id'] not in protected]
    batches = []
    for index in range(0, len(pending), 4):
        members = pending[index:index + 4]
        size, rectangles = packed_layout(members)
        batch_id = f'{TILE}-batch-{index // 4 + 1:03d}'
        directory = output / 'batches' / batch_id
        directory.mkdir(parents=True, exist_ok=True)
        image_path = directory / 'reference.png'
        if not image_path.exists():
            canvas = Image.new('RGB', size, (240, 240, 240))
            for rectangle in rectangles:
                image = Image.open(rectangle['reference_image']).convert('RGB')
                canvas.paste(image, tuple(rectangle['rectangle_px'][:2]))
            canvas.save(image_path)
        metadata = {'written_by': 'AI, GPT-6 Astra, 2026-10-26', 'id': batch_id, 'tile': TILE, 'reference_image': str(image_path), 'image_size_px': size, 'pixel_size_m': .05, 'gap_px': 64, 'margin_px': 32, 'gap_rgb': [240, 240, 240], 'packing': 'Unscaled source references, clear light gray gaps contrasting with source gray RGB160; rectangles use pixel corner coordinates [left,top,right,bottom]. Resize model output to the full canvas size before cropping these rectangles.', 'elevations': rectangles}
        (directory / 'reference.json').write_text(json.dumps(metadata, indent=2) + '\n')
        batches.append(metadata)
    reuse = [entry for entry in entries if entry['id'] not in selected_ids]
    selection = {'written_by': 'AI, GPT-6 Astra, 2026-10-26', 'tile': TILE, 'target_share': target_share, 'total_exterior_area_m2': total_area, 'selected_area_m2': selected_area, 'selected_share': selected_area / total_area, 'selected_elevation_count': len(selected), 'selected_elevation_ids': [entry['id'] for entry in selected], 'protected_existing_generation_ids': sorted(protected), 'pending_model_elevation_count': len(pending), 'pending_batch_count': len(batches), 'reuse_elevation_count': len(reuse), 'reuse_elevation_ids': [entry['id'] for entry in reuse], 'reuse_policy': 'Prefer a generated source wall from the same BAG; otherwise nearest BAG with similar construction year and use. Record source wall ID and mark reused areas interpreted.'}
    (tile_directory / 'model-selection.json').write_text(json.dumps(selection, indent=2) + '\n')
    (tile_directory / 'model-generation-queue.json').write_text(json.dumps({'written_by': 'AI, GPT-6 Astra, 2026-10-26', 'tile': TILE, 'batches': batches}, indent=2) + '\n')
    print(json.dumps(selection))


def run(output, inventory_only=False, workers=12, diagnostic=False):
    global SHARED_TILE_DATA
    source = ROOT / 'scene/v1/tiles' / TILE / 'buildings.glb'
    walls, images, source_hash, features = walls_from_tile(source)
    accepted_directory = output / 'elevations/aelbrechtskolk-quay-first-v1'
    accepted = json.loads((accepted_directory / 'reference.json').read_text())
    accepted_triangles = {(t['primitive_index'], t['triangle_index']) for wall in accepted['walls'] for t in wall['triangles']}
    roofs, footprints = roof_geometry(source)
    exterior, excluded = exposed_walls(walls, roofs, footprints, accepted_triangles)
    rows = grouped_rows(exterior)
    SHARED_TILE_DATA = images, source_hash, features
    selections = output / 'tiles' / TILE / 'selections'
    selections.mkdir(parents=True, exist_ok=True)
    entries = [{'id': accepted['id'], 'directory': str(accepted_directory), 'wall_count': len(accepted['walls']), 'triangle_count': len(accepted_triangles), 'existing_accepted': True}]
    jobs = []
    for index, (row, origin, normal, tangent) in enumerate(rows, 1):
        elevation_id = f'{TILE}-elevation-{index:03d}'
        directory = output / 'elevations' / elevation_id
        selection = {'written_by': 'AI, GPT-6 Astra, 2026-10-26', 'id': elevation_id, 'tile': TILE, 'bag_ids': sorted(set(w['bag_id'] for w in row)), 'wall_ids': [w['wall_id'] for w in row], 'max_angle_deg': 8, 'max_plane_deviation_m': 1, 'max_gap_m': 1.25, 'selection_basis': 'Adjacent existing mesh wall fragments, canonical normals within 8 degrees and every vertex within 1m of the shared plane; shared triangles below an adjacent mesh roof excluded.'}
        path = selections / f'{elevation_id}.json'
        path.write_text(json.dumps(selection, indent=2) + '\n')
        entry = {'id': elevation_id, 'directory': str(directory), 'bag_ids': selection['bag_ids'], 'wall_count': len(row), 'triangle_count': sum(len(w['triangles']) for w in row), 'area_m2': sum(w['area_m2'] for w in row), 'photographed_area_m2': sum(t['area_m2'] for w in row for t in w['triangles'] if t['image_index'] is not None)}
        entries.append(entry)
        if not inventory_only and (not diagnostic or index <= 12 or index > len(rows) - 12) and not (directory / 'reference.json').exists():
            jobs.append((path, output, row, origin, normal, tangent))
    inventory = {'written_by': 'AI, GPT-6 Astra, 2026-10-26', 'tile': TILE, 'source': str(source), 'source_sha256': source_hash, 'source_wall_triangles': sum(len(w['triangles']) for w in walls), 'elevation_count': len(entries), 'photo_coverage_basis': 'Valid original source UV mapping only. This includes trees, foreground roofs, other buildings and projection artifacts. Semantic evidence masks must exclude those regions before verification; mapped photo coverage is not verified facade coverage.', 'elevations': entries, 'excluded_original_material_triangles': excluded, 'exclusion_method': 'A triangle is excluded only when four interior samples lie inside one adjacent existing mesh footprint and below its triangulated roof surface by at least 5cm; 8cm XY footprint tolerance. No photo content or model output is used for this decision.'}
    destination = output / 'tiles' / TILE / 'elevations-inventory.json'
    destination.write_text(json.dumps(inventory, indent=2) + '\n')
    print(json.dumps({'inventory': str(destination), 'elevations': len(entries), 'excluded_triangles': len(excluded), 'exterior_fragments': len(exterior)}))
    if jobs:
        with multiprocessing.get_context('fork').Pool(workers) as pool:
            pool.map(prepare_job, jobs, chunksize=1)
    if not inventory_only:
        queue = []
        for entry in entries:
            directory = Path(entry['directory'])
            sidecar = directory / 'reference.json'
            entry['reference_prepared'] = sidecar.exists()
            if not sidecar.exists():
                continue
            reference = json.loads(sidecar.read_text())
            entry['reference_image'] = str(directory / 'reference.png')
            entry['reference_sidecar'] = str(sidecar)
            entry['image_size_px'] = reference['image_size_px']
            entry['geometry_pixels'] = sum(wall['geometry_pixels'] for wall in reference['walls'])
            entry['photo_pixels'] = sum(wall['photo_pixels'] for wall in reference['walls'])
            if not entry.get('existing_accepted'):
                queue.append({key: entry[key] for key in ['id', 'directory', 'reference_image', 'reference_sidecar', 'image_size_px', 'wall_count', 'area_m2', 'photographed_area_m2']})
        inventory['prepared_elevations'] = sum(entry.get('reference_prepared', False) for entry in entries)
        destination.write_text(json.dumps(inventory, indent=2) + '\n')
        (destination.parent / 'generation-queue.json').write_text(json.dumps({'written_by': 'AI, GPT-6 Astra, 2026-10-26', 'tile': TILE, 'order': 'descending exterior wall area; accepted first elevation excluded', 'elevations': queue}, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'assets/v1')
    parser.add_argument('--inventory-only', action='store_true')
    parser.add_argument('--workers', type=int, default=12)
    parser.add_argument('--diagnostic', action='store_true')
    parser.add_argument('--plan-model-batches', action='store_true')
    arguments = parser.parse_args()
    if arguments.plan_model_batches:
        plan_model_batches(arguments.output)
    else:
        run(arguments.output, arguments.inventory_only, arguments.workers, arguments.diagnostic)
