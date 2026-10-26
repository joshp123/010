#!/usr/bin/env -S .devenv/profile/bin/python
"""Written by AI on 2026-10-26 by model GPT-6 Astra.

Assemble evidence-made textures onto the unchanged municipal tile geometry.
"""
import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
import os
import re
from pathlib import Path
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'buildings'))
from build import accessor, unpack_glb

ROOT = Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
DEFAULT_TILE = os.environ.get('ASSET_TILE', 'x90250_y436000')


class BinaryWriter:
    def __init__(self, document):
        self.document = document
        self.binary = bytearray()

    def view(self, data, target=None):
        self.binary.extend(b'\x00' * (-len(self.binary) % 4))
        view = {'buffer': 0, 'byteOffset': len(self.binary), 'byteLength': len(data)}
        if target:
            view['target'] = target
        self.document['bufferViews'].append(view)
        self.binary.extend(data)
        return len(self.document['bufferViews']) - 1

    def attribute(self, values, original):
        values = np.ascontiguousarray(values)
        record = {key: deepcopy(value) for key, value in original.items()
                  if key not in ('bufferView', 'byteOffset', 'count', 'min', 'max', 'sparse')}
        record.update(bufferView=self.view(values.tobytes(), 34962), count=len(values))
        if 'min' in original:
            record['min'] = np.atleast_1d(values.min(axis=0)).tolist()
            record['max'] = np.atleast_1d(values.max(axis=0)).tolist()
        self.document['accessors'].append(record)
        return len(self.document['accessors']) - 1


def webp_bytes(image, quality):
    stream = io.BytesIO()
    image.convert('RGB').save(stream, format='WEBP', quality=quality, method=6)
    return stream.getvalue()


def wall_checks(generation):
    verification = generation.get('verification') or {}
    if isinstance(verification, dict):
        records = verification.get('walls', generation.get('walls', []))
    else:
        records = generation.get('walls', [])
    if isinstance(records, dict):
        return records
    return {record.get('wall_id', record.get('bag_id')): record for record in records}


def generated_texture_path(directory, generation):
    chosen = generation.get('texture_path') or generation.get('output_aligned')
    if chosen:
        path = Path(chosen)
        return path if path.is_absolute() else directory / path
    return directory / 'generated-raw.png'


def geometry_triangles(document, binary):
    triangles = Counter()
    for primitive in document['meshes'][0]['primitives']:
        arrays = [accessor(document, binary, primitive['attributes'][name])
                  for name in ('POSITION', 'NORMAL', '_FEATURE_ID_0')]
        count = len(arrays[0]) // 3
        for parts in zip(*(array.reshape(count, 3, -1) for array in arrays)):
            triangles[b''.join(part.tobytes() for part in parts)] += 1
    return triangles


def remove_unused_resources(document, binary):
    """Keep only rendered materials/images and repack their actual buffer views."""
    used_materials=sorted({p['material'] for m in document['meshes'] for p in m['primitives']})
    material_map={old:new for new,old in enumerate(used_materials)}
    document['materials']=[document['materials'][i] for i in used_materials]
    for mesh in document['meshes']:
        for primitive in mesh['primitives']:
            primitive['material']=material_map[primitive['material']]
    infos=[]
    def visit(node):
        if isinstance(node,dict):
            for key,value in node.items():
                if key.endswith('Texture') and isinstance(value,dict) and 'index' in value:infos.append(value)
                else:visit(value)
        elif isinstance(node,list):
            for value in node:visit(value)
    visit(document['materials'])
    used_textures=sorted({info['index'] for info in infos})
    texture_map={old:new for new,old in enumerate(used_textures)}
    document['textures']=[document['textures'][i] for i in used_textures]
    for info in infos:info['index']=texture_map[info['index']]
    sources=[]
    for texture in document['textures']:
        if 'source' in texture:sources.append(texture)
        for extension in texture.get('extensions',{}).values():
            if 'source' in extension:sources.append(extension)
    used_images=sorted({source['source'] for source in sources})
    image_map={old:new for new,old in enumerate(used_images)}
    document['images']=[document['images'][i] for i in used_images]
    for source in sources:source['source']=image_map[source['source']]
    users=document['accessors']+document['images']
    used_views=sorted({user['bufferView'] for user in users})
    view_map={old:new for new,old in enumerate(used_views)}
    packed=bytearray()
    views=[]
    for index in used_views:
        view=deepcopy(document['bufferViews'][index])
        start=view.get('byteOffset',0)
        payload=binary[start:start+view['byteLength']]
        packed.extend(b'\x00'*(-len(packed)%4))
        view['byteOffset']=len(packed)
        packed.extend(payload)
        views.append(view)
    for user in users:user['bufferView']=view_map[user['bufferView']]
    document['bufferViews']=views
    document['buffers'][0]['byteLength']=len(packed)
    return packed


def compact_wall_record(wall):
    result = {key:wall[key] for key in ('wall_id','route','area_m2','evidence_fraction','verified_fraction','occluded_fraction','failed_evidence_fraction') if key in wall}
    check = wall.get('check',{})
    result['checks'] = check.get('checks',check)
    if wall.get('generation'):
        result['verification_record'] = wall['generation'].get('verification')
        result['elevation'] = wall.get('elevation')
    return result


