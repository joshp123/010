#!/usr/bin/env python3
"""Written by AI, gpt-6-astra, 2026-10-24. Replace reviewed container-terminal source branches.
Observed roofs/straight members, inferred hidden walls/bases, illustrative joints. Other branches are copied unchanged.
Requires the project's Nix Python dependencies. Writes a separate staged directory, never mutates the input.
"""
import argparse
import concurrent.futures
import gzip
import hashlib
import json
import shutil
import time
from pathlib import Path
from importlib.machinery import SourceFileLoader
import numpy as np
from scipy.spatial import cKDTree
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks
from industrial_terminal_ground import MeasuredGround
from industrial_terminal_members import fit_members
from industrial_terminal_roofs import reconstruct_roofs
PROJECT_ROOT = Path(__file__).resolve().parents[1]
industrial_builder = SourceFileLoader(
    'industrial_builder',
    str(PROJECT_ROOT / 'scripts/build-industrial-structures.py')
).load_module()
mesh_partition = SourceFileLoader(
    'prepared_partition',
    str(PROJECT_ROOT / 'scripts/subdivide-prepared-meshes.py')
).load_module()

def point_quality(points, cache_directory):
    fingerprint = hashlib.sha256(points.tobytes()).hexdigest()
    quality_path = cache_directory / 'quality.npz'
    quality_record = cache_directory / 'quality-input.json'
    if quality_path.exists() and quality_record.exists() and (json.loads(quality_record.read_text())['pointsSha256'] == fingerprint):
        with np.load(quality_path) as cached_quality:
            return {name: cached_quality[name] for name in cached_quality.files}
    tree = cKDTree(points)
    normal = np.empty((len(points), 3))
    principal = np.empty((len(points), 3))
    eigenvalues = np.empty((len(points), 3))
    for start in range(0, len(points), 50000):
        end = min(start + 50000, len(points))
        _, neighbours = tree.query(points[start:end], k=16, workers=2)
        neighbourhood = points[neighbours]
        neighbourhood -= neighbourhood.mean(axis=1, keepdims=True)
        values, vectors = np.linalg.eigh(np.einsum('nki,nkj->nij', neighbourhood, neighbourhood) / 16)
        normal[start:end] = vectors[:, :, 0]
        principal[start:end] = vectors[:, :, 2]
        eigenvalues[start:end] = values
    np.savez_compressed(quality_path, normal=normal, principal=principal, eigenvalues=eigenvalues)
    quality_record.write_text(json.dumps({'pointsSha256': fingerprint, 'neighbours': 16}))
    return {'normal': normal, 'principal': principal, 'eigenvalues': eigenvalues}

def row_orientation(points, quality, source_config, rails):
    horizontal_surface = (
        (abs(quality['normal'][:, 2]) > 0.85)
        & (quality['eigenvalues'][:, 0] < 0.25)
        & (points[:, 2] > 6)
        & (points[:, 2] < 25)
    )
    if horizontal_surface.sum() < 100:
        return None
    horizontal_positions = points[horizontal_surface, :2] - source_config['displayOriginRD'][:2]
    rail_angle, rail_ids = industrial_builder.terminal_orientation(rails, source_config['boundsRD_NAP'])
    rail_degrees = float(np.degrees(rail_angle))

    def score(angle_degrees):
        angle = np.radians(angle_degrees)
        across = horizontal_positions @ np.array([-np.sin(angle), np.cos(angle)])
        counts, edges = np.histogram(across, bins=np.arange(np.floor(across.min()), across.max() + 0.5, 0.25))
        smoothed_counts = gaussian_filter1d(counts.astype(float), 1)
        frequencies = np.fft.rfftfreq(len(smoothed_counts), d=0.25)
        power = abs(np.fft.rfft(smoothed_counts - smoothed_counts.mean())) ** 2
        selected_frequencies = (frequencies > 1 / 4) & (frequencies < 1 / 1.7)
        if not selected_frequencies.any():
            return {'angleDegrees': float(angle_degrees), 'repeatedBandPower': 0, 'consecutiveRowWidthGaps': 0}
        peaks, _ = find_peaks(smoothed_counts, distance=7, prominence=25)
        peaks = peaks[smoothed_counts[peaks] >= 40]
        gaps = np.diff(edges[peaks] + 0.125)
        credible_row_gaps = (gaps > 1.7) & (gaps < 4)
        return {
            'angleDegrees': float(angle_degrees),
            'repeatedBandPower': float(power[selected_frequencies].max() / len(horizontal_positions) ** 2),
            'detectedPeaks': len(peaks),
            'consecutiveRowWidthGaps': int(credible_row_gaps.sum()),
            'medianRowPitchMetres': float(np.median(gaps[credible_row_gaps])) if credible_row_gaps.any() else None
        }
    coarse_scores = [
        score(rail_degrees + quarter * 90 + delta)
        for quarter in [0, 1]
        for delta in np.arange(-7.5, 7.51, 0.25)
    ]
    best_score = max(coarse_scores, key=lambda report: report['repeatedBandPower'])
    fine_scores = [score(best_score['angleDegrees'] + delta) for delta in np.arange(-0.25, 0.251, 0.05)]
    best_score = max(fine_scores, key=lambda report: report['repeatedBandPower'])
    return {
        'method': 'Measured transverse roof periodicity near either orthogonal local BGT crane-rail axis; shared search bounds, no terminal-specific angle.',
        'localRailAxisDegrees': rail_degrees,
        'localRailIds': rail_ids,
        'selected': best_score
    }

