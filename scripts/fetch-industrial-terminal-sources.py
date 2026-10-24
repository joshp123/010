#!/usr/bin/env python3
"""Written by AI, gpt-6-astra, 2026-10-24. Acquire denser official inputs for reviewed terminal reconstruction.
Keeps the original selected flight/day and exclusions. Requires the project's Nix Python dependencies.
"""
import argparse
import concurrent.futures
import hashlib
import json
import time
from pathlib import Path
import laspy
import numpy as np
from laspy.copc import Bounds
PROJECT_ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--plan',
        type=Path,
        default=PROJECT_ROOT / 'source-data/industrial-structures/terminal-reconstruction.json'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=PROJECT_ROOT / 'source-data/industrial-structures/terminal-sources.json'
    )
    parser.add_argument('--workers', type=int, default=3)
    arguments = parser.parse_args()
    plan = json.loads(arguments.plan.read_text())
    original = json.loads((PROJECT_ROOT / plan['originalSelection']).read_text())
    cache_directory = PROJECT_ROOT / 'work/data-cache/industrial-terminals'
    cache_directory.mkdir(parents=True, exist_ok=True)
    selected = [
        (source_index, source_config) for source_index,
        source_config in enumerate(original) if source_config['region'] in plan['reviewedContainerRegions']
    ]
    unique_sources = {}
    for source_index, source_config in selected:
        unique_sources.setdefault(source_config['name'], source_config)

    def fetch(source):
        cache_path = cache_directory / (source['name'] + '-0.5m.laz')
        started = time.monotonic()
        if not cache_path.exists():
            with laspy.CopcReader.open(source['source'], http_num_threads=3) as reader:
                points = reader.query(
                    bounds=Bounds(*[np.array(item) for item in source['boundsRD_NAP']]),
                    resolution=0.5
                )
                header = reader.header.copy()
                header.vlrs = [item for item in header.vlrs if item.user_id != 'copc']
                laspy.LasData(header, points=points).write(cache_path)
        source_record = {
            'rawPointCloudCache': str(cache_path.relative_to(PROJECT_ROOT)),
            'sourceCropSha256': hashlib.sha256(cache_path.read_bytes()).hexdigest(),
            'sourceCropBytes': cache_path.stat().st_size,
            'queryResolutionMetres': 0.5,
            'boundsRD_NAP': source['boundsRD_NAP']
        }
        print(
            json.dumps({
                'source': source['name'],
                'bytes': source_record['sourceCropBytes'],
                'seconds': round(time.monotonic() - started, 2)
            }),
            flush=True
        )
        return (source['name'], source_record)
    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=arguments.workers) as pool:
        acquired = dict(pool.map(fetch, unique_sources.values()))
    source_inputs = []
    for index, source in selected:
        source_config = dict(source)
        source_config.update(acquired[source['name']])
        source_config['originalSourceIndex'] = index
        source_inputs.append(source_config)
    arguments.output.write_text(json.dumps(
        {
            'writtenBy': 'AI, gpt-6-astra, 2026-10-24',
            'planSha256': hashlib.sha256(arguments.plan.read_bytes()).hexdigest(),
            'policy': 'Original per-region point-source ID/day, masks and exclusions retained; no cross-flight infill.',
            'sources': source_inputs,
            'uniqueSources': len(acquired),
            'rawBytes': sum((item['sourceCropBytes'] for item in acquired.values())),
            'elapsedSeconds': time.monotonic() - started
        },
        indent=2
    ) + '\n')
    print(
        json.dumps({
            'segments': len(source_inputs),
            'uniqueSources': len(acquired),
            'rawBytes': sum((item['sourceCropBytes'] for item in acquired.values())),
            'seconds': time.monotonic() - started
        }),
        flush=True
    )
if __name__ == '__main__':
    main()
