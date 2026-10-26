#!/usr/bin/env -S .devenv/profile/bin/python
"""Written by AI on 2026-10-26 by model GPT-6 Astra.

Merge LOD2 fragments into measured wall planes and classify BGT-facing sides.
All source triangles survive. Coplanarity is bounded, not inferred by style.
"""
import os
os.environ['OPENBLAS_NUM_THREADS'] = '1'
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
import sys

import numpy as np
from PIL import Image
from shapely import STRtree, make_valid, union_all
from shapely.geometry import LineString, Point, Polygon, box, shape

from elevations import ROOT, TILE, walls_from_tile, rasterize_triangle
from prepare_tile import roof_geometry

OUTPUT = ROOT / 'facts/v1/work' / TILE
ANGLE_DEGREES = 2
PLANE_DISTANCE_M = .1
CONNECTIVITY_GAP_M = .3


def merge_wall_fragments(fragments):
    by_building = defaultdict(list)
    for fragment in fragments:
        by_building[fragment['feature_index']].append(fragment)
    merged = []
    cosine = np.cos(np.radians(ANGLE_DEGREES))
    for feature_index, building_fragments in sorted(by_building.items()):
        remaining = sorted(building_fragments, key=lambda wall: -wall['area_m2'])
        sides = []
        while remaining:
            seed = remaining.pop(0)
            normal, point = seed['normal'], seed['center']
            tangent = np.cross([0., 0., 1.], normal)
            members = [seed]
            changed = True
            while changed:
                changed = False
                vertices = np.concatenate([t['rd'] for member in members for t in member['triangles']])
                footprint = union_all([Polygon(np.column_stack(((t['rd']-point) @ tangent, t['rd'][:, 2]))) for member in members for t in member['triangles']])
                for candidate in list(remaining):
                    if abs(normal @ candidate['normal']) < cosine:
                        continue
                    candidate_vertices = np.concatenate([t['rd'] for t in candidate['triangles']])
                    if np.max(np.abs((candidate_vertices-point) @ normal)) > PLANE_DISTANCE_M:
                        continue
                    candidate_polygon = union_all([Polygon(np.column_stack(((t['rd']-point) @ tangent, t['rd'][:, 2]))) for t in candidate['triangles']])
                    if footprint.distance(candidate_polygon) > CONNECTIVITY_GAP_M:
                        continue
                    members.append(candidate)
                    remaining = [item for item in remaining if item is not candidate]
                    changed = True
            triangles = [triangle for member in members for triangle in member['triangles']]
            area = sum(t['area_m2'] for t in triangles)
            center = sum(t['rd'].mean(axis=0) * t['area_m2'] for t in triangles) / area
            vertices = np.concatenate([t['rd'] for t in triangles])
            sides.append(dict(seed, triangles=triangles, area_m2=area, center=center,
                              fragment_count=len(members), plane_deviation_m=float(np.max(np.abs((vertices-point) @ normal)))))
        sides.sort(key=lambda wall: (round(float(np.arctan2(wall['normal'][1], wall['normal'][0])), 3), *wall['center'][:2]))
        for side_index, wall in enumerate(sides):
            wall['wall_id'] = f"{wall['bag_id']}:side-{side_index:03d}"
            merged.append(wall)
    return merged


