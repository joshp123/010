"""Written by AI on 2026-10-26 by model GPT-6 Astra.

Extract source pixel samples and reuse them through an inspectable material plan.
Crop choices live in source-crops.json; this stage never calls a model.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_erosion, label, find_objects, uniform_filter

from assemble import ROOT, TILE, generated_texture_path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'buildings'))
from build import unpack_glb


def source_center(wall):
    return np.asarray(wall['wall_plane_rd_nap']['point'], dtype=float)


def suggested_crops(image, mask, scale):
    pixels = np.asarray(image.convert('RGB'))
    inside = binary_erosion(mask, iterations=3)
    if not inside.any():
        inside = mask
    samples = pixels[inside]
    if not len(samples):
        return None, None
    # Select actual, low-variance wall pixels near the dominant non-dark colour.
    usable = samples[np.mean(samples, axis=1) > 65]
    if not len(usable):
        usable = samples
    quantized = usable // 24
    colours, counts = np.unique(quantized, axis=0, return_counts=True)
    dominant = colours[np.argmax(counts)] * 24 + 12
    patch = max(3, round(.3 / scale))
    candidates = binary_erosion(inside, iterations=max(1, patch // 2))
    if not candidates.any():
        candidates = inside
    local_mean = np.stack([uniform_filter(pixels[:, :, channel].astype(float), size=patch)
                           for channel in range(3)], axis=-1)
    local_variance = np.stack([uniform_filter(pixels[:, :, channel].astype(float) ** 2, size=patch)
                               for channel in range(3)], axis=-1) - local_mean ** 2
    score = np.mean(np.maximum(local_variance, 0), axis=-1) + np.mean((local_mean - dominant) ** 2, axis=-1)
    score[~candidates] = np.inf
    y, x = np.unravel_index(np.argmin(score), score.shape)
    radius = max(1, patch // 2)
    plain = [max(0, int(x) - radius), max(0, int(y) - radius),
             min(image.width, int(x) + radius + 1), min(image.height, int(y) + radius + 1)]
    normalized = pixels / 255.
    # The accepted prompt explicitly draws windows as dark-blue glass panes.
    glass = inside & (normalized.mean(axis=-1) < .43) & (normalized[:, :, 2] > normalized[:, :, 0] * 1.05)
    labels, _ = label(glass)
    components = []
    occupied_y = np.flatnonzero(mask.any(axis=1))
    upper_window_limit = occupied_y[-1] - .2 * (occupied_y[-1] - occupied_y[0])
    for value, region in enumerate(find_objects(labels), 1):
        if region is None:
            continue
        ys, xs = region
        width, height = xs.stop - xs.start, ys.stop - ys.start
        area = int(np.count_nonzero(labels[region] == value))
        if (.25 <= width * scale <= 2.5 and .35 <= height * scale <= 2.5
                and .35 <= width / height <= 2
                and (ys.start + ys.stop) / 2 < upper_window_limit
                and area / (width * height) > .3):
            components.append((area, xs.start, ys.start, xs.stop, ys.stop))
    if not components:
        return plain, None
    _, x0, y0, x1, y1 = max(components)
    frame = max(1, round(.1 / scale))
    window = [max(0, x0-frame), max(0, y0-frame), min(image.width, x1+frame), min(image.height, y1+frame)]
    return plain, window


def references(assets):
    result = []
    for path in sorted((assets / 'elevations').glob('*/reference.json')):
        reference = json.loads(path.read_text())
        generation_file = path.with_name('generation.json')
        generation = json.loads(generation_file.read_text()) if generation_file.exists() else {}
        texture = generated_texture_path(path.parent, generation)
        result.append((path, reference, generation, texture))
    return result


def candidates(assets, overrides_path):
    output = assets / 'tiles' / TILE / 'reuse'
    output.mkdir(parents=True, exist_ok=True)
    overrides = json.loads(overrides_path.read_text()).get('sources', {}) if overrides_path.exists() else {}
    sources = {}
    for reference_path, reference, generation, texture in references(assets):
        if not texture.exists():
            continue
        image = Image.open(texture).convert('RGB').resize(reference['image_size_px'], Image.Resampling.LANCZOS)
        wall_ids = np.asarray(Image.open(reference_path.with_name('wall-ids.png')))
        for wall in reference['walls']:
            if wall['geometry_area_m2'] < 1:
                continue
            plain, window = suggested_crops(image, wall_ids == wall['mask_value'], reference['pixel_size_m'])
            record = {'wall_id': wall['wall_id'], 'bag_id': wall['bag_id'], 'feature_index': wall['feature_index'],
                      'elevation': reference['id'], 'texture': str(texture), 'reference': str(reference_path),
                      'texture_size_px': reference['image_size_px'], 'wall_rectangle_px': wall['rectangle_px'],
                      'pixel_size_m': reference['pixel_size_m'], 'center_rd_nap': source_center(wall).tolist(),
                      'plain_crop_px': plain, 'window_crop_px': window,
                      'crop_method': 'source-pixels-v1: dominant-colour low-variance plain patch; dark-blue connected window component',
                      'crop_review': 'candidate-unreviewed'}
            if wall['wall_id'] in overrides:
                record.update(overrides[wall['wall_id']])
                record['crop_review'] = 'model-authored-override'
            sources[wall['wall_id']] = record
    destination = output / 'source-candidates.json'
    destination.write_text(json.dumps({'written_by': 'AI, GPT-6 Astra, 2026-10-26',
                                      'sources': sources}, indent=2) + '\n')
    records = list(sources.values())
    for page_index in range(0, len(records), 36):
        page_records = records[page_index:page_index+36]
        canvas = Image.new('RGB', (1440, 6 * 190), 'white')
        draw = ImageDraw.Draw(canvas)
        for index, record in enumerate(page_records):
            x, y = index % 6 * 240, index // 6 * 190
            image = Image.open(record['texture']).convert('RGB').resize(record['texture_size_px'], Image.Resampling.LANCZOS)
            crop = image.crop(tuple(map(int, record['wall_rectangle_px'])))
            crop.thumbnail((225, 130))
            canvas.paste(crop, (x, y+25))
            draw.text((x, y), record['wall_id'][-25:], fill='black')
            for key, offset in [('plain_crop_px', 0), ('window_crop_px', 90)]:
                if record[key]:
                    sample = image.crop(record[key]); sample.thumbnail((80, 30))
                    canvas.paste(sample, (x+offset, y+155))
        canvas.save(output / f'source-crops-{page_index//36+1:02d}.jpg', quality=90)
    print(json.dumps({'sources': len(sources), 'candidates': str(destination), 'montage_pages': (len(records)+35)//36}))
    return sources


def select_source(wall, feature, sources, features, max_year_difference):
    center = source_center(wall)
    same = [source for source in sources.values() if source['bag_id'] == wall['bag_id'] and source['plain_crop_px']]
    if same:
        return min(same, key=lambda source: np.linalg.norm(np.asarray(source['center_rd_nap'])[:2]-center[:2])), 'same-building'
    comparable = []
    for source in sources.values():
        other = features[source['feature_index']]
        if not source['plain_crop_px'] or not (set(feature.get('use', [])) & set(other.get('use', []))):
            continue
        if not feature.get('year') or not other.get('year'):
            continue
        if abs(feature['year']-other['year']) <= max_year_difference:
            comparable.append(source)
    if not comparable:
        return None, 'no-similar-generated-source'
    return min(comparable, key=lambda source: np.linalg.norm(np.asarray(source['center_rd_nap'])[:2]-center[:2])), 'similar-year-and-use-neighbour'


def tile_crop(crop, size):
    result = Image.new('RGB', size)
    for top in range(0, size[1], crop.height):
        for left in range(0, size[0], crop.width):
            result.paste(crop, (left, top))
    return result


def build(assets, crops_path, max_year_difference=25):
    source_file = assets / 'tiles' / TILE / 'reuse/source-candidates.json'
    if not source_file.exists():
        sources = candidates(assets, crops_path)
    else:
        sources = json.loads(source_file.read_text())['sources']
        if crops_path.exists():
            for wall_id, override in json.loads(crops_path.read_text()).get('sources', {}).items():
                if wall_id in sources:
                    sources[wall_id].update(override)
                    sources[wall_id]['crop_review'] = 'model-authored-override'
    document, _ = unpack_glb((ROOT / 'scene/v1/tiles' / TILE / 'buildings.glb').read_bytes())
    features = document['extras']['features']
    records, unresolved = [], []
    output = assets / 'tiles' / TILE / 'reuse'
    for reference_path, reference, generation, texture in references(assets):
        if texture.exists():
            continue
        for wall in reference['walls']:
            source, match = select_source(wall, features[wall['feature_index']], sources, features, max_year_difference)
            if source is None:
                unresolved.append({'wall_id': wall['wall_id'], 'area_m2': wall['geometry_area_m2'], 'reason': match})
                continue
            x0, y0, x1, y1 = wall['rectangle_px']
            width, height = max(1, int(np.ceil(x1-x0))), max(1, int(np.ceil(y1-y0)))
            source_image = Image.open(source['texture']).convert('RGB').resize(source['texture_size_px'], Image.Resampling.LANCZOS)
            plain = source_image.crop(source['plain_crop_px'])
            image = tile_crop(plain, (width, height))
            feature = features[wall['feature_index']]
            nominal_storey = 3.2 if (feature.get('year') or 2000) < 1945 else 2.8
            building_height = float(feature.get('height_m') or height * reference['pixel_size_m'])
            storey_m = building_height / max(1, round(building_height / nominal_storey))
            window = source_image.crop(source['window_crop_px']) if source.get('window_crop_px') else None
            spacing_m = max(1.8, window.width * source['pixel_size_m'] * 1.7) if window else None
            if window:
                sample_scale = source['pixel_size_m'] / reference['pixel_size_m']
                window = window.resize((max(1, round(window.width*sample_scale)), max(1, round(window.height*sample_scale))), Image.Resampling.LANCZOS)
                storey_px = storey_m / reference['pixel_size_m']
                spacing_px = spacing_m / reference['pixel_size_m']
                for bottom in np.arange(height-.7/reference['pixel_size_m'], -window.height, -storey_px):
                    for center in np.arange(spacing_px/2, width, spacing_px):
                        image.paste(window, (round(center-window.width/2), round(bottom-window.height)))
            name = wall['wall_id'].replace(':', '_')
            target = output / 'textures' / f'{name}.webp'
            target.parent.mkdir(parents=True, exist_ok=True)
            image.save(target, format='WEBP', quality=86, method=6)
            triangles = []
            for triangle in wall['triangles']:
                triangles.append({'primitive_index': triangle['primitive_index'], 'triangle_index': triangle['triangle_index'],
                                  'uv': ((np.asarray(triangle['pixel_vertices']) - [x0, y0]) / [width, height]).tolist()})
            records.append({'wall_id': wall['wall_id'], 'bag_id': wall['bag_id'], 'feature_index': wall['feature_index'],
                            'area_m2': wall['geometry_area_m2'], 'texture_path': str(target), 'source_wall_id': source['wall_id'],
                            'source_elevation': source['elevation'], 'source_match': match, 'source_crop': source,
                            'interpreted': True, 'verified': False, 'method': 'generated-wall-crop-reuse-v1',
                            'storey_m': storey_m, 'storey_method': 'BAG building height divided by rounded storey estimate; nominal 3.2m before 1945, otherwise 2.8m',
                            'window_spacing_m': spacing_m, 'window_pattern_available': window is not None,
                            'triangles': triangles})
    plan = {'written_by': 'AI, GPT-6 Astra, 2026-10-26', 'date': datetime.now(timezone.utc).isoformat(),
            'method': 'generated-wall-crop-reuse-v1', 'tile': TILE, 'max_year_difference': max_year_difference,
            'source_selection': 'Nearest generated wall in the same BAG building; otherwise nearest intersecting BAG-use category within the configured year difference.',
            'walls': records, 'unresolved': unresolved,
            'coverage_area_m2': sum(record['area_m2'] for record in records),
            'unresolved_area_m2': sum(record['area_m2'] for record in unresolved)}
    destination = output / 'reuse-plan.json'
    destination.write_text(json.dumps(plan, indent=2) + '\n')
    print(json.dumps({'plan': str(destination), 'reused_walls': len(records), 'reused_area_m2': plan['coverage_area_m2'],
                      'unresolved_walls': len(unresolved), 'unresolved_area_m2': plan['unresolved_area_m2']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['candidates', 'build'])
    parser.add_argument('--assets-root', type=Path, default=ROOT / 'assets/v1')
    parser.add_argument('--source-crops', type=Path)
    parser.add_argument('--max-year-difference', type=int, default=25)
    args = parser.parse_args()
    crops = args.source_crops or args.assets_root / 'tiles' / TILE / 'reuse/source-crops.json'
    if args.mode == 'candidates':
        candidates(args.assets_root, crops)
    else:
        build(args.assets_root, crops, args.max_year_difference)
