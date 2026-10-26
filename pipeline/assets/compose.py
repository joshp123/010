#!/usr/bin/env -S .devenv/profile/bin/python
"""Written by AI on 2026-10-26 by model GPT-6 Astra.

Compose drawn miniature parts at measured positions at native 5 cm pixels.
No model calls; Claude owns generated-raw.png and generation.json.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from PIL import Image

from composed_parts import load_library, material_tile, opening_part, cornice_part, component_part

ROOT = Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
TILE = 'x90250_y436000'


def read_json(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def measured_colour(fact):
    value = fact.get('mean_colour_srgb')
    if isinstance(value, str) and len(value) == 7 and value.startswith('#'):
        return np.array([int(value[i:i+2], 16) for i in (1, 3, 5)])
    return None


def material_name(fact):
    value = fact.get('material', 'other')
    return value.get('class', 'other') if isinstance(value, dict) else value


def accepted_openings(fact):
    result, seen = [], set()
    for key in ('openings', 'doors', 'shop_fronts'):
        for opening in fact.get(key, []):
            rectangle = opening.get('box_px')
            identity = (opening.get('kind'), tuple(rectangle or []))
            if opening.get('status') != 'edge_supported' or opening.get('partial') or not rectangle or identity in seen:
                continue
            seen.add(identity)
            result.append(opening)
    return result


def valid_rectangle(rectangle, size):
    return (isinstance(rectangle, list) and len(rectangle) == 4
            and 0 <= rectangle[0] < rectangle[2] <= size[0]
            and 0 <= rectangle[1] < rectangle[3] <= size[1])


def material_sample(fact):
    colour = measured_colour(fact)
    if colour is None:
        return None
    return {'colour': colour, 'material': material_name(fact), 'fact': fact}


def texture_wall(wall, fact, inherited_sample, library):
    size = tuple(wall['image_size_px'])
    own = material_sample(fact)
    sample = own or inherited_sample
    if sample is None:
        raise ValueError('Composition requires a tile measured material fallback')
    material = sample['material']
    target = sample['colour']
    canvas = material_tile(target, material, wall['bag_id'], size=size, library=library)
    same_building = sample['fact']['wall_id'].split(':')[0] == str(wall['bag_id'])
    colour_route = ('measured' if own else 'same-building-measured-interpretation'
                    if same_building else 'tile-measured-interpretation')
    drawn, rejected, trims = [], [], []
    def draw_components(layer):
        for index,component in enumerate(fact.get('source_review_components',[])):
            rectangle = component.get('box_px')
            if component.get('layer','foreground') != layer or not valid_rectangle(rectangle,size):
                continue
            left,top,right,bottom = map(int,rectangle)
            part,method = component_part((right-left,bottom-top),dict(component,wall_id=wall['wall_id']),wall['wall_id']+str(index),library)
            canvas.paste(part,(left,top))
            trims.append({'kind':component['kind'],'rectangle_px':rectangle,'method':method,
                          'source_review_component':component,'verified_fraction':0,'interpreted_fraction':1})
    draw_components('background')
    for opening in accepted_openings(fact)+fact.get('source_review_additions', []):
        rectangle = opening['box_px']
        if not valid_rectangle(rectangle, size):
            rejected.append({'opening': opening, 'reason': 'rectangle_outside_wall'})
            continue
        rectangle = list(map(int, rectangle))
        left, top, right, bottom = rectangle
        if wall['wall_id'] == '0599100000650062:side-004':
            centre = ((left+right)/2,(top+bottom)/2)
            strips = [c for c in fact.get('source_review_components',[]) if c['kind']=='glazing_strip']
            if any(c['box_px'][0] <= centre[0] <= c['box_px'][2] and c['box_px'][1] <= centre[1] <= c['box_px'][3] for c in strips):
                rejected.append({'opening':opening,'reason':'superseded-by-source-reviewed-continuous-glazing-strip'})
                continue
        measured_outer_rectangle = rectangle[:]
        lintels = [c for c in fact.get('source_review_components',[]) if c['kind']=='lintel']
        for lintel in lintels:
            lx,ly,rx,ry = lintel['box_px']
            if lx <= (left+right)/2 <= rx and top <= ry < bottom and ly < top+max(1,(bottom-top)/2):
                top = max(top,ry)
        rectangle = [left,top,right,bottom]
        part, method = opening_part((right-left,bottom-top), opening['kind'], opening.get('type'),
                                    wall['wall_id']+str(rectangle), library)
        canvas.paste(part, (left,top))
        drawn.append({'kind': opening['kind'], 'rectangle_px': rectangle,
                      'source_fact': opening, 'measured_outer_rectangle_px':measured_outer_rectangle, 'method': method,
                      'interpretation': 'Position is edge-supported; part detail and unmeasured type are interpreted.'})
    cornice = fact.get('cornice') or {}
    rectangle = cornice.get('box_px')
    if cornice.get('observed') and cornice.get('type') not in (None,'none','unknown') and valid_rectangle(rectangle,size):
        left,top,right,bottom = map(int,rectangle)
        # No trim is added outside a measured trim rectangle.
        part, method = cornice_part((right-left,bottom-top),cornice['type'],
                                   np.clip(target+35,0,255),wall['wall_id'],library)
        canvas.paste(part,(left,top))
        trims.append({'kind':'cornice','rectangle_px':rectangle,'source_fact':cornice,'method':method})
    draw_components('foreground')
    return canvas, {'material':material,'material_route':'miniature-parts',
                    'colour_route':colour_route,'mean_colour_srgb':target.tolist(),
                    'material_sample':{'wall_id':sample['fact']['wall_id'],
                                       'photo':sample['fact'].get('photo'),
                                       'method':'scalar-mean-only-no-photo-texels'},
                    'openings_drawn':drawn,'openings_rejected':rejected,'trims_drawn':trims,
                    'uncomposed_gable_type':fact.get('gable_type','unknown'),
                    'appearance':'Miniature parts, scalar measured colour and exact accepted opening rectangles; no photograph pixels.',
                    'interpretation':'Material drawing, part detail, and inherited colours are interpreted; no unmeasured openings or trims are invented.'}


def area_class(area):
    return 'under-10' if area < 10 else '10-to-100' if area <= 100 else 'over-100'


def elevation_groups(assets_root, tile):
    groups, membership, paths = [], defaultdict(list), []
    for path in sorted((assets_root/'elevations').glob('*/reference.json')):
        reference = read_json(path)
        if reference.get('tile') != tile:
            continue
        area = sum(w.get('geometry_area_m2', 0) for w in reference.get('walls', []))
        group = {'id': reference['id'], 'area_m2': area, 'area_class': area_class(area),
                 'reference': str(path)}
        groups.append(group)
        paths.append(path)
        for wall in reference.get('walls', []):
            for triangle in wall.get('triangles', []):
                membership[(triangle['primitive_index'], triangle['triangle_index'])].append(group)
    return groups, membership, paths


def compose(facts_root, assets_root, walls_path, tile=TILE):
    start = time.monotonic()
    source_path = ROOT/'scene/v1/tiles'/tile/'buildings.glb'
    if (not walls_path.exists() or
            read_json(walls_path).get('source',{}).get('sha256') != sha(source_path)):
        from wall_facts import prepare_walls
        walls_path = prepare_walls(tile)
    walls_document = read_json(walls_path)
    walls = walls_document['walls']
    facts, fact_paths = {}, []
    walls_by_id = {wall['wall_id']:wall for wall in walls}
    bag_ids = {str(w['bag_id']) for w in walls}
    for bag in sorted(bag_ids):
        local_path = facts_root/'work'/tile/'buildings'/f'{bag}.json'
        path = local_path if local_path.exists() else facts_root/'buildings'/f'{bag}.json'
        if not path.exists():
            continue
        fact_paths.append(path)
        document = read_json(path)
        if document.get('tile') != tile:
            continue
        for fact in document.get('walls', []):
            wall = walls_by_id.get(fact['wall_id'])
            if wall is None:
                continue
            recorded_hash = fact.get('provenance',{}).get('reference_hashes',{}).get(wall['reference'])
            if recorded_hash != wall['reference_sha256']:
                continue
            facts[fact['wall_id']] = fact
    source_review_path = assets_root/'tiles'/tile/'tier2-comparison'/'source-review.json'
    source_review = read_json(source_review_path) if source_review_path.exists() else {}
    if source_review:
        for correction in source_review.get('walls',[]):
            fact = facts.get(correction['wall_id'])
            if fact and fact.get('photo') == correction.get('photo') and sha(fact['photo']) == correction.get('photo_sha256'):
                removed = correction.get('remove_source_indices',[])
                for key in ('openings','doors','shop_fronts'):
                    fact[key] = [opening for opening in fact.get(key,[]) if opening.get('source_index') not in removed]
                fact['source_review_additions'] = correction.get('add_openings',[])
                fact['source_review_components'] = correction.get('components',[])
                fact['source_review'] = str(source_review_path)
    groups, membership, reference_paths = elevation_groups(assets_root, tile)
    library_directory = assets_root/'parts'
    library = load_library(library_directory)
    paths = {Path(__file__), Path(__file__).with_name('composed_parts.py'), walls_path, *fact_paths, *reference_paths}
    if source_review_path.exists():
        paths.add(source_review_path)
    if library_directory.exists():
        paths.update(p for p in library_directory.rglob('*') if p.is_file())
    for wall in walls:
        paths.add(Path(wall['reference']))
    for fact in facts.values():
        for key in ('photo', 'evidence_mask', 'occlusion_mask'):
            if fact.get(key) and Path(fact[key]).exists():
                paths.add(Path(fact[key]))
    hashes = {str(p): sha(p) for p in sorted(paths)}
    fingerprint = hashlib.sha256(json.dumps({'tile': tile, 'hashes': hashes,
                                             'groups': groups, 'source_review':source_review}, sort_keys=True).encode()).hexdigest()
    directory = assets_root/'tiles'/tile/'composed'
    output = directory/'composition.json'
    if output.exists():
        previous = read_json(output)
        if previous.get('input_fingerprint') == fingerprint and all(Path(a['path']).exists() for a in previous['atlases']):
            print(json.dumps({'status': 'unchanged', 'input_fingerprint': fingerprint, 'counts': previous['counts']}))
            return previous
    directory.mkdir(parents=True, exist_ok=True)
    building_samples = defaultdict(list)
    for wall in walls:
        fact = facts.get(wall['wall_id'], {})
        sample = material_sample(fact)
        if sample:
            building_samples[str(wall['bag_id'])].append((wall['area_m2'], sample))
    inherited = {bag: max(samples, key=lambda item: item[0])[1] for bag, samples in building_samples.items()}
    all_samples = [sample for samples in building_samples.values() for _, sample in samples]
    if not all_samples:
        raise ValueError('No measured tile material exists')
    median_colour = np.median([s['colour'] for s in all_samples], axis=0)
    tile_sample = min(all_samples, key=lambda sample: np.linalg.norm(sample['colour']-median_colour))
    limit, gutter = 4096, 2
    atlas = Image.new('RGB', (limit, limit), (160, 160, 160))
    atlases, records = [], []
    x = y = row_height = atlas_index = 0

    def save_atlas(canvas=None):
        canvas = atlas if canvas is None else canvas
        canvas_size = canvas.size
        path = directory/f'wall-atlas-{atlas_index:03d}.webp'
        pending_path = path.with_name('.'+path.name+'.pending')
        canvas.save(pending_path, 'WEBP', lossless=True, method=4)
        pending_path.replace(path)
        mask_path = directory/f'wall-atlas-{atlas_index:03d}-interpreted.png'
        pending_mask = mask_path.with_name('.'+mask_path.name+'.pending')
        Image.new('L',canvas_size,255).save(pending_mask,'PNG')
        pending_mask.replace(mask_path)
        atlases.append({'id': f'c4-tier2-{atlas_index:03d}', 'path': str(path),
                        'interpreted_mask': str(mask_path),
                        'image_size_px': list(canvas_size), 'sha256': sha(path)})

    def packing_order(wall):
        oversized = max(wall['image_size_px'])+2*gutter > limit
        return (not oversized, -wall['image_size_px'][1])

    for wall in sorted(walls, key=packing_order):
        fact = facts.get(wall['wall_id'], {})
        image, details = texture_wall(wall, fact, inherited.get(str(wall['bag_id']), tile_sample), library)
        width, height = image.size
        oversized = max(width, height)+2*gutter > limit
        if max(width,height)+2*gutter > 16383:
            raise ValueError(f'Wall exceeds WebP native size limit: {wall["wall_id"]} {image.size}')
        if not oversized and x+width+2*gutter > limit:
            x, y, row_height = 0, y+row_height, 0
        if not oversized and y+height+2*gutter > limit:
            save_atlas()
            atlas_index += 1
            atlas = Image.new('RGB', (limit, limit), (160, 160, 160))
            x = y = row_height = 0
        left, top = (gutter,gutter) if oversized else (x+gutter,y+gutter)
        padded = Image.fromarray(np.pad(np.asarray(image), ((gutter,gutter),(gutter,gutter),(0,0)), mode='edge'))
        if oversized:
            atlas_size = np.asarray(padded.size)
            save_atlas(padded)
        else:
            atlas_size = np.array([limit,limit])
            atlas.paste(padded, (x, y))
        triangles, wall_groups, routes = [], {}, Counter()
        for triangle in wall['triangles']:
            key = triangle['primitive_index'], triangle['triangle_index']
            candidates = membership.get(key, [])
            # Preserve all memberships, but assign one bounded work route per triangle.
            group = max(candidates, key=lambda g: g['area_m2']) if candidates else None
            category = group['area_class'] if group else area_class(wall['area_m2'])
            route = {'under-10': 'fragment-material-fallback', '10-to-100': 'tier2-parts-composed',
                     'over-100': 'tier1-parts-fallback'}[category]
            routes[route] += 1
            for item in candidates:
                wall_groups[item['id']] = item
            uv = (np.asarray(triangle['pixel_vertices'])+[left,top])/atlas_size
            triangles.append({'primitive_index': key[0], 'triangle_index': key[1], 'uv': uv.tolist(),
                              'composition_route': route, 'elevation_group': group['id'] if group else None})
        route = next(iter(routes)) if len(routes) == 1 else 'mixed'
        records.append({'wall_id': wall['wall_id'], 'bag_id': wall['bag_id'], 'feature_index': wall['feature_index'],
                        'area_m2': wall['area_m2'], 'wall_area_class': area_class(wall['area_m2']),
                        'street_facing': wall['street_facing'], 'atlas_index': atlas_index,
                        'rectangle_px': [left,top,left+width,top+height], 'triangles': triangles,
                        'route': 'tier2-composed', 'composition_route': route,
                        'triangle_route_counts': dict(routes), 'elevation_groups': list(wall_groups.values()),
                        'facts_path': next((str(p) for p in fact_paths if p.stem == str(wall['bag_id'])), None),
                        'facts_present': bool(fact), 'details': details,
                        'verified_fraction': 0, 'interpreted_fraction': 1, 'occluded_fraction': fact.get('occluded_fraction', 1),
                        'visible_evidence_fraction': fact.get('visible_evidence_fraction', 0),
                        'failed_evidence_fraction': fact.get('failed_evidence_fraction', 0),
                        'evidence_mask': fact.get('evidence_mask'), 'occlusion_mask': fact.get('occlusion_mask'),
                        'source_reference': fact.get('photo', wall['reference']), 'provenance': fact.get('provenance', {}),
                        'verification': {'status': 'drawn-parts-not-independently-verified'},
                        'interpreted': True})
        if oversized:
            atlas_index += 1
        else:
            x += width+2*gutter
            row_height = max(row_height, height+2*gutter)
    if x or y or not atlases:
        save_atlas()
    elapsed = time.monotonic()-start
    result = {'written_by': 'AI, GPT-6 Astra, 2026-10-26', 'date': datetime.now(timezone.utc).isoformat(),
              'tile': tile, 'method': 'c3-miniature-parts-composition-v3-no-photo-texels', 'pixel_size_m': .05,
              'tier1_selection': 'Assembly selects current accepted Claude generations dynamically; this file contains a drawn parts fallback for every measured wall triangle.',
              'input_fingerprint': fingerprint, 'input_hashes': hashes, 'walls_source': str(walls_path),
              'atlases': atlases, 'walls': records, 'elevation_groups': groups,
              'elapsed_seconds': elapsed, 'image_calls': 0, 'model_calls': 0, 'photo_texels_retained': 0,
              'seconds_per_building': elapsed/len(bag_ids) if bag_ids else 0,
              'counts': {'walls': len(records), 'buildings': len(bag_ids),
                         'facts_present': sum(r['facts_present'] for r in records),
                         'wall_area_classes': dict(Counter(r['wall_area_class'] for r in records)),
                         'elevation_group_area_classes': dict(Counter(g['area_class'] for g in groups)),
                         'composition_routes': dict(Counter(r['composition_route'] for r in records)),
                         'triangle_routes': dict(sum((Counter(r['triangle_route_counts']) for r in records), Counter())),
                         'openings_drawn': sum(len(r['details']['openings_drawn']) for r in records),
                         'colour_routes': dict(Counter(r['details']['colour_route'] for r in records))}}
    pending_output = output.with_name('.composition.json.pending')
    pending_output.write_text(json.dumps(result, indent=2)+'\n')
    pending_output.replace(output)
    print(json.dumps({key: result[key] for key in ('elapsed_seconds', 'seconds_per_building', 'counts')}))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tile', default=TILE)
    parser.add_argument('--facts-root', type=Path, default=ROOT/'facts/v1')
    parser.add_argument('--assets-root', type=Path, default=ROOT/'assets/v1')
    parser.add_argument('--walls', type=Path)
    args = parser.parse_args()
    compose(args.facts_root, args.assets_root,
            args.walls or args.facts_root/'work'/args.tile/'walls.json', args.tile)