def bgt_surfaces(tile=TILE):
    records, seen, hashes = [], set(), {}
    tile_x, tile_y = map(int, tile[1:].split('_y'))
    boundary = box(tile_x-20, tile_y-20, tile_x+270, tile_y+270)
    for collection in ['wegdeel', 'waterdeel']:
        for path in sorted((ROOT/'sources/bgt/2026-10-25'/collection).glob('*.json')):
            bounds = re.match(r'bbox_(\d+)_(\d+)_(\d+)_(\d+)', path.name)
            if bounds and not box(*map(int, bounds.groups())).intersects(boundary):
                continue
            data = json.loads(path.read_text())
            local = []
            for feature in data.get('features', []):
                properties = feature['properties']
                if properties.get('eind_registratie') or properties.get('termination_date') or (properties.get('relatieve_hoogteligging') or 0) < 0 or properties.get('status') not in (None, 'bestaand'):
                    continue
                function = properties.get('functie', '')
                if collection == 'wegdeel' and not (function.startswith('rijbaan') or function in ['voetpad', 'voetpad op trap', 'fietspad', 'OV-baan', 'ov-baan']):
                    continue
                if not feature.get('geometry'):
                    continue
                geometry = make_valid(shape(feature['geometry']))
                if not geometry.intersects(boundary):
                    continue
                identifier = str(feature.get('id') or properties.get('identificatie'))
                key = collection, identifier
                if key in seen:
                    continue
                seen.add(key)
                local.append({'collection': collection, 'id': identifier, 'function': function, 'geometry': geometry, 'source': str(path)})
            if local:
                hashes[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
                records.extend(local)
    return records, hashes


def horizontal_wall_segments(building_walls, excluded_wall, height):
    """Intersect the building's other vertical walls with the viewing height."""
    segments = []
    for other in building_walls:
        if other is excluded_wall or other.get('wall_id') == excluded_wall.get('wall_id'):
            continue
        for triangle in other['triangles']:
            vertices = triangle['rd']
            if height < vertices[:, 2].min() or height > vertices[:, 2].max():
                continue
            points = []
            for a, b in zip(vertices, np.roll(vertices, -1, axis=0)):
                if a[2] == b[2]:
                    if a[2] == height:
                        points.extend([a[:2], b[:2]])
                elif min(a[2], b[2]) <= height <= max(a[2], b[2]):
                    points.append((a + (b-a) * ((height-a[2])/(b[2]-a[2])))[:2])
            if len(points) < 2:
                continue
            points = np.asarray(points)
            distances = np.linalg.norm(points[:, None] - points[None, :], axis=2)
            first, last = np.unravel_index(distances.argmax(), distances.shape)
            if distances[first, last] > .01:
                segments.append(LineString([points[first], points[last]]))
    return union_all(segments)


def classify_wall(wall, footprints, surfaces, surface_tree, footprint_ids, footprint_tree, building_walls):
    normal = wall['normal'].copy()
    footprint = footprints[wall['feature_index']]
    normal_status = 'ambiguous_footprint_offset'
    for distance in [.15, .3, .6, 1., 2.]:
        positive = footprint.contains(Point((wall['center'] + distance*normal)[:2]))
        negative = footprint.contains(Point((wall['center'] - distance*normal)[:2]))
        if positive != negative:
            if positive:
                normal *= -1
            normal_status = 'outward_from_building_footprint'
            break
    if normal_status.startswith('ambiguous'):
        source_normal = sum((np.cross(t['rd'][1]-t['rd'][0], t['rd'][2]-t['rd'][0]) for t in wall['triangles']), np.zeros(3))
        if normal @ source_normal < 0:
            normal *= -1
        normal_status = 'source_triangle_winding_footprint_offset_ambiguous'
    wall['normal'] = normal
    tangent = np.cross([0., 0., 1.], normal)
    vertices = np.concatenate([t['rd'] for t in wall['triangles']])
    along = (vertices-wall['center']) @ tangent
    a = wall['center'][:2] + along.min()*tangent[:2]
    b = wall['center'][:2] + along.max()*tangent[:2]
    corridor = Polygon([a+.05*normal[:2], b+.05*normal[:2], b+15*normal[:2], a+15*normal[:2]])
    self_obstruction = horizontal_wall_segments(building_walls, wall, wall['center'][2])
    reachable = {}
    for position in np.linspace(along.min()+.01, along.max()-.01, 9):
        start = wall['center'][:2]+position*tangent[:2]+.15*normal[:2]
        ray = LineString([start, start+14.85*normal[:2]])
        self_intersection = self_obstruction.intersection(ray)
        obstruction = Point(start).distance(self_intersection) if not self_intersection.is_empty else 15.
        for index in footprint_tree.query(ray):
            identifier = footprint_ids[int(index)]
            if identifier == wall['feature_index']:
                continue
            intersection = footprints[identifier].intersection(ray)
            if not intersection.is_empty:
                obstruction = min(obstruction, Point(start).distance(intersection))
        for index in surface_tree.query(ray):
            intersection = surfaces[int(index)]['geometry'].intersection(ray)
            if intersection.is_empty:
                continue
            distance = Point(start).distance(intersection)
            if distance <= obstruction+.08:
                reachable[int(index)] = min(reachable.get(int(index), 15.), distance+.15)
    matches = []
    for index in surface_tree.query(corridor):
        surface = surfaces[int(index)]
        if int(index) not in reachable:
            continue
        intersection = surface['geometry'].intersection(corridor)
        if intersection.is_empty or intersection.area < .02:
            continue
        nearest = intersection.representative_point()
        distance = reachable[int(index)]
        matches.append({key: surface[key] for key in ['collection', 'id', 'function', 'source']} | {'normal_distance_m': distance, 'intersection_area_m2': intersection.area})
    wall['street_facing'] = bool(matches)
    wall['street_classification'] = {'method': 'nine_outward_rays_other_building_footprints_and_same_building_wall_slices', 'maximum_distance_m': 15, 'normal_status': normal_status, 'matches': sorted(matches, key=lambda match: match['normal_distance_m'])}


def reference(wall, images, source_hash, output=OUTPUT):
    normal = wall['normal']
    tangent = np.cross([0., 0., 1.], normal)
    vertices = np.concatenate([t['rd'] for t in wall['triangles']])
    origin = wall['center'].copy()
    left = np.floor(((vertices-origin) @ tangent).min()*20)/20
    right = np.ceil(((vertices-origin) @ tangent).max()*20)/20
    top = np.ceil(vertices[:, 2].max()*20)/20
    bottom = np.floor(vertices[:, 2].min()*20)/20
    width, height = max(1, round((right-left)*20)), max(1, round((top-bottom)*20))
    image_origin = origin + left*tangent
    image_origin[2] = top
    rgb = np.full((height, width, 3), 160, np.uint8)
    geometry, photo = np.zeros((height, width), np.uint8), np.zeros((height, width), np.uint8)
    triangles = []
    for triangle in wall['triangles']:
        projected = np.column_stack(((triangle['rd']-image_origin) @ tangent*20, (top-triangle['rd'][:, 2])*20))
        raster = rasterize_triangle(projected, triangle['uv'], images.get(triangle['image_index']), width, height)
        if raster is not None:
            (x0,y0,x1,y1), inside, photographed, pixels = raster
            geometry[y0:y1,x0:x1][inside] = 255
            photo[y0:y1,x0:x1][photographed] = 255
            if pixels is not None:
                rgb[y0:y1,x0:x1][photographed] = pixels[photographed]
        triangles.append({'primitive_index': triangle['primitive_index'], 'triangle_index': triangle['triangle_index'], 'rd_nap_vertices': triangle['rd'].tolist(), 'pixel_vertices': projected.tolist(), 'source_uv': triangle['uv'].tolist(), 'source_image_index': triangle['image_index'], 'area_m2': triangle['area_m2']})
    directory = output/'walls-v2'/wall['wall_id'].replace(':', '_')
    directory.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb).save(directory/'reference.png')
    Image.fromarray(geometry).save(directory/'geometry-mask.png')
    Image.fromarray(photo).save(directory/'photo-mask.png')
    record = {key: wall[key] for key in ['wall_id','bag_id','feature_index','area_m2','fragment_count','plane_deviation_m','street_facing','street_classification','source_url']}
    record.update({'reference': str(directory/'reference.png'), 'geometry_mask': str(directory/'geometry-mask.png'), 'photo_mask': str(directory/'photo-mask.png'), 'reference_sha256': hashlib.sha256((directory/'reference.png').read_bytes()).hexdigest(), 'image_size_px': [width,height], 'photo_pixels': int((photo>0).sum()), 'geometry_pixels': int((geometry>0).sum()), 'photo_fraction': float((photo>0).sum()/max((geometry>0).sum(),1)), 'photo_coverage_is_visibility': False, 'pixel_size_m': .05, 'wall_plane_rd_nap': {'point': wall['center'].tolist(), 'normal': normal.tolist()}, 'pixel_transform': {'pixel_corner_origin_rd_nap': image_origin.tolist(),'u_axis_m_per_px': (tangent*.05).tolist(),'v_axis_m_per_px': [0,0,-.05]}, 'triangles': triangles, 'source_sha256': source_hash})
    (directory/'reference.json').write_text(json.dumps(record, indent=2)+'\n')
    return record


