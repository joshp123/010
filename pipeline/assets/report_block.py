#!/usr/bin/env -S .devenv/profile/bin/python
"""Written by AI on 2026-10-26 by GPT-6 Astra. Report delivered block assets."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from block import ROOT, TILES


def load(path):
    return json.loads(path.read_text())


def report():
    counts = {tile: {'roof': 0, 'wall': 0} for tile in TILES}
    elevations = ROOT / 'assets/v1/elevations'
    for path in elevations.glob('*/reference.json'):
        metadata = load(path)
        tile = metadata.get('tile')
        if tile not in counts:
            continue
        folder = path.parent
        chunks = list(folder.glob('chunks/*/generation.json'))
        generations = chunks or [folder / 'generation.json']
        for generation in generations:
            if not generation.exists() or not (generation.parent / 'generated-raw.png').exists():
                continue
            record = load(generation)
            if record.get('tool') == 'image_gen.imagegen':
                counts[tile]['wall'] += record.get('call_count', 1)
    # Extracted elevations record zero calls; count their shared generation once.
    for reference in (ROOT / 'assets/v1/batches').glob('*/reference.json'):
        tile = load(reference).get('tile')
        generation = reference.parent / 'generation.json'
        if tile in counts and generation.exists() and (reference.parent/'generated-raw.png').exists():
            record = load(generation)
            if record.get('tool') == 'image_gen.imagegen':
                counts[tile]['wall'] += record.get('call_count', 1)
    records = []
    for tile in TILES:
        directory = ROOT / 'assets/v1/tiles' / tile
        roofs = ROOT / 'assets/v1/roofs' / tile
        for generation in roofs.glob('*/generation.json'):
            if (generation.parent / 'generated-raw.png').exists():
                counts[tile]['roof'] += load(generation).get('call_count', 1)
        assembly = directory / 'buildings.assembly.json'
        row = {'tile': tile, 'completed_image_calls': counts[tile], 'status': 'missing'}
        if assembly.exists():
            data = load(assembly)
            glb = directory / 'buildings.glb'
            tint = directory / 'buildings-provenance.glb'
            capture = directory / 'check-oblique.json'
            row.update(status='assembled', wall=data['wall_area_fractions'],
                       roof=data['building_roof_area_fractions'], glb_mb=glb.stat().st_size/1e6,
                       pending_elevations=data['pending_elevations'], routes_m2=data['area_routes_m2'],
                       original_materials=data['original_materials'],
                       assembly_hash_matches=hashlib.sha256(glb.read_bytes()).hexdigest() == data['sha256'],
                       tint_exists=tint.exists(),
                       rendered=capture.exists() and load(capture).get('glb_sha256') == data['sha256'])
        records.append(row)
    directory = ROOT / 'assets/v1/blocks/delfshaven'
    directory.mkdir(parents=True, exist_ok=True)
    result = {'written_by': 'AI, GPT-6 Astra, 2026-10-26', 'date': datetime.now(timezone.utc).isoformat(),
              'image_calls_scope': 'Recorded per-tile roof, wall, and shared batch generation calls with saved raw images and metadata. Stitches are excluded. Shared parts/comparison calls and C3 text-model perception are excluded.',
              'verification_scope': 'Numerical source-visible checks; interpreted includes unmeasured synthetic styling. No all-component semantic certification.',
              'tiles': records}
    (directory / 'buildings-report.json').write_text(json.dumps(result, indent=2)+'\n')
    print('| Tile | Wall verified % | Wall interpreted % | Roof verified % | Image calls (roof + wall) | GLB MB | Pending elevations |')
    print('|---|---:|---:|---:|---:|---:|---:|')
    for row in records:
        c = row['completed_image_calls']
        if row['status'] != 'assembled':
            print(f'| {row["tile"]} | — | — | — | {c["roof"]} + {c["wall"]} | — | — |')
            continue
        print(f'| {row["tile"]} | {100*row["wall"]["verified"]:.2f} | {100*row["wall"]["interpreted"]:.2f} | {100*row["roof"]["verified"]:.2f} | {c["roof"]} + {c["wall"]} | {row["glb_mb"]:.2f} | {len(row["pending_elevations"])} |')
    return result


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    report()
