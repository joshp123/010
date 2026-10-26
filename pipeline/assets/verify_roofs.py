"""Written by AI on 2026-10-26 by model GPT-6 Astra.

Compare generated roof material with aerial evidence per BAG feature.
Roof polygons come from the retained source mesh, intersected with class 11.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw
from skimage.color import rgb2lab, deltaE_ciede2000

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'buildings'))
from build import accessor, unpack_glb

ROOT = Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
TILE = 'x90250_y436000'
CONFIG = Path(__file__).with_name('verification-config.json')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(directory, config_path=CONFIG):
    tile = ROOT / 'scene/v1/tiles' / TILE
    source_path = tile / 'ortho.jpg'
    source = np.asarray(Image.open(source_path).convert('RGB'))
    generated = np.asarray(Image.open(directory / 'roof.webp').convert('RGB'))
    if source.shape != generated.shape:
        raise ValueError('Roof output pixel grid does not match source aerial')
    height, width = source.shape[:2]
    classes = np.asarray(Image.open(tile / 'classes.png'))[..., 0]
    config = json.loads(config_path.read_text())
    annotation_path = directory / 'occlusions.json'
    annotation = json.loads(annotation_path.read_text())
    if annotation['reference_sha256'] != digest(source_path):
        raise ValueError('Roof occlusion assessment belongs to a different aerial')
    occlusion_image = Image.new('1', (width, height))
    painter = ImageDraw.Draw(occlusion_image)
    for region in annotation['regions']:
        painter.polygon([tuple(point) for point in region['polygon_px']], fill=1)
    occlusion = np.asarray(occlusion_image, dtype=bool)
    document, binary = unpack_glb((tile / 'buildings.glb').read_bytes())
    features = document['extras']['features']
    triangles = {}
    geometry_areas = {}
    for primitive in document['meshes'][0]['primitives']:
        attributes = primitive['attributes']
        positions = accessor(document, binary, attributes['POSITION']).reshape(-1, 3, 3).astype(float)
        identifiers = accessor(document, binary, attributes['_FEATURE_ID_0']).reshape(-1, 3)[:, 0].astype(int)
        cross = np.cross(positions[:, 1] - positions[:, 0], positions[:, 2] - positions[:, 0])
        lengths = np.linalg.norm(cross, axis=1)
        normals_y = cross[:, 1] / np.maximum(lengths, 1e-20)
        for index in np.flatnonzero((normals_y > .2) & (lengths > .01)):
            feature_index = int(identifiers[index])
            if features[feature_index]['kind'] != 'building':
                continue
            local = positions[index]
            projected = np.column_stack((local[:, 0] * 10, (250 + local[:, 2]) * 10))
            triangles.setdefault(feature_index, []).append(projected)
            geometry_areas[feature_index] = geometry_areas.get(feature_index, 0) + float(lengths[index] / 2)
    differences = deltaE_ciede2000(rgb2lab(source), rgb2lab(generated))
    records = {}
    roof_ids = np.zeros((height, width), dtype=np.uint16)
    evidence_union = np.zeros((height, width), dtype=bool)
    for feature_index, feature in enumerate(features):
        if feature['kind'] != 'building':
            continue
        roof_mask_image = Image.new('1', (width, height))
        roof_painter = ImageDraw.Draw(roof_mask_image)
        for triangle in triangles.get(feature_index, []):
            roof_painter.polygon([tuple(point) for point in triangle], fill=1)
        geometry = np.asarray(roof_mask_image, dtype=bool)
        classified = geometry & (classes == 11)
        visible = classified & ~occlusion
        roof_ids[geometry] = feature_index + 1
        evidence_union |= visible
        visible_count = int(visible.sum())
        geometry_count = int(geometry.sum())
        colour = float(differences[visible].mean()) if visible_count else None
        enough = visible_count >= config['minimum_evidence_pixels']
        passed = colour <= config['mean_ciede2000_max'] if enough else None
        records[feature['bag_id']] = {
            'bag_id': feature['bag_id'], 'feature_index': feature_index,
            'geometry_area_m2': geometry_areas.get(feature_index, 0),
            'geometry_pixels_in_tile': geometry_count,
            'classified_building_pixels': int(classified.sum()),
            'evidence_pixels': visible_count,
            'interpreted_pixels': geometry_count - visible_count,
            'source_occlusion_pixels': int((classified & occlusion).sum()),
            'outside_building_class_pixels': int((geometry & (classes != 11)).sum()),
            'evidence_share': visible_count / geometry_count if geometry_count else 0,
            'verified_share': visible_count / geometry_count if geometry_count and passed else 0,
            'interpreted_share': 1 - visible_count / geometry_count if geometry_count else 1,
            'checks': {'mean_ciede2000': colour, 'passed': passed,
                       'status': 'pass' if passed else 'fail' if enough else 'insufficient-evidence'},
            'mean_ciede2000': colour, 'passed': passed,
            'evidence': [str(source_path), str(tile / 'classes.png'), str(tile / 'buildings.glb')],
            'regions': {'roof_ids_mask': str(directory / 'roof-ids.png'), 'mask_value': feature_index+1,
                        'evidence_mask': str(directory / 'evidence-mask.png'),
                        'interpreted_mask': str(directory / 'interpreted-mask.png')},
        }
    Image.fromarray(roof_ids).save(directory / 'roof-ids.png')
    Image.fromarray(evidence_union.astype(np.uint8) * 255).save(directory / 'evidence-mask.png')
    Image.fromarray(((roof_ids > 0) & ~evidence_union).astype(np.uint8) * 255).save(directory / 'interpreted-mask.png')
    generation_path = directory / 'generation.json'
    generation = json.loads(generation_path.read_text()) if generation_path.exists() else {
        'written_by': 'AI, GPT-6 Astra, 2026-10-26',
        'quadrants': [json.loads((directory / quadrant / 'generation.json').read_text()) for quadrant in ['nw','ne','sw','se']],
    }
    checked = [record for record in records.values() if record['passed'] is not None]
    aggregate = {'mean_ciede2000': float(differences[evidence_union].mean()) if evidence_union.any() else None,
                 'roofs_passed': sum(record['passed'] for record in checked), 'roofs_checked': len(checked),
                 'roofs_insufficient_evidence': len(records)-len(checked),
                 'evidence_pixels': int(evidence_union.sum())}
    generation['verification'] = {
        'method': 'per-feature-upward-source-mesh-projection-intersect-class11-source-occlusion-mask-ciede2000-v1',
        'date': datetime.now(timezone.utc).isoformat(), 'roofs': records, 'aggregate': aggregate,
        'thresholds': config, 'config_sha256': digest(config_path),
        'source_only_occlusion_assessment': str(annotation_path), 'source_sha256': digest(source_path),
        'class_raster_sha256': digest(tile / 'classes.png'),
        'note': 'Classes encode building coverage, not BAG IDs. BAG identity comes from retained mesh feature IDs. Roof pixels outside class 11, aerial frame or source-visible roof evidence cannot be verified. Photograph shadows remain in the comparison; conservative canopy envelopes are excluded.',
    }
    generation['output'] = str(directory / 'roof.webp')
    generation['output_sha256'] = digest(directory / 'roof.webp')
    generation_path.write_text(json.dumps(generation, indent=2, allow_nan=False) + '\n')
    return aggregate


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--roofs', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=CONFIG)
    args = parser.parse_args()
    print(json.dumps(verify(args.roofs, args.config), allow_nan=False))