def write_provenance_tint(document, binary, masks, target):
    tinted = deepcopy(document)
    writer = BinaryWriter(tinted)
    writer.binary = bytearray(binary)
    changed = 0
    for image in tinted['images']:
        mask = masks.get(image.get('name'))
        if mask is None:
            raise ValueError(f"Missing interpretation mask for {image.get('name')}")
        view = tinted['bufferViews'][image['bufferView']]
        start = view.get('byteOffset',0)
        pixels = np.array(Image.open(io.BytesIO(binary[start:start+view['byteLength']])).convert('RGB'))
        selected = np.asarray(mask.resize((pixels.shape[1],pixels.shape[0]), Image.Resampling.NEAREST)) > 0
        pixels[selected] = np.rint(pixels[selected]*.55 + np.array([255,0,255])*.45).astype(np.uint8)
        stream = io.BytesIO()
        Image.fromarray(pixels).save(stream, format='PNG')
        image['bufferView'] = writer.view(stream.getvalue())
        image['mimeType'] = 'image/png'
        changed += int(selected.sum())
    for texture in tinted['textures']:
        source = texture.get('extensions',{}).pop('EXT_texture_webp',{}).get('source')
        if source is not None:
            texture['source'] = source
        if not texture.get('extensions'):
            texture.pop('extensions',None)
    for field in ('extensionsUsed','extensionsRequired'):
        tinted[field] = [name for name in tinted.get(field,[]) if name != 'EXT_texture_webp']
    packed = remove_unused_resources(tinted, writer.binary)
    text = json.dumps(tinted,separators=(',',':'),allow_nan=False).encode()
    text += b' '*(-len(text)%4)
    payload = bytes(packed)+b'\x00'*(-len(packed)%4)
    output = struct.pack('<III',0x46546C67,2,28+len(text)+len(payload))+struct.pack('<II',len(text),0x4E4F534A)+text+struct.pack('<II',len(payload),0x004E4942)+payload
    before,after = unpack_glb(output)
    if geometry_triangles(document,binary) != geometry_triangles(before,after):
        raise ValueError('Provenance tint changed geometry')
    temporary = target.with_name('.'+target.name+'.pending')
    temporary.write_bytes(output)
    temporary.replace(target)
    return {'path':str(target),'bytes':len(output),'sha256':hashlib.sha256(output).hexdigest(),'tinted_texels':changed,'blend':.45,'colour':'#ff00ff','encoding':'Lossless PNG of decoded delivery texels; only interpreted pixels changed'}


