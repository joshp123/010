#!/usr/bin/env -S .devenv/profile/bin/python
"""Written by AI on 2026-10-26 by model GPT-6 Astra.

Read the delivered GLB pair and check geometry, materials and every nonroof tint texel.
Roof embedding and tint have a separate independent audit in roof-output-review.json.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'buildings'))
from build import accessor, unpack_glb
from block import TILES, ROOT


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def triangle_records(document, binary, attributes):
    result = Counter()
    for mesh in document['meshes']:
        for primitive in mesh['primitives']:
            if 'indices' in primitive:
                raise ValueError('Expected delivered nonindexed geometry')
            arrays = [accessor(document, binary, primitive['attributes'][name]) for name in attributes]
            count = len(arrays[0]) // 3
            for parts in zip(*(array.reshape(count, 3, -1) for array in arrays)):
                result[b''.join(part.tobytes() for part in parts)] += 1
    return result


def image_pixels(document, binary, image):
    view = document['bufferViews'][image['bufferView']]
    start = view.get('byteOffset', 0)
    return np.asarray(Image.open(io.BytesIO(binary[start:start + view['byteLength']])).convert('RGB'))


def interpretation_mask(name, size, tile, composition):
    for atlas in composition['atlases']:
        if name == atlas['id']:
            return np.asarray(Image.open(atlas['interpreted_mask']).convert('L').resize(size, Image.Resampling.NEAREST)) > 0
    if name.startswith('tier2-material:'):
        return np.ones(tuple(reversed(size)), dtype=bool)
    directory = ROOT / 'assets/v1/elevations' / name
    reference = json.loads((directory / 'reference.json').read_text())
    if reference['tile'] != tile:
        raise ValueError(f'{name}: wrong tile reference')
    mask = np.array(Image.open(directory / 'interpreted-mask.png').convert('L'))
    ids = np.asarray(Image.open(directory / 'wall-ids.png'))
    checks = json.loads((directory / 'verification.json').read_text())['walls']
    checks = checks.values() if isinstance(checks, dict) else checks
    for check in checks:
        if check.get('checks', {}).get('passed') is not True:
            mask[ids == check.get('mask_value', -1)] = 255
    return np.asarray(Image.fromarray(mask).resize(size, Image.Resampling.NEAREST)) > 0


def audit(tile):
    folder = ROOT / 'assets/v1/tiles' / tile
    normal_path, tint_path = folder / 'buildings.glb', folder / 'buildings-provenance.glb'
    report = json.loads((folder / 'buildings.assembly.json').read_text())
    normal_hash, tint_hash = digest(normal_path), digest(tint_path)
    if normal_hash != report['sha256'] or tint_hash != report['provenance_tint']['sha256']:
        raise ValueError('GLB pair does not match assembly report')
    normal, normal_binary = unpack_glb(normal_path.read_bytes())
    tint, tint_binary = unpack_glb(tint_path.read_bytes())
    source, source_binary = unpack_glb((ROOT / 'scene/v1/tiles' / tile / 'buildings.glb').read_bytes())
    source_attributes = ('POSITION', 'NORMAL', '_FEATURE_ID_0')
    source_records = triangle_records(source, source_binary, source_attributes)
    if source_records != triangle_records(normal, normal_binary, source_attributes):
        raise ValueError('Delivered geometry or feature IDs differ from source')
    paired_attributes = source_attributes + ('TEXCOORD_0',)
    if triangle_records(normal, normal_binary, paired_attributes) != triangle_records(tint, tint_binary, paired_attributes):
        raise ValueError('Tinted delivery changed geometry or UVs')
    if normal['extras']['features'] != tint['extras']['features']:
        raise ValueError('Tinted delivery changed feature metadata')
    if normal['materials'] != tint['materials']:
        raise ValueError('Tinted delivery changed materials')
    original_materials = sum(material.get('extras', {}).get('asset') is not True for material in normal['materials'])
    if original_materials or report['area_routes_m2']['retained_original'] != 0:
        raise ValueError('Original material or area remains')
    features = [{key: value for key, value in feature.items() if key != 'asset'} for feature in normal['extras']['features']]
    if features != source['extras']['features']:
        raise ValueError('Source feature metadata changed')
    for name in ('wall_area_fractions', 'roof_area_fractions', 'building_roof_area_fractions'):
        if abs(report[name]['verified'] + report[name]['interpreted'] - 1) > 1e-7:
            raise ValueError(f'{name} fractions do not sum to one')
    images = {image['name']: image for image in normal['images']}
    tinted_images = {image['name']: image for image in tint['images']}
    if len(images) != len(normal['images']) or images.keys() != tinted_images.keys():
        raise ValueError('GLB image identities changed')
    composition = json.loads((folder / 'composed/composition.json').read_text())
    interpreted_texels = evidence_texels = checked_images = 0
    roof_images = []
    for name, image in images.items():
        if name.startswith('roof-2026'):
            roof_images.append(name)
            continue
        pixels = image_pixels(normal, normal_binary, image)
        actual = image_pixels(tint, tint_binary, tinted_images[name])
        if pixels.shape != actual.shape:
            raise ValueError(f'{name}: image grid changed')
        mask = interpretation_mask(name, (pixels.shape[1], pixels.shape[0]), tile, composition)
        expected = pixels.copy()
        expected[mask] = np.rint(pixels[mask] * .55 + np.array([255, 0, 255]) * .45).astype(np.uint8)
        if not np.array_equal(actual, expected):
            raise ValueError(f'{name}: {int(np.any(actual != expected, axis=2).sum())} incorrect tint pixels')
        interpreted_texels += int(mask.sum())
        evidence_texels += int((~mask).sum())
        checked_images += 1
    result = {'written_by': 'AI, GPT-6 Astra, 2026-10-26', 'date': datetime.now(timezone.utc).isoformat(),
              'tile': tile, 'glb_sha256': normal_hash, 'provenance_glb_sha256': tint_hash,
              'triangles_preserved': sum(source_records.values()), 'features_preserved': len(features),
              'asset_materials': len(normal['materials']), 'original_materials': original_materials,
              'nonroof_images_checked': checked_images, 'interpreted_texels_exact_blend': interpreted_texels,
              'evidence_texels_unchanged': evidence_texels, 'pixel_mismatches': 0,
              'roof_images_checked_separately': roof_images,
              'note': 'Numerical delivery audit, not semantic certification of architectural components.'}
    path = folder / 'buildings.output-audit.json'
    path.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument('--tile')
    scope.add_argument('--block', choices=['delfshaven'])
    args = parser.parse_args()
    results = [audit(tile) for tile in ([args.tile] if args.tile else TILES)]
    if args.block:
        (ROOT / 'assets/v1/blocks/delfshaven/buildings.output-audit.json').write_text(json.dumps(results, indent=2) + '\n')
