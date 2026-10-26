#!/usr/bin/env -S .devenv/profile/bin/python
"""Written by AI on 2026-10-26 by model GPT-6 Astra.

Incremental source-masked elevation verification. Generator raw images and metadata
are read-only. Missing source assessment is interpreted, never verified.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_dilation, binary_erosion
from skimage.color import rgb2lab, rgb2gray, deltaE_ciede2000
from skimage.filters import sobel

ROOT = Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
CONFIG = Path(__file__).with_name('verification-config.json')
VERSION = 'source-visible-derived-verification-v3'


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, value):
    temporary = path.with_name('.' + path.name + '.pending')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def save_image(path, value):
    temporary = path.with_name('.' + path.name + '.pending.png')
    Image.fromarray(value).save(temporary)
    temporary.replace(path)


def source_facts(tile, bags):
    """Read only facts whose retained reference still matches perception input."""
    sources, inputs = {}, {}
    folder = ROOT / 'facts/v1/work' / tile / 'walls-v2'
    for bag in sorted(bags):
        for path in sorted(folder.glob(bag + '_*/perception.json')):
            try:
                fact = json.loads(path.read_text())
                reference = path.parent / 'reference.png'
                mask = path.parent / 'evidence-mask.png'
                recorded = fact.get('provenance', {}).get('reference_hashes', {}).get(str(reference))
                for item in [path, reference, mask]:
                    inputs[str(item)] = sha256(item)
                if not recorded or recorded != inputs[str(reference)]:
                    continue
                visible = np.asarray(Image.open(mask).convert('L')) > 0
                if visible.shape != tuple(reversed(fact['image_size_px'])):
                    continue
                window = np.zeros_like(visible)
                for opening in fact.get('openings', []):
                    if opening.get('kind') != 'window' or opening.get('partial'):
                        continue
                    x0, y0, x1, y1 = opening['box_px']
                    window[y0:y1, x0] = True
                    window[y0:y1, x1-1] = True
                    window[y0, x0:x1] = True
                    window[y1-1, x0:x1] = True
                # Shared triangle identity, not BAG footprint overlap, establishes mapping.
                for triangle in fact.get('triangles', []):
                    key = (bag, triangle['primitive_index'], triangle['triangle_index'])
                    sources[key] = (np.asarray(triangle['pixel_vertices'], float), visible, window)
            except (OSError, ValueError, KeyError, IndexError):
                # A partially rewritten fact is absent evidence until the next invocation.
                continue
    return sources, inputs


def project_sources(sidecar, shape, sources):
    evidence = np.zeros(shape, bool)
    windows = np.zeros(shape, bool)
    for wall in sidecar['walls']:
        for triangle in wall['triangles']:
            key = (wall['bag_id'], triangle['primitive_index'], triangle['triangle_index'])
            source = sources.get(key)
            if source is None:
                continue
            source_points, visible, boundary = source
            target = np.asarray(triangle['pixel_vertices'], float)
            matrix = (target[1:] - target[0]).T
            if abs(np.linalg.det(matrix)) < 1e-8:
                continue
            left, top = np.maximum(np.floor(target.min(axis=0)).astype(int), 0)
            right, bottom = np.minimum(np.ceil(target.max(axis=0)).astype(int)+1, [shape[1], shape[0]])
            if right <= left or bottom <= top:
                continue
            yy, xx = np.mgrid[top:bottom, left:right]
            relative = np.stack((xx+.5-target[0,0], yy+.5-target[0,1]), axis=-1)
            bary = relative @ np.linalg.inv(matrix).T
            inside = (bary[...,0] >= 0) & (bary[...,1] >= 0) & (bary.sum(axis=-1) <= 1)
            coords = source_points[0] + bary @ (source_points[1:]-source_points[0])
            sx, sy = np.floor(coords[...,0]).astype(int), np.floor(coords[...,1]).astype(int)
            inside &= (sx >= 0) & (sy >= 0) & (sx < visible.shape[1]) & (sy < visible.shape[0])
            sx = np.clip(sx, 0, visible.shape[1]-1)
            sy = np.clip(sy, 0, visible.shape[0]-1)
            evidence[top:bottom,left:right] |= inside & visible[sy,sx]
            windows[top:bottom,left:right] |= inside & boundary[sy,sx]
    return evidence, windows


def verify(directory, occlusions_path=None, config_path=CONFIG):
    directory = Path(directory)
    raw_path = directory / 'generated-raw.png'
    reference_path = directory / 'reference.png'
    metadata_path = directory / 'generation.json'
    # Load/validate complete generator-owned inputs before touching derived output.
    raw_hash = sha256(raw_path)
    with Image.open(raw_path) as image:
        image.load()
        raw_image = image.convert('RGB')
    if not metadata_path.exists():
        raise OSError('Generator metadata not ready; retry next invocation')
    generation = json.loads(metadata_path.read_text())
    reference = np.asarray(Image.open(reference_path).convert('RGB'))
    if generation.get('output_sha256') and generation['output_sha256'] != raw_hash:
        raise ValueError('Raw image and generator metadata hashes differ; pending metadata completion')
    if generation.get('reference_sha256') and generation['reference_sha256'] != sha256(reference_path):
        raise ValueError('Generator reference hash differs from current reference; pending generation update')
    height, width = reference.shape[:2]
    sidecar = json.loads((directory / 'reference.json').read_text())
    photo = np.asarray(Image.open(directory / 'photo-mask.png').convert('L')) > 0
    wall_ids = np.asarray(Image.open(directory / 'wall-ids.png'))
    if photo.shape != (height, width) or wall_ids.shape != (height, width):
        raise ValueError('Reference masks are not on the reference grid')
    config = json.loads(config_path.read_text())
    inputs = {str(path): sha256(path) for path in [raw_path, reference_path, directory/'reference.json', directory/'photo-mask.png', directory/'wall-ids.png', config_path, Path(__file__)]}
    if metadata_path.exists():
        inputs[str(metadata_path)] = sha256(metadata_path)
    sources, source_inputs = source_facts(sidecar['tile'], {w['bag_id'] for w in sidecar['walls']})
    inputs.update(source_inputs)
    projected_evidence, window_boundaries = project_sources(sidecar, (height,width), sources)
    occlusions_path = occlusions_path or directory / 'occlusions.json'
    regions = []
    if occlusions_path.exists():
        assessment = json.loads(occlusions_path.read_text())
        inputs[str(occlusions_path)] = sha256(occlusions_path)
        if assessment.get('reference_sha256') != inputs[str(reference_path)]:
            raise ValueError('Occlusion assessment reference hash is stale; pending source reassessment')
        occlusion_image = Image.new('1', (width,height))
        painter = ImageDraw.Draw(occlusion_image)
        regions = assessment['regions']
        for region in regions:
            painter.polygon([tuple(point) for point in region['polygon_px']], fill=1)
        occluded = np.asarray(occlusion_image, dtype=bool)
        evidence = photo & ~occluded & (wall_ids > 0)
        mask_method = 'source-photo-map-minus-hash-matched-source-occlusion-annotations'
    else:
        evidence = photo & projected_evidence & (wall_ids > 0)
        mask_method = 'hash-matched-C3-source-evidence-mask-projected-through-shared-triangles; unassessed-interpreted'
    interpreted = (wall_ids > 0) & ~evidence
    # Existing reviewed registration is applicable only to the exact retained raw.
    alignment = {'method':'full-image-resize','raw_sha256':raw_hash,'output_size_px':[width,height], 'note':'No reviewed crop available; full output mapped to reference, comparison can fail.'}
    image = raw_image
    registration = generation.get('registration') or {}
    if generation.get('output_sha256') == raw_hash and registration.get('crop_px'):
        crop = registration['crop_px']
        if len(crop) != 4 or not (0 <= crop[0] < crop[2] <= image.width and 0 <= crop[1] < crop[3] <= image.height):
            raise ValueError('Recorded alignment crop is outside raw image')
        image = image.crop(crop)
        alignment = dict(registration, raw_sha256=raw_hash, output_size_px=[width,height])
    elif generation.get('output_sha256') == raw_hash and generation.get('texture_path'):
        existing = Path(generation['texture_path'])
        if existing.exists() and existing.name != 'generated-aligned.png':
            inputs[str(existing)] = sha256(existing)
            image = Image.open(existing).convert('RGB')
            alignment = {'method':'preserved-recorded-texture','path':str(existing),'sha256':inputs[str(existing)],'raw_sha256':raw_hash,'output_size_px':[width,height]}
        elif existing.exists() and existing.name == 'generated-aligned.png':
            # A reviewed existing aligned file with no reproducible crop is an input,
            # retained via a private derived snapshot for stable incremental reruns.
            snapshot = directory / ('alignment-source-' + raw_hash[:16] + '.png')
            if not snapshot.exists():
                save_image(snapshot, np.asarray(Image.open(existing).convert('RGB')))
            inputs[str(snapshot)] = sha256(snapshot)
            image = Image.open(snapshot).convert('RGB')
            alignment = {'method':'preserved-reviewed-alignment-source','path':str(snapshot),'sha256':inputs[str(snapshot)],'raw_sha256':raw_hash,'output_size_px':[width,height]}
    fingerprint = hashlib.sha256(json.dumps({'version':VERSION,'inputs':inputs,'alignment':alignment}, sort_keys=True).encode()).hexdigest()
    output_path = directory / 'generated-aligned.png'
    verification_path = directory / 'verification.json'
    if verification_path.exists():
        previous = json.loads(verification_path.read_text())
        outputs = previous.get('derived_hashes', {})
        if previous.get('input_fingerprint') == fingerprint and outputs and all(Path(path).exists() and sha256(path) == digest for path,digest in outputs.items()):
            return {'status':'cached','directory':str(directory),'aggregate':previous['aggregate']}
    generated_image = image.resize((width,height), Image.Resampling.LANCZOS)
    generated = np.asarray(generated_image)
    photo_edges = sobel(rgb2gray(reference)) >= config['sobel_threshold']
    output_edges = sobel(rgb2gray(generated)) >= config['sobel_threshold']
    tolerance = config['edge_tolerance_px']
    yy,xx = np.mgrid[-tolerance:tolerance+1,-tolerance:tolerance+1]
    nearby = binary_dilation(output_edges, structure=xx**2+yy**2 <= tolerance**2)
    differences = deltaE_ciede2000(rgb2lab(reference), rgb2lab(generated))
    records = []
    for wall in sidecar['walls']:
        geometry = wall_ids == wall['mask_value']
        visible = geometry & evidence
        eroded = binary_erosion(visible, iterations=config['mask_boundary_erosion_px'])
        edges = photo_edges & eroded
        windows = window_boundaries & eroded
        visible_count, geometry_count, edge_count = int(visible.sum()),int(geometry.sum()),int(edges.sum())
        agreement = float((edges & nearby).sum()/edge_count) if edge_count else None
        window_count = int(windows.sum())
        window_agreement = float((windows & nearby).sum()/window_count) if window_count else None
        colour = float(differences[visible].mean()) if visible_count else None
        enough = visible_count >= config['minimum_evidence_pixels'] and edge_count > 0
        passed = bool(agreement >= config['edge_agreement_min'] and colour <= config['mean_ciede2000_max'] and (window_agreement is None or window_agreement >= config['edge_agreement_min'])) if enough else None
        records.append({'wall_id':wall['wall_id'],'bag_id':wall['bag_id'],'mask_value':wall['mask_value'],'geometry_pixels':geometry_count,'evidence_pixels':visible_count,'interpreted_pixels':geometry_count-visible_count,'evidence_share':visible_count/geometry_count if geometry_count else 0,'verified_share':visible_count/geometry_count if geometry_count and passed else 0,'interpreted_share':1-visible_count/geometry_count if geometry_count else 1,'failed_evidence_share':visible_count/geometry_count if geometry_count and passed is False else 0,'checks':{'edge_agreement':agreement,'window_edge_agreement':window_agreement,'window_boundary_pixels':window_count,'mean_ciede2000':colour,'photo_edge_pixels':edge_count,'status':'pass' if passed else 'fail' if enough else 'insufficient-evidence','passed':passed},'interpreted_regions':{'raster_mask':str(directory/'interpreted-mask.png'),'wall_ids_mask':str(directory/'wall-ids.png'),'wall_mask_value':wall['mask_value']}})
    total_edges = sum(r['checks']['photo_edge_pixels'] for r in records)
    aggregate = {'edge_agreement':sum((r['checks']['edge_agreement'] or 0)*r['checks']['photo_edge_pixels'] for r in records)/total_edges if total_edges else None,'mean_ciede2000':float(differences[evidence].mean()) if evidence.any() else None,'walls_passed':sum(r['checks']['passed'] is True for r in records),'walls_checked':sum(r['checks']['passed'] is not None for r in records),'walls_interpreted_only':sum(r['evidence_pixels']==0 for r in records),'walls_insufficient_evidence':sum(r['checks']['passed'] is None for r in records),'evidence_pixels':int(evidence.sum()),'interpreted_pixels':int(interpreted.sum())}
    # Inputs can change while Claude writes. Never publish outputs for a mixed snapshot.
    if any(not Path(path).exists() or sha256(path) != digest for path,digest in inputs.items()):
        return {'status':'pending','directory':str(directory),'reason':'Input changed while verification ran; retry next invocation'}
    save_image(output_path, generated)
    save_image(directory/'evidence-mask.png', evidence.astype(np.uint8)*255)
    save_image(directory/'interpreted-mask.png', interpreted.astype(np.uint8)*255)
    masks = {'written_by':'AI, GPT-6 Astra, 2026-10-26','method':mask_method,'reference_sha256':inputs[str(reference_path)],'evidence_mask':str(directory/'evidence-mask.png'),'interpreted_mask':str(directory/'interpreted-mask.png'),'wall_ids_mask':str(directory/'wall-ids.png'),'regions':regions,'pixel_scale_m':sidecar['pixel_size_m']}
    save_json(directory/'masks.json',masks)
    verification = {'written_by':'AI, GPT-6 Astra, 2026-10-26','version':VERSION,'date':datetime.now(timezone.utc).isoformat(),'input_fingerprint':fingerprint,'inputs':inputs,'raw_sha256':raw_hash,'reference_sha256':inputs[str(reference_path)],'compared_texture':str(output_path),'compared_texture_sha256':sha256(output_path),'alignment':alignment,'status':'checked-with-failures-or-insufficient-evidence' if any(r['checks']['passed'] is not True for r in records) else 'screen-passed-with-interpretation' if interpreted.any() else 'screen-passed','method':'source-visible-nearby-sobel-edge-and-CIEDE2000','thresholds':config,'evidence_masks':str(directory/'masks.json'),'source_only_mask':True,'evidence_limit':'Photo mapping alone never establishes visibility. Occlusions/unassessed regions are interpreted. Window checks use only projected C3 window boundaries; null means no assessed window support. Numerical screens do not certify every component or semantic completeness.','walls':records,'aggregate':aggregate}
    geometry_count = int((wall_ids>0).sum())
    provenance = {'written_by':'AI, GPT-6 Astra, 2026-10-26','model':generation.get('model'),'model_version':generation.get('model_version'),'date':generation.get('ended_at') or generation.get('date'),'prompt_sha256':generation.get('prompt_sha256'),'prompt_source':generation.get('prompt_source'),'generation_metadata_sha256':inputs[str(metadata_path)],'reference_hashes':{str(reference_path):inputs[str(reference_path)],str(directory/'reference.json'):inputs[str(directory/'reference.json')]},'raw_sha256':raw_hash,'generation_record':str(metadata_path),'verification_record':str(verification_path),'asset':str(output_path),'verified_fraction':sum(r['geometry_pixels']*r['verified_share'] for r in records)/geometry_count if geometry_count else 0,'verified_fraction_scope':'Numerical source-visible edge/colour/window-boundary screen only','semantic_verified_fraction':0,'occluded_fraction':int(interpreted.sum())/geometry_count if geometry_count else 1,'interpreted_fraction':int(interpreted.sum())/geometry_count if geometry_count else 1,'interpreted_regions':str(directory/'masks.json'),'all_components_verified':False,'walls':records}
    save_json(directory/'provenance.json',provenance)
    verification['derived_hashes'] = {str(path):sha256(path) for path in [output_path,directory/'evidence-mask.png',directory/'interpreted-mask.png',directory/'masks.json',directory/'provenance.json']}
    save_json(verification_path,verification)
    return {'status':'processed','directory':str(directory),'aggregate':aggregate}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--elevation',type=Path)
    group.add_argument('--tile')
    parser.add_argument('--occlusions',type=Path)
    parser.add_argument('--config',type=Path,default=CONFIG)
    args=parser.parse_args()
    directories=[args.elevation] if args.elevation else sorted((ROOT/'assets/v1/elevations').iterdir())
    results=[]
    for directory in directories:
        if not (directory/'generated-raw.png').exists():
            continue
        try:
            if args.tile and json.loads((directory/'reference.json').read_text())['tile'] != args.tile:
                continue
            result=verify(directory,args.occlusions,args.config)
        except (OSError,ValueError,KeyError,IndexError) as error:
            result={'status':'pending','directory':str(directory),'reason':str(error)}
        results.append(result)
        print(json.dumps(result,allow_nan=False),flush=True)
    print(json.dumps({'tile':args.tile,'elevations':len(results),'processed':sum(r['status']=='processed' for r in results),'cached':sum(r['status']=='cached' for r in results),'pending':sum(r['status']=='pending' for r in results),'walls_passed':sum(r.get('aggregate',{}).get('walls_passed',0) for r in results),'walls_checked':sum(r.get('aggregate',{}).get('walls_checked',0) for r in results),'walls_interpreted_only':sum(r.get('aggregate',{}).get('walls_interpreted_only',0) for r in results)},allow_nan=False),flush=True)


if __name__=='__main__':
    main()