def assemble(assets_root, target=None, quality=86, provenance_tint=False, tile=DEFAULT_TILE):
    match = re.fullmatch(r'x(\d+)_y(\d+)', tile)
    if not match:
        raise ValueError(f'Invalid tile identifier: {tile}')
    origin_x, origin_y = map(int, match.groups())
    target = target or assets_root / 'tiles' / tile / 'buildings.glb'
    source = ROOT / 'scene/v1/tiles' / tile / 'buildings.glb'
    source_bytes = source.read_bytes()
    original, binary = unpack_glb(source_bytes)
    document = deepcopy(original)
    document.update(accessors=[], bufferViews=[], images=[], buffers=[{'byteLength': 0}])
    document['asset']['generator'] = '010 evidence asset assembly v1; unchanged source geometry'
    writer = BinaryWriter(document)
    texture_statistics = []
    interpreted_texture_masks = {}
    material_region_masks = {}
    encoded_asset_views = {}
    for image_index, original_image in enumerate(original.get('images', [])):
        view = original['bufferViews'][original_image['bufferView']]
        start = view.get('byteOffset', 0)
        image = Image.open(io.BytesIO(binary[start:start + view['byteLength']]))
        encoded = webp_bytes(image, quality)
        document['images'].append({'bufferView': writer.view(encoded), 'mimeType': 'image/webp',
                                   'name': original_image.get('name', f'original-{image_index}')})
        texture_statistics.append({'kind': 'original', 'image': image_index, 'name': document['images'][-1]['name'], 'bytes': len(encoded)})
    for texture in document.get('textures', []):
        image_index = texture.pop('source')
        texture.setdefault('extensions', {})['EXT_texture_webp'] = {'source': image_index}
    for field in ('extensionsUsed', 'extensionsRequired'):
        document[field] = list(dict.fromkeys(document.get(field, []) + ['EXT_texture_webp']))
    document.setdefault('samplers', []).append({'magFilter': 9728, 'minFilter': 9984,
                                                'wrapS': 33071, 'wrapT': 33071})
    sampler_index = len(document['samplers']) - 1
    assignments, feature_walls, feature_reused_walls = {}, defaultdict(list), defaultdict(list)
    assignment_routes = {}
    generations = []

    def add_texture_material(image, name, kind, interpreted_mask=None):
        if kind == 'tier2-composed':
            stream = io.BytesIO()
            image.convert('RGB').save(stream, format='WEBP', quality=95, method=6)
            encoded = stream.getvalue()
        else:
            encoded = webp_bytes(image, quality)
        image_index = len(document['images'])
        encoded_hash = hashlib.sha256(encoded).hexdigest()
        if encoded_hash not in encoded_asset_views:
            encoded_asset_views[encoded_hash] = writer.view(encoded)
        document['images'].append({'bufferView': encoded_asset_views[encoded_hash], 'mimeType': 'image/webp', 'name': name})
        interpreted_texture_masks[name] = (interpreted_mask.convert('L').resize(image.size, Image.Resampling.NEAREST) if interpreted_mask is not None else Image.new('L', image.size, 255))
        texture_index = len(document.setdefault('textures', []))
        document['textures'].append({'sampler': sampler_index,
                                     'extensions': {'EXT_texture_webp': {'source': image_index}}})
        material_index = len(document['materials'])
        document['materials'].append({'name': name, 'pbrMetallicRoughness': {
            'baseColorFactor': [1, 1, 1, 1], 'baseColorTexture': {'index': texture_index},
            'metallicFactor': 0, 'roughnessFactor': 1}, 'doubleSided': False, 'extras': {'asset': True}})
        material_region_masks[material_index] = np.asarray(interpreted_texture_masks[name])
        texture_statistics.append({'kind': kind, 'name': name, 'bytes': len(encoded), 'size_px': list(image.size)})
        return material_index

    pending_elevations = []
    rejected_generated_walls = []
    # Claude owns raw images and generator metadata; derived verification is ours.
    for sidecar_path in sorted((assets_root / 'elevations').glob('*/reference.json')):
        directory = sidecar_path.parent
        reference = json.loads(sidecar_path.read_text())
        if reference.get('tile') != tile:
            continue
        raw_path = directory / 'generated-raw.png'
        chunks = sorted(path for path in (directory / 'chunks').glob('*') if path.is_dir())
        if chunks and any(not (chunk / 'generated-raw.png').exists() for chunk in chunks):
            pending_elevations.append({'id': directory.name, 'reason': 'generation_chunks_incomplete'})
            continue
        if not raw_path.exists():
            if chunks:
                pending_elevations.append({'id': directory.name, 'reason': 'awaiting_stitched_generation'})
            continue
        verification_path = directory / 'verification.json'
        if not verification_path.exists():
            pending_elevations.append({'id': directory.name, 'reason': 'awaiting_verification'})
            continue
        verification = json.loads(verification_path.read_text())
        raw_hash = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        reference_hash = hashlib.sha256((directory/'reference.png').read_bytes()).hexdigest()
        if verification.get('raw_sha256') != raw_hash or verification.get('reference_sha256') != reference_hash:
            pending_elevations.append({'id': directory.name, 'reason': 'raw_or_reference_changed_since_verification'})
            continue
        aligned_path = directory / 'generated-aligned.png'
        if not aligned_path.exists() or hashlib.sha256(aligned_path.read_bytes()).hexdigest() != verification.get('compared_texture_sha256'):
            pending_elevations.append({'id': directory.name, 'reason': 'aligned_texture_missing_or_changed'})
            continue
        generation_path = directory / 'generation.json'
        try:
            generation = json.loads(generation_path.read_text()) if generation_path.exists() else {}
        except json.JSONDecodeError:
            pending_elevations.append({'id': directory.name, 'reason': 'generator_metadata_being_written'})
            continue
        generation['verification'] = verification
        raw_path = aligned_path
        image = Image.open(raw_path).convert('RGB').resize(tuple(reference['image_size_px']), Image.Resampling.LANCZOS)
        mask_path = directory / 'interpreted-mask.png'
        checks = wall_checks(generation)
        interpreted_mask = Image.open(mask_path).convert('L') if mask_path.exists() else Image.new('L', image.size,255)
        wall_ids_path = directory/'wall-ids.png'
        if wall_ids_path.exists():
            ids = np.asarray(Image.open(wall_ids_path))
            mask_array = np.array(interpreted_mask)
            for record in checks.values():
                if record.get('checks',{}).get('passed') is not True:
                    mask_array[ids == record.get('mask_value',-1)] = 255
            interpreted_mask = Image.fromarray(mask_array)
        material = add_texture_material(image, reference['id'], 'elevation', interpreted_mask)
        generations.append({'id': reference['id'], 'generation': str(generation_path),
                            'model': generation.get('model'), 'model_version': generation.get('model_version'),
                            'date': generation.get('ended_at'), 'tool': generation.get('tool', 'image_gen.imagegen'),
                            'prompt_sha256': generation.get('prompt_sha256'),
                            'reference_sha256': reference['source'].get('image_sha256'),
                            'output_sha256': hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                            'verification': str(verification_path), 'raw_sha256': raw_hash,
                            'reference_sha256': reference_hash})
        for wall in reference['walls']:
            check = checks.get(wall['wall_id'], checks.get(wall['bag_id'], {}))
            selected = []
            if check.get('checks',{}).get('passed') is False:
                rejected_generated_walls.append({'elevation': reference['id'], 'wall_id': wall['wall_id'], 'reason': 'source_comparison_failed'})
                continue
            for triangle in wall['triangles']:
                key = (triangle['primitive_index'], triangle['triangle_index'])
                if key in assignments:
                    continue
                uv = np.asarray(triangle['pixel_vertices'], dtype=np.float32) / np.asarray(reference['image_size_px'], dtype=np.float32)
                assignments[key] = (material, uv)
                assignment_routes[key] = 'tier1-generated'
                selected.append(key)
            if selected:
                feature_walls[wall['feature_index']].append({
                    'wall_id': wall['wall_id'], 'elevation': reference['id'], 'area_m2': 0.,
                    'triangle_keys': selected, 'route': 'tier1-generated',
                    'evidence': wall['evidence'], 'check': check,
                    'generation': generations[-1], 'evidence_mask': str(directory / 'evidence-mask.png'),
                    'interpreted_regions': check.get('interpreted_regions', {
                        'raster_mask': str(directory / 'interpreted-mask.png'),
                        'wall_ids_mask': str(directory / 'wall-ids.png'),
                        'wall_mask_value': wall.get('mask_value')}),
                    'evidence_fraction': check.get('evidence_share', 0),
                    'verified_fraction': check.get('verified_share', 0),
                    'occluded_fraction': check.get('interpreted_share', 1) if check.get('checks',{}).get('passed') is True else 1.,
                    'failed_evidence_fraction': check.get('failed_evidence_share', 0),
                    'interpreted': bool(check.get('interpreted_share',1)) or check.get('checks',{}).get('passed') is not True,
                    'semantic_verified_fraction': 0.})
    composition_path = assets_root / 'tiles' / tile / 'composed/composition.json'
    composition_bytes = composition_path.read_bytes() if composition_path.exists() else b'{}'
    composition_hash = hashlib.sha256(composition_bytes).hexdigest()
    composition = json.loads(composition_bytes)
    if composition.get('photo_texels_retained') != 0:
        raise ValueError('Run compose.py: photo-free composition is required; photo texels must not ship')
    composed_materials = {}
    for wall in composition.get('walls', []):
        selected = []
        for triangle in wall['triangles']:
            key = (triangle['primitive_index'], triangle['triangle_index'])
            if key in assignments:
                continue
            atlas_index = wall['atlas_index']
            if atlas_index not in composed_materials:
                atlas = composition['atlases'][atlas_index]
                mask_path = Path(atlas['interpreted_mask']) if atlas.get('interpreted_mask') else None
                composed_materials[atlas_index] = add_texture_material(Image.open(atlas['path']), atlas['id'], 'tier2-composed', Image.open(mask_path) if mask_path and mask_path.exists() else None)
            assignments[key] = composed_materials[atlas_index], np.asarray(triangle['uv'], dtype=np.float32)
            assignment_routes[key] = 'tier2-composed'
            selected.append(key)
        if selected:
            feature_walls[wall['feature_index']].append({
                'wall_id': wall['wall_id'], 'route': 'tier2-composed', 'area_m2': 0.,
                'triangle_keys': selected, 'evidence': [wall['source_reference']] if wall.get('source_reference') else [],
                'composition': str(composition_path), 'facts': wall['facts_path'], 'details': wall['details'],
                'evidence_mask': wall.get('evidence_mask'), 'source_occlusion_mask': wall.get('occlusion_mask'),
                'interpreted_regions': {'raster_mask': composition['atlases'][wall['atlas_index']].get('interpreted_mask'), 'rectangle_px':wall.get('rectangle_px'), 'coordinate_space':'composition-atlas-pixels'},
                'evidence_fraction': wall.get('visible_evidence_fraction', 0),
                'verified_fraction': wall.get('verified_fraction', 0),
                'occluded_fraction': wall.get('interpreted_fraction', wall.get('occluded_fraction', 1)),
                'failed_evidence_fraction': wall.get('failed_evidence_fraction', 0),
                'check': wall.get('verification', {}), 'provenance': wall.get('provenance', {})})
    reuse_plan_path = assets_root / 'tiles' / tile / 'reuse/reuse-plan.json'
    roof_path = assets_root / 'roofs' / tile / 'roof.webp'
    roof_generation_path = roof_path.with_name('generation.json')
    roof_generation = json.loads(roof_generation_path.read_text()) if roof_generation_path.exists() else {}
    if not roof_path.exists():
        raise ValueError('Roof asset is required; source photograph fallback is forbidden')
    roof_image = Image.open(roof_path).convert('RGB')
    roof_mask_path = roof_path.with_name('interpreted-mask.png')
    roof_mask = Image.open(roof_mask_path).convert('L') if roof_mask_path.exists() else Image.new('L', roof_image.size, 255)
    # Extend the generated roof asset over whole features crossing the tile edge.
    source_positions = np.concatenate([accessor(original, binary, p['attributes']['POSITION']) for p in original['meshes'][0]['primitives']])
    roof_bounds = [min(0., float(source_positions[:,0].min())), min(0., float((-source_positions[:,2]).min())), max(250., float(source_positions[:,0].max())), max(250., float((-source_positions[:,2]).max()))]
    roof_scale = roof_image.width / 250.
    left, top = int(np.ceil(-roof_bounds[0]*roof_scale)), int(np.ceil((roof_bounds[3]-250)*roof_scale))
    right, bottom = int(np.ceil((roof_bounds[2]-250)*roof_scale)), int(np.ceil(-roof_bounds[1]*roof_scale))
    roof_array = np.pad(np.asarray(roof_image), ((top,bottom),(left,right),(0,0)), mode='edge')
    roof_mask_array = np.pad(np.asarray(roof_mask), ((top,bottom),(left,right)), constant_values=255)
    roof_image = Image.fromarray(roof_array)
    roof_mask = Image.fromarray(roof_mask_array)
    roof_material = add_texture_material(roof_image, 'roof-2026', 'roof', roof_mask)
    interpreted_roof_material = None
    fallback_materials = {}
    fallback_wall_records = {}
    building_materials = {}
    for wall in composition.get('walls', []):
        colour = wall.get('details',{}).get('mean_colour_srgb')
        if colour is not None:
            building_materials.setdefault(wall['feature_index'], (colour, wall.get('details',{}).get('material', 'brick')))
    def fallback_wall_material(identifier, primitive):
        if identifier in fallback_materials:
            return fallback_materials[identifier]
        colour, material_class = building_materials.get(identifier, (None, 'other'))
        if colour is None:
            # Measure only a scalar colour; never transfer photograph texels.
            source_material = original['materials'][primitive['material']]
            texture_index = source_material.get('pbrMetallicRoughness',{}).get('baseColorTexture',{}).get('index')
            if texture_index is not None:
                image_index = original['textures'][texture_index]['source']
                view = original['bufferViews'][original['images'][image_index]['bufferView']]
                start = view.get('byteOffset',0)
                colour = np.asarray(Image.open(io.BytesIO(binary[start:start+view['byteLength']])).convert('RGB')).reshape(-1,3).mean(axis=0).tolist()
            else:
                colour = [int(v*255) for v in source_material.get('pbrMetallicRoughness',{}).get('baseColorFactor',[.5,.5,.5,1])[:3]]
        from composed_parts import material_tile
        from composed_parts import load_library
        image = material_tile(colour, material_class, identifier, library=load_library(assets_root/'parts'))
        result = add_texture_material(image, f'tier2-material:{identifier}', 'tier2-composed')
        material_texture_index = document['materials'][result]['pbrMetallicRoughness']['baseColorTexture']['index']
        document['samplers'].append({'magFilter':9728,'minFilter':9984,'wrapS':10497,'wrapT':10497})
        document['textures'][material_texture_index]['sampler'] = len(document['samplers'])-1
        fallback_materials[identifier] = result
        return result
    roof_triangle_shares = {}
    wall_triangle_shares = {}
    steps = 48
    roof_barycentric_samples = np.array([(i/steps,j/steps,1-(i+j)/steps) for i in range(steps+1) for j in range(steps+1-i)])

    roof_checks = (roof_generation.get('verification') or {}).get('roofs', [])
    if isinstance(roof_checks, list):
        roof_checks = {str(record.get('bag_id')): record for record in roof_checks}
    feature_area, feature_generated_area = defaultdict(float), defaultdict(float)
    feature_direct_wall_area, feature_reused_wall_area = defaultdict(float), defaultdict(float)
    feature_composed_wall_area = defaultdict(float)
    feature_roof_area, feature_generated_roof_area = defaultdict(float), defaultdict(float)
    output_primitives = []
    triangle_areas = {}
    route_areas = defaultdict(float)
    source_triangle_count = 0
    for primitive_index, primitive in enumerate(original['meshes'][0]['primitives']):
        if 'indices' in primitive:
            raise ValueError('Expected the existing non-indexed scene contract')
        attributes = {name: accessor(original, binary, index) for name, index in primitive['attributes'].items()}
        positions = attributes['POSITION'].reshape(-1, 3, 3)
        feature_ids = attributes['_FEATURE_ID_0'].reshape(-1, 3)[:, 0].astype(int)
        cross = np.cross(positions[:, 1] - positions[:, 0], positions[:, 2] - positions[:, 0])
        area = np.linalg.norm(cross, axis=1) / 2
        roof = cross[:, 1] > .2 * np.linalg.norm(cross, axis=1)
        buckets = defaultdict(list)
        new_uv = attributes['TEXCOORD_0'].reshape(-1, 3, 2).copy()
        for triangle_index, position in enumerate(positions):
            identifier = int(feature_ids[triangle_index])
            feature_area[identifier] += float(area[triangle_index])
            material = primitive['material']
            key = (primitive_index, triangle_index)
            triangle_areas[key] = float(area[triangle_index])
            if key in assignments:
                material, new_uv[triangle_index] = assignments[key]
                mask = material_region_masks[material]
                samples = roof_barycentric_samples @ new_uv[triangle_index]
                coordinates = np.minimum(np.maximum((samples*np.array([mask.shape[1],mask.shape[0]])).astype(int),0),np.array([mask.shape[1],mask.shape[0]])-1)
                interpreted_share = float((mask[coordinates[:,1],coordinates[:,0]]>0).mean())
                wall_triangle_shares[key] = (1-interpreted_share,interpreted_share)
                feature_generated_area[identifier] += float(area[triangle_index])
                route_areas[assignment_routes[key]] += float(area[triangle_index])
                if assignment_routes[key] == 'reused':
                    feature_reused_wall_area[identifier] += float(area[triangle_index])
                elif assignment_routes[key] == 'tier1-generated':
                    feature_direct_wall_area[identifier] += float(area[triangle_index])
                else:
                    feature_composed_wall_area[identifier] += float(area[triangle_index])
            elif roof[triangle_index]:
                feature_roof_area[identifier] += float(area[triangle_index])
                uv = np.column_stack(((position[:,0]*roof_scale+left)/roof_image.width, ((250+position[:,2])*roof_scale+top)/roof_image.height))
                roof_has_evidence = original['extras']['features'][identifier].get('kind') == 'building' and bool(roof_checks.get(str(original['extras']['features'][identifier].get('bag_id')),{}).get('checks',{}).get('passed'))
                if not roof_has_evidence and interpreted_roof_material is None:
                    interpreted_roof_material = add_texture_material(roof_image,'roof-2026-interpreted','roof')
                material, new_uv[triangle_index] = (roof_material if roof_has_evidence else interpreted_roof_material), uv
                feature_generated_area[identifier] += float(area[triangle_index])
                feature_generated_roof_area[identifier] += float(area[triangle_index])
                # Uniform barycentric quadrature; exterior generated padding is interpreted.
                samples = roof_barycentric_samples @ uv
                coordinates = np.minimum(np.maximum((samples*np.array(roof_image.size)).astype(int),0),np.array(roof_image.size)-1)
                interpreted_share = float((roof_mask_array[coordinates[:,1],coordinates[:,0]]>0).mean()) if roof_has_evidence else 1.
                roof_triangle_shares[key] = (identifier, float(area[triangle_index]), 1-interpreted_share, interpreted_share)
                route_areas['roof-asset'] += float(area[triangle_index])
            else:
                material = fallback_wall_material(identifier, primitive)
                horizontal_axis = 0 if np.ptp(position[:,0]) >= np.ptp(position[:,2]) else 2
                new_uv[triangle_index] = np.column_stack((position[:,horizontal_axis]/3.2, -position[:,1]/3.2))
                feature_generated_area[identifier] += float(area[triangle_index])
                feature_composed_wall_area[identifier] += float(area[triangle_index])
                route_areas['tier2-material-fallback'] += float(area[triangle_index])
                wall_triangle_shares[key] = (0.,1.)
                if identifier not in fallback_wall_records:
                    record = {'wall_id': f'uncovered-feature:{identifier}', 'route': 'tier2-material-fallback', 'area_m2': 0., 'triangle_keys': [], 'evidence': [], 'evidence_fraction': 0., 'verified_fraction': 0., 'occluded_fraction': 1., 'interpreted': True, 'provenance': {'method': 'same-building-measured-colour-generated-parts', 'material': material}}
                    feature_walls[identifier].append(record)
                    fallback_wall_records[identifier] = record
                fallback_wall_records[identifier]['triangle_keys'].append(key)

            buckets[material].append(triangle_index)
        source_triangle_count += len(positions)
        attributes['TEXCOORD_0'] = new_uv.reshape(-1, 2)
        for material, triangle_indices in buckets.items():
            vertex_indices = (np.asarray(triangle_indices)[:, None] * 3 + np.arange(3)).ravel()
            result = {key: deepcopy(value) for key, value in primitive.items() if key not in ('attributes', 'material')}
            result.update(attributes={}, material=int(material))
            for name, values in attributes.items():
                original_accessor = original['accessors'][primitive['attributes'][name]]
                result['attributes'][name] = writer.attribute(values[vertex_indices], original_accessor)
            output_primitives.append(result)
    document['meshes'][0]['primitives'] = output_primitives
    now = datetime.now(timezone.utc).isoformat()
    feature_provenance_path = target.with_name(target.stem+'.feature-provenance.json')
    full_feature_provenance = {}
    for feature_index, feature in enumerate(document['extras']['features']):
        walls = feature_walls[feature_index]
        reused_walls = feature_reused_walls[feature_index]
        for wall in walls + reused_walls:
            selected_keys = wall.pop('triangle_keys')
            wall['area_m2'] = sum(triangle_areas[key] for key in selected_keys)
            if wall['area_m2']:
                wall['verified_fraction'] = sum(triangle_areas[key]*wall_triangle_shares[key][0] for key in selected_keys)/wall['area_m2']
                wall['occluded_fraction'] = sum(triangle_areas[key]*wall_triangle_shares[key][1] for key in selected_keys)/wall['area_m2']
                wall['interpretation_share_basis'] = 'Assigned triangle area weighted 48-step barycentric samples of delivery interpretation mask'

        wall_area = sum(wall['area_m2'] for wall in walls + reused_walls)
        evidence_area = sum(w['area_m2'] * w.get('evidence_fraction', 0) for w in walls)
        verified_area = sum(w['area_m2'] * w.get('verified_fraction', 0) for w in walls)
        interpreted_area = sum(w['area_m2'] * w.get('occluded_fraction', 1) for w in walls + reused_walls)
        failed_area = sum(w['area_m2'] * w.get('failed_evidence_fraction', 0) for w in walls)
        feature['asset'] = {
            'provenance': {'method': 'tier1-generated-tier2-drawn-parts-v3', 'assembled_at': now,
                           'source': str(source), 'source_sha256': hashlib.sha256(source_bytes).hexdigest(),
                           'evidence': sorted(set(evidence for wall in walls for evidence in wall['evidence']))
                                       + ([str(ROOT / 'scene/v1/tiles' / tile / 'ortho.jpg')]
                                          if feature_generated_roof_area[feature_index] else []),
                           'generations': list({wall['generation']['id']:wall['generation'] for wall in walls if 'generation' in wall}.values()),
                           'composition': str(composition_path) if any(w['route'] == 'tier2-composed' for w in walls) else None,
                           'roof_generation': str(roof_generation_path) if feature_generated_roof_area[feature_index] else None,
                           'reuse_plan': str(reuse_plan_path) if reused_walls else None,
                           'model_reporting': 'Tool model and version are retained as reported; null means not reported.'},
            'semantic_verified_fraction': 0.,
            'all_components_verified': False,
            'asset_share': feature_generated_area[feature_index] / feature_area[feature_index] if feature_area[feature_index] else 0,
            'generated_share': (feature_direct_wall_area[feature_index]+feature_generated_roof_area[feature_index]) / feature_area[feature_index] if feature_area[feature_index] else 0,
            'wall_generated_area_m2': feature_direct_wall_area[feature_index],
            'wall_composed_area_m2': feature_composed_wall_area[feature_index],
            'wall_reused_area_m2': feature_reused_wall_area[feature_index],
            'wall_textured_area_m2': wall_area,
            'area_routes_m2': {'model_walls': feature_direct_wall_area[feature_index],
                               'composed_walls': feature_composed_wall_area[feature_index],
                               'reused_walls': feature_reused_wall_area[feature_index],
                               'generated_roofs': feature_generated_roof_area[feature_index],
                               'retained_original': 0.},
            'wall_evidence_share': evidence_area / wall_area if wall_area else None,
            'verified_share': verified_area / wall_area if wall_area else None,
            'interpreted_share': interpreted_area / wall_area if wall_area else None,
            'failed_evidence_share': failed_area / wall_area if wall_area else None,
            'wall_routes': dict(Counter(w['route'] for w in walls)),
            'share_basis': 'Assigned wall triangle area. Source evidence, machine verification, failed evidence and occluded interpretation are separate. Delivered verification/interpretation shares sample actual assigned triangle mask regions. Unscreened and synthetic parts are interpreted; no source photograph surface is retained.',
            'check_numbers': {'walls': [compact_wall_record(wall) for wall in walls], 'reused_walls': reused_walls, 'roof': roof_checks.get(str(feature.get('bag_id')), {})},
            'roof_generated_area_m2': feature_generated_roof_area[feature_index],
            'roof_retained_area_m2': feature_roof_area[feature_index] - feature_generated_roof_area[feature_index]}
        full_feature_provenance[str(feature_index)] = deepcopy(feature['asset'])
        feature['asset']['provenance']['evidence_count'] = len(feature['asset']['provenance'].pop('evidence'))
        feature['asset']['provenance']['evidence_record'] = {'path':str(feature_provenance_path),'feature_index':feature_index}
        feature['asset']['check_numbers'] = {'record':str(feature_provenance_path), 'feature_index':feature_index, 'wall_records':len(walls), 'roof_checks':roof_checks.get(str(feature.get('bag_id')),{}).get('checks',{})}
    feature_provenance_bytes = (json.dumps({'written_by':'AI, GPT-6 Astra, 2026-10-26','tile':tile,'features':full_feature_provenance},indent=2)+'\n').encode()
    document['extras']['asset_provenance'] = {'record':str(feature_provenance_path),'sha256':hashlib.sha256(feature_provenance_bytes).hexdigest()}
    writer.binary = remove_unused_resources(document, writer.binary)
    if any(not material.get('extras',{}).get('asset') for material in document['materials']):
        raise ValueError('Original material remains: source photograph fallback is forbidden')
    active_image_names={item.get('name') for item in document['images']}
    texture_statistics=[record for record in texture_statistics if record.get('name') in active_image_names]
    document['buffers'][0]['byteLength'] = len(writer.binary)
    json_bytes = json.dumps(document, separators=(',', ':'), allow_nan=False).encode()
    json_bytes += b' ' * (-len(json_bytes) % 4)
    binary_bytes = bytes(writer.binary) + b'\x00' * (-len(writer.binary) % 4)
    output = struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(json_bytes) + 8 + len(binary_bytes))
    output += struct.pack('<II', len(json_bytes), 0x4E4F534A) + json_bytes
    output += struct.pack('<II', len(binary_bytes), 0x004E4942) + binary_bytes
    serialized_document, serialized_binary = unpack_glb(output)
    if geometry_triangles(original, binary) != geometry_triangles(serialized_document, serialized_binary):
        raise ValueError('Serialized output changed the source triangle geometry or feature IDs')
    retained_features = [{key: value for key, value in feature.items() if key != 'asset'}
                         for feature in serialized_document['extras']['features']]
    if retained_features != original['extras']['features']:
        raise ValueError('Serialized output changed the source feature metadata')
    if composition_path.read_bytes() != composition_bytes:
        raise ValueError('Composition changed during assembly; rerun after compose.py finishes')
    target.parent.mkdir(parents=True, exist_ok=True)
    pending_target=target.with_name('.'+target.name+'.pending')
    feature_provenance_path.write_bytes(feature_provenance_bytes)
    pending_target.write_bytes(output)
    pending_target.replace(target)
    wall_records = [wall for walls in feature_walls.values() for wall in walls]
    wall_total = sum(w['area_m2'] for w in wall_records)
    wall_verified = sum(w['area_m2']*w.get('verified_fraction',0) for w in wall_records)
    wall_interpreted = sum(w['area_m2']*w.get('occluded_fraction',1) for w in wall_records)
    roof_total = sum(record[1] for record in roof_triangle_shares.values())
    roof_verified = sum(record[1]*record[2] for record in roof_triangle_shares.values())
    roof_interpreted = sum(record[1]*record[3] for record in roof_triangle_shares.values())
    building_roof_total = sum(record[1] for record in roof_triangle_shares.values() if original['extras']['features'][record[0]].get('kind') == 'building')
    building_roof_verified = sum(record[1]*record[2] for record in roof_triangle_shares.values() if original['extras']['features'][record[0]].get('kind') == 'building')
    tint_report = None
    if provenance_tint:
        tint_report = write_provenance_tint(document, writer.binary, interpreted_texture_masks, target.with_name('buildings-provenance.glb'))
    report = {'written_by': 'AI, GPT-6 Astra, 2026-10-26', 'date': now, 'tile': tile,
              'original_materials': 0,
              'delivery_budget': {'target_bytes': 25_000_000, 'within_budget': len(output) < 25_000_000, 'policy': 'Preserve source detail; report oversized tiles without downsampling'},
              'wall_area_fractions': {'basis': 'Assigned triangle area weighted 48-step barycentric mask samples; numeric verification only', 'area_m2': wall_total, 'verified': wall_verified/wall_total, 'interpreted': wall_interpreted/wall_total, 'verified_area_m2': wall_verified, 'interpreted_area_m2': wall_interpreted},
              'building_roof_area_fractions': {'area_m2':building_roof_total,'verified':building_roof_verified/building_roof_total,'interpreted':1-building_roof_verified/building_roof_total,'verified_area_m2':building_roof_verified,'interpreted_area_m2':building_roof_total-building_roof_verified},
              'roof_area_fractions': {'scope':'All upward asset surfaces including bridge deck', 'area_m2': roof_total, 'verified': roof_verified/roof_total, 'interpreted': roof_interpreted/roof_total, 'verified_area_m2': roof_verified, 'interpreted_area_m2': roof_interpreted, 'basis': 'Triangle area weighted 48-step barycentric mask sampling; all exterior padding interpreted'},
              'provenance_tint': tint_report,
              'path': str(target), 'bytes': len(output), 'sha256': hashlib.sha256(output).hexdigest(),
              'features': len(document['extras']['features']), 'triangles': source_triangle_count,
              'asset_wall_triangles': len(wall_triangle_shares),
              'composed_fallback_wall_triangles': len(wall_triangle_shares)-len(assignments),
              'generated_wall_triangles': sum(route=='tier1-generated' for route in assignment_routes.values()), 'generated_roof_area_m2': sum(feature_generated_roof_area.values()),
              'area_routes_m2': {'model_walls': sum(feature_direct_wall_area.values()),
                                 'composed_walls': sum(feature_composed_wall_area.values()),
                                 'reused_walls': sum(feature_reused_wall_area.values()),
                                 'generated_roofs': sum(feature_generated_roof_area.values()),
                                 'retained_original': 0.},
              'retained_roof_area_m2': sum(feature_roof_area.values()) - sum(feature_generated_roof_area.values()),
              'elevations': len(generations), 'textures': texture_statistics,
              'pending_elevations': pending_elevations, 'rejected_generated_walls': rejected_generated_walls,
              'wall_routes': dict(Counter(w['route'] for walls in feature_walls.values() for w in walls)),
              'wall_route_areas_m2': {key:value for key,value in route_areas.items() if key != 'roof-asset'},
              'composition': str(composition_path) if composition else None,
              'composition_sha256': composition_hash, 'composition_input_fingerprint': composition.get('input_fingerprint'),
              'texture_encoding': {'tier2':'WebP quality 95; photo-free parts atlases retained on disk; no spatial downsampling', 'other':f'WebP quality {quality}'},
              'geometry_verification': 'All source triangles retained once, positions, normals and feature IDs byte-identical; primitive groups reordered.',
              'axes': {'x': f'RD x minus {origin_x}', 'y': 'NAP metres', 'z': f'negative RD y offset from {origin_y}'}}
    target.with_suffix('.assembly.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('path', 'bytes', 'features', 'triangles', 'elevations', 'generated_wall_triangles', 'wall_routes')}))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tile', default=DEFAULT_TILE)
    parser.add_argument('--assets-root', type=Path, default=ROOT / 'assets/v1')
    parser.add_argument('--output', type=Path, help='Default: assets-root/tiles/<tile>/buildings.glb')
    parser.add_argument('--quality', type=int, default=86)
    parser.add_argument('--provenance-tint', action='store_true', help='Also write buildings-provenance.glb with interpreted texels blended 45 percent toward magenta')
    args = parser.parse_args()
    assemble(args.assets_root, args.output, args.quality, args.provenance_tint, args.tile)
