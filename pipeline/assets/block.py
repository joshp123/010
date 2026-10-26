#!/usr/bin/env -S .devenv/profile/bin/python
"""Written by AI on 2026-10-26 by model GPT-6 Astra.

Incrementally compose, verify, assemble and inspect building assets for Delfshaven.
Generation and perception remain separate owners; this command makes no model calls.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from PIL import Image, ImageDraw, ImageOps

ROOT = Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
REPOSITORY = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
TILES = [f'x{x}_y{y}' for x in (89750, 90000, 90250, 90500)
         for y in (435750, 436000, 436250, 436500)]


def input_stamp(paths):
    records = []
    for path in sorted(set(paths)):
        if path.exists():
            stat = path.stat()
            records.append((str(path), stat.st_size, stat.st_mtime_ns))
        else:
            records.append((str(path), None, None))
    return hashlib.sha256(json.dumps(records).encode()).hexdigest()


def save_json(path, value):
    pending = path.with_name('.' + path.name + '.pending')
    pending.write_text(json.dumps(value, indent=2) + '\n')
    pending.replace(path)


def run_step(script, tile, log, *arguments):
    command = [sys.executable, str(SCRIPTS / script), *arguments, '--tile', tile]
    environment = dict(os.environ)
    environment['PATH'] = str(Path(sys.executable).parent) + os.pathsep + environment.get('PATH', '')
    result = subprocess.run(command, cwd=REPOSITORY, env=environment,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    with log.open('a') as stream:
        stream.write('\n' + datetime.now(timezone.utc).isoformat() + ' ' + ' '.join(command) + '\n' + result.stdout)
    if result.returncode:
        raise RuntimeError(f'{script}: {result.stdout[-2000:].strip()}')


def process_tile(tile, render=False, preserve_existing=False):
    directory = ROOT / 'assets/v1/tiles' / tile
    directory.mkdir(parents=True, exist_ok=True)
    state_path = directory / 'buildings.pipeline.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    log = directory / 'buildings.pipeline.log'
    result = {'tile': tile, 'date': datetime.now(timezone.utc).isoformat()}
    try:
        if preserve_existing:
            report = json.loads((directory / 'buildings.assembly.json').read_text())
            result.update(status='preserved-existing', bytes=report['bytes'],
                          pending_elevations=len(report['pending_elevations']),
                          wall_area_fractions=report['wall_area_fractions'],
                          roof_area_fractions=report['building_roof_area_fractions'],
                          original_materials=report['original_materials'],
                          retained_original=report['area_routes_m2']['retained_original'])
            if render:
                capture = directory / 'check-oblique.json'
                captured = json.loads(capture.read_text()) if capture.exists() else {}
                if captured.get('glb_sha256') != report['sha256'] or not (directory / 'check-oblique.png').exists():
                    run_step('check_render.py', tile, log)
                result['rendered'] = True
            return result
        # These commands cache source-stable outputs. Neither invokes a model.
        run_step('wall_facts.py', tile, log)
        run_step('compose.py', tile, log)
        run_step('verify.py', tile, log)
        roof = ROOT / 'assets/v1/roofs' / tile
        quadrant_inputs = [roof / quadrant / filename for quadrant in ('nw', 'ne', 'sw', 'se')
                           for filename in ('generated-raw.png', 'generation.json')]
        if not all(path.exists() for path in quadrant_inputs):
            result.update(status='pending-roofs', missing_roof_inputs=[str(p) for p in quadrant_inputs if not p.exists()])
            return result
        roof_dependencies = quadrant_inputs + [roof / 'reference.json', roof / 'occlusions.json', roof / 'semantic-review.json',
            ROOT / 'scene/v1/tiles' / tile / 'ortho.jpg', ROOT / 'scene/v1/tiles' / tile / 'classes.png',
            ROOT / 'scene/v1/tiles' / tile / 'buildings.glb', SCRIPTS / 'roofs.py',
            SCRIPTS / 'verify_roofs.py', SCRIPTS / 'verification-config.json']
        roof_stamp = input_stamp(roof_dependencies)
        roof_generation = roof / 'generation.json'
        if state.get('roof_inputs') != roof_stamp or not (roof / 'roof.webp').exists() or not roof_generation.exists():
            # A separate roof worker may already have produced the same completed asset.
            existing = json.loads(roof_generation.read_text()) if roof_generation.exists() else {}
            fresh = ((roof / 'roof.webp').exists() and existing.get('verification')
                     and existing.get('output_sha256') == hashlib.sha256((roof / 'roof.webp').read_bytes()).hexdigest()
                     and max(path.stat().st_mtime_ns for path in roof_dependencies if path.exists()) <= roof_generation.stat().st_mtime_ns)
            if not fresh:
                image_dependencies = quadrant_inputs + [roof / 'reference.json', SCRIPTS / 'roofs.py']
                image_fresh = ((roof / 'roof.webp').exists()
                               and existing.get('output_sha256') == hashlib.sha256((roof / 'roof.webp').read_bytes()).hexdigest()
                               and max(path.stat().st_mtime_ns for path in image_dependencies) <= (roof / 'roof.webp').stat().st_mtime_ns)
                if not image_fresh:
                    run_step('roofs.py', tile, log, 'assemble')
                run_step('verify_roofs.py', tile, log)
            state['roof_inputs'] = roof_stamp
        dependencies = [directory / 'composed/composition.json', roof / 'roof.webp', roof_generation,
                        roof / 'interpreted-mask.png', ROOT / 'scene/v1/tiles' / tile / 'buildings.glb',
                        SCRIPTS / 'assemble.py', SCRIPTS / 'composed_parts.py',
                        ROOT / 'facts/v1/work' / tile / 'reference-coordinate-audit.json']
        dependencies.extend((ROOT / 'assets/v1/parts').glob('*'))
        for reference_path in (ROOT / 'assets/v1/elevations').glob('*/reference.json'):
            reference = json.loads(reference_path.read_text())
            if reference.get('tile') != tile:
                continue
            folder = reference_path.parent
            dependencies.extend([reference_path, folder / 'reference.png', folder / 'generated-raw.png',
                                 folder / 'generation.json', folder / 'verification.json', folder / 'generated-aligned.png',
                                 folder / 'interpreted-mask.png'])
            dependencies.extend(folder.glob('chunks/*/generated-raw.png'))
        stamp = input_stamp(dependencies)
        artifacts = [directory / name for name in ('buildings.glb', 'buildings-provenance.glb', 'buildings.assembly.json')]
        if state.get('assembly_inputs') != stamp or not all(path.exists() for path in artifacts):
            run_step('assemble.py', tile, log, '--provenance-tint')
            state['assembly_inputs'] = stamp
            result['assembled'] = True
        else:
            result['assembled'] = False
        report = json.loads((directory / 'buildings.assembly.json').read_text())
        result.update(status='assembled', bytes=report['bytes'], pending_elevations=len(report['pending_elevations']),
                      wall_area_fractions=report['wall_area_fractions'],
                      roof_area_fractions=report['building_roof_area_fractions'],
                      original_materials=report['original_materials'], retained_original=report['area_routes_m2']['retained_original'])
        if render:
            capture = directory / 'check-oblique.json'
            captured = json.loads(capture.read_text()) if capture.exists() else {}
            if captured.get('glb_sha256') != report['sha256'] or not (directory / 'check-oblique.png').exists():
                run_step('check_render.py', tile, log)
            result['rendered'] = True
    except (RuntimeError, ValueError, OSError) as error:
        if 'No measured tile material exists' in str(error):
            result.update(status='pending-facts', reason='Awaiting tile material measurement from perception', log=str(log))
        else:
            result.update(status='blocked', error=str(error), log=str(log))
    finally:
        state.update(written_by='AI, GPT-6 Astra, 2026-10-26', result=result)
        save_json(state_path, state)
    return result


def write_contact_sheet(tiles, target):
    canvas = Image.new('RGB', (2400, 2560), 'white')
    painter = ImageDraw.Draw(canvas)
    for index, tile in enumerate(tiles):
        left, top = (index // 4) * 600, (index % 4) * 640
        painter.text((left + 15, top + 10), tile, fill='black')
        capture = ROOT / 'assets/v1/tiles' / tile / 'check-oblique.png'
        if capture.exists():
            with Image.open(capture) as image:
                canvas.paste(ImageOps.contain(image.convert('RGB'), (600, 600)), (left, top + 40))
        else:
            painter.text((left + 15, top + 100), 'Pending', fill='black')
    pending = target.with_name('.' + target.stem + '.pending.png')
    canvas.save(pending)
    pending.replace(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument('--tile')
    scope.add_argument('--block', choices=['delfshaven'])
    parser.add_argument('--render', action='store_true')
    parser.add_argument('--preserve-existing', action='append', default=[], metavar='TILE',
                        help='Read and render this tile without rebuilding its accepted assets')
    parser.add_argument('--watch', action='store_true', help='Repeat until interrupted; model work remains external')
    parser.add_argument('--interval', type=float, default=60)
    args = parser.parse_args()
    tiles = [args.tile] if args.tile else TILES
    while True:
        records = []
        for tile in tiles:
            result = process_tile(tile, args.render, tile in args.preserve_existing)
            records.append(result)
            print(json.dumps(result), flush=True)
        if args.block:
            path = ROOT / 'assets/v1/blocks/delfshaven/buildings.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            save_json(path, {'written_by': 'AI, GPT-6 Astra, 2026-10-26', 'tiles': records})
            if args.render:
                write_contact_sheet(tiles, path.with_name('buildings-contact-sheet.png'))
        if not args.watch:
            return int(any(record['status'] == 'blocked' for record in records))
        time.sleep(max(1, args.interval))


if __name__ == '__main__':
    raise SystemExit(main())