def prepare_walls(tile=TILE, workers=4):
    output = ROOT / 'facts/v1/work' / tile
    destination = output/'walls.json'
    source = ROOT/'scene/v1/tiles'/tile/'buildings.glb'
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if destination.exists():
        previous = json.loads(destination.read_text())
        if previous.get('source',{}).get('sha256') == source_hash:
            return destination
    fragments, images, source_hash, features = walls_from_tile(source)
    walls = merge_wall_fragments(fragments)
    _, footprints = roof_geometry(source)
    surfaces, surface_hashes = bgt_surfaces(tile)
    tree = STRtree([surface['geometry'] for surface in surfaces])
    footprint_ids = list(footprints)
    footprint_tree = STRtree([footprints[index] for index in footprint_ids])
    building_walls = defaultdict(list)
    for wall in walls:
        building_walls[wall['feature_index']].append(wall)
    for wall in walls:
        classify_wall(wall, footprints, surfaces, tree, footprint_ids, footprint_tree, building_walls[wall['feature_index']])
    output.mkdir(parents=True, exist_ok=True)
    counts = {'buildings': sum(f['kind']=='building' for f in features),'source_wall_fragments': len(fragments), 'merged_walls': len(walls),'street_facing_walls': sum(wall['street_facing'] for wall in walls),'not_street_facing_walls': sum(not wall['street_facing'] for wall in walls), 'street_facing_with_mapped_photo': sum(wall['street_facing'] and any(t['image_index'] is not None for t in wall['triangles']) for wall in walls)}
    print(json.dumps(counts), flush=True)
    (output/'walls-counts.json').write_text(json.dumps(counts, indent=2)+'\n')
    with ThreadPoolExecutor(max_workers=workers) as pool:
        records = list(pool.map(lambda wall: reference(wall, images, source_hash, output), walls))
    document = {'written_by': 'AI, GPT-6 Astra, 2026-10-26', 'date': datetime.now(timezone.utc).isoformat(), 'tile': tile, 'counts': counts, 'source': {'path': str(source),'sha256': source_hash}, 'bgt_reference_hashes': surface_hashes, 'merge': {'max_angle_degrees': ANGLE_DEGREES,'max_plane_distance_m': PLANE_DISTANCE_M,'max_connectivity_gap_m': CONNECTIVITY_GAP_M,'method': 'largest_plane_seed_per_building_bounded_complete_plane_distance_connected_projected_geometry'}, 'limitations': ['Photo UV coverage is not verified visibility. Vegetation, roof bleed and all other occlusions need C3 semantic masks.', 'Street classification samples nine outward rays across a wall. Same-building obstruction uses vertical-wall slices at wall-centre NAP height, excluding roof overhang projections; other buildings retain footprint blockers. Outward orientation from source winding is explicitly identified where footprint-offset tests are ambiguous.'], 'walls': records}
    (output/'walls.json').write_text(json.dumps(document, indent=2)+'\n')
    print(str(destination), flush=True)
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tile', default=TILE)
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    prepare_walls(args.tile, args.workers)