def branch_source_index(tile):
    uri = tile.get('content', {}).get('uri', '')
    filename_parts = uri.split('-')
    source_prefix = filename_parts[1] if filename_parts[0] == 'terminal' else filename_parts[0]
    return int(source_prefix) if source_prefix.isdigit() else None

def contents(tile):
    if 'content' in tile:
        yield tile['content']['uri']
    for child in tile.get('children', []):
        yield from contents(child)

def build_segment(source_config, plan, reconstruction_cache, rails):
    source_index = source_config['originalSourceIndex']
    cache_directory = reconstruction_cache / str(source_index)
    cache_directory.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    points, colors = industrial_builder.source_returns(source_config)
    if len(points) < 1000:
        return {
            'sourceIndex': source_index,
            'status': 'retained original; fewer than1000 source returns',
            'sourceReturns': len(points)
        }
    source_config = dict(source_config)
    selection = industrial_builder.shape(json.loads((PROJECT_ROOT / source_config['selectionMask']).read_text())['geometry'])
    source_config['displayOriginRD'] = [selection.centroid.x, selection.centroid.y, 0]
    # Region-centred coordinates keep adjacent source segments in the same measured frame.
    quality = point_quality(points, cache_directory)
    orientation = row_orientation(points, quality, source_config, rails)
    if orientation is None or orientation['selected']['consecutiveRowWidthGaps'] < plan['parameters']['minimumConsecutiveRowGaps']:
        return {
            'sourceIndex': source_index,
            'status': 'retained original; no credible repeated roof-row pattern',
            'sourceReturns': len(points),
            'rowAxisEvidence': orientation
        }
    source_config['orientationDegrees'] = orientation['selected']['angleDegrees']
    angle = np.radians(source_config['orientationDegrees'])
    rotation = np.array([[np.cos(angle), -np.sin(angle), 0], [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
    local = (points - source_config['displayOriginRD']) @ rotation
    local_quality = {
        name: values @ rotation if name in ['normal', 'principal'] else values for name,
        values in quality.items()
    }
    frames, levels = fit_members(points, local, local_quality)
    if len(levels) < 2 or not np.any((np.diff(levels) > 2.5) & (np.diff(levels) < 3.2)):
        return {
            'sourceIndex': source_index,
            'status': 'retained original; insufficient repeated source roof elevations',
            'sourceReturns': len(points),
            'rowAxisEvidence': orientation
        }
    ground = MeasuredGround(PROJECT_ROOT, source_config, plan['surveyWaterInventory'])
    rectangles, face_colors, report = reconstruct_roofs(
        PROJECT_ROOT,
        source_config,
        points,
        colors,
        local_quality,
        frames,
        levels,
        ground,
        industrial_builder
    )
    output_filename = f'terminal-{source_index}.glb'
    bounds, byte_count = industrial_builder.encode_glb(
        rectangles,
        face_colors,
        cache_directory / output_filename,
        source_config,
        1.0
    )
    document, binary = mesh_partition.read_glb(cache_directory / output_filename)
    interpretation = {
        'reconstruction': 'source roof bands and fitted straight members',
        'hiddenWallsAndBases': 'inferred to surveyed DTM or nearby same-flight dry-terminal ground',
        'tierJoints': 'illustrative material divisions from repeated roof levels; not surveyed container boundaries'
    }
    for item in [*document['nodes'], *document['meshes']]:
        item.setdefault('extras', {}).update(interpretation)
    mesh_partition.write_glb(cache_directory / output_filename, document, bytearray(binary))
    byte_count = (cache_directory / output_filename).stat().st_size
    report.update({
        'sourceIndex': source_index,
        'status': 'reconstructed',
        'source': source_config,
        'rowAxisEvidence': orientation,
        'sourceDerivedRoofLevels': levels.tolist(),
        'uri': output_filename,
        'bounds': industrial_builder.bounding_box(bounds),
        'bytes': byte_count,
        'gzipBytes': len(gzip.compress((cache_directory / output_filename).read_bytes(), compresslevel=9)),
        'seconds': time.monotonic() - started
    })
    (cache_directory / 'reconstruction.json').write_text(json.dumps(report, indent=2) + '\n')
    print(
        json.dumps({field_name: report[field_name] for field_name in ['sourceIndex', 'status', 'triangles', 'bytes', 'seconds']}),
        flush=True
    )
    return report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--plan',
        type=Path,
        default=PROJECT_ROOT / 'source-data/industrial-structures/terminal-reconstruction.json'
    )
    parser.add_argument(
        '--sources',
        type=Path,
        default=PROJECT_ROOT / 'source-data/industrial-structures/terminal-sources.json'
    )
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument(
        '--tileset',
        type=Path,
        required=True,
        help='Stable shipping tileset, not temporary prototype index'
    )
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--only', type=int, nargs='*', help='Bounded reproduction by original source index')
    arguments = parser.parse_args()
    assert arguments.base.resolve() != arguments.output.resolve()
    arguments.output.mkdir(parents=True, exist_ok=True)
    plan = json.loads(arguments.plan.read_text())
    source_inventory = json.loads(arguments.sources.read_text())
    tileset = json.loads(arguments.tileset.read_text())
    manifest = json.loads((arguments.base / 'manifest.json').read_text())
    reconstruction_cache = PROJECT_ROOT / 'work/data-cache/industrial-terminals/reconstruction'
    reconstruction_cache.mkdir(parents=True, exist_ok=True)
    rails = industrial_builder.load_crane_rails()
    reports = []
    started = time.monotonic()
    selected_sources = [
        source_config for source_config in source_inventory['sources']
        if arguments.only is None or source_config['originalSourceIndex'] in arguments.only
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=arguments.workers) as pool:
        pending = [pool.submit(
            build_segment,
            source_config,
            plan,
            reconstruction_cache,
            rails
        ) for source_config in selected_sources]
        for future in concurrent.futures.as_completed(pending):
            report = future.result()
            reports.append(report)
            if report['status'] != 'reconstructed':
                print(json.dumps(report), flush=True)
            (reconstruction_cache / 'progress.json').write_text(json.dumps(
                [{
                    field_name: field_value for field_name,
                    field_value in report.items() if field_name not in ['roofs', 'bands']
                } for report in reports],
                indent=2
            ))
    reports.sort(key=lambda report: report['sourceIndex'])
    replacements = {report['sourceIndex']: report for report in reports if report['status'] == 'reconstructed'}
    children = []
    unchanged = []
    emitted = set()
    delivery = []
    for tile in tileset['root']['children']:
        source_index = branch_source_index(tile)
        if source_index in replacements:
            if source_index in emitted:
                continue
            emitted.add(source_index)
            report = replacements[source_index]
            source = reconstruction_cache / str(source_index) / report['uri']
            chunks, proof = mesh_partition.partition_glb(
                source,
                arguments.output,
                plan['parameters']['deliveryCellMetres']
            )
            delivery.append(proof)
            for child in chunks.values():
                child['geometricError'] = 0
                children.append(child)
        else:
            children.append(tile)
            for uri in contents(tile):
                source = arguments.base / uri
                destination = arguments.output / uri
                if not destination.exists():
                    shutil.copy2(source, destination)
                unchanged.append({'uri': uri, 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()})
    assert emitted == set(replacements), (emitted, set(replacements))
    tileset['root']['children'] = children
    tileset['root']['boundingVolume']['box'] = mesh_partition.union_boxes([child['boundingVolume']['box'] for child in children])
    (arguments.output / 'tileset.json').write_text(json.dumps(tileset, separators=(',', ':')))
    summary = [
        {field_name: field_value for field_name, field_value in report.items()
         if field_name not in ['roofs', 'bands', 'omittedRoofs', 'memberEvidence', 'surveyWaterSourceInventory']}
        for report in reports
    ]
    previous_reconstruction = manifest.get('terminalReconstruction', {})
    previous_reports = {report['sourceIndex']: report
                        for report in previous_reconstruction.get('replacements', [])}
    previous_reports.update({report['sourceIndex']: report for report in summary})
    summary = sorted(previous_reports.values(), key=lambda report: report['sourceIndex'])
    previous_delivery = {record['source']: record
                         for record in previous_reconstruction.get('delivery', [])}
    previous_delivery.update({record['source']: record for record in delivery})
    delivery = list(previous_delivery.values())
    if 'spatialSubdivision' in manifest:
        manifest['originalVoxelDelivery'] = manifest.pop('spatialSubdivision')
    manifest['terminalReconstruction'] = {
        'writtenBy': 'AI, gpt-6-astra, 2026-10-24',
        'plan': str(arguments.plan.relative_to(PROJECT_ROOT)),
        'planSha256': hashlib.sha256(arguments.plan.read_bytes()).hexdigest(),
        'sourceInputsSha256': hashlib.sha256(arguments.sources.read_bytes()).hexdigest(),
        'baseTilesetSha256': hashlib.sha256(arguments.tileset.read_bytes()).hexdigest(),
        'stages': 'Original source/flight selection and exclusions; denser input; observed roof bands/straight members; inferred hidden walls/bases; illustrative tier joints; exact250m triangle partition.',
        'replacements': summary,
        'delivery': delivery,
        'unchangedFiles': unchanged,
        'elapsedSeconds': time.monotonic() - started
    }
    (arguments.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(
        json.dumps({
            'reconstructedSegments': len(replacements),
            'retainedSegments': len(reports) - len(replacements),
            'referencedGlbFiles': len(list(arguments.output.glob('*.glb'))),
            'glbBytes': sum((p.stat().st_size for p in arguments.output.glob('*.glb'))),
            'seconds': time.monotonic() - started
        }),
        flush=True
    )
if __name__ == '__main__':
    main()
