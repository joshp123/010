#!/usr/bin/env python3
"""Written by AI on 2026-10-24 by model GPT-6.1 Sol.
Prepare replaceable, illustrative surface-light lookups from existing lamp GLBs.
No source acquisition, geometry edits, missing fixtures or photometric claims.
"""
import argparse
import gzip
import hashlib
import json
import struct
import time
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TILE_METRES = 1024
CELL_METRES = 8
PIXELS = TILE_METRES // CELL_METRES


def read_accessor(document, binary, index):
    accessor = document['accessors'][index]
    view = document['bufferViews'][accessor['bufferView']]
    data_type = {5123: '<u2', 5125: '<u4', 5126: '<f4'}[accessor['componentType']]
    components = {'SCALAR': 1, 'VEC3': 3}[accessor['type']]
    component_bytes = np.dtype(data_type).itemsize
    values = np.ndarray(
        (accessor['count'], components), dtype=data_type, buffer=binary,
        offset=view.get('byteOffset', 0) + accessor.get('byteOffset', 0),
        strides=(view.get('byteStride', component_bytes * components), component_bytes),
    )
    return values.copy()


def source_heads():
    positions = []
    radii = []
    inventory = []
    measured_count = 0
    for directory in ['lamps', 'supplementary-lamps']:
        for filename in sorted((PROJECT_ROOT / 'public/data' / directory).glob('*.glb')):
            content = filename.read_bytes()
            json_bytes = struct.unpack_from('<I', content, 12)[0]
            document = json.loads(content[20:20 + json_bytes])
            binary = content[28 + json_bytes:]
            node = next(node for node in document['nodes']
                        if document['meshes'][node['mesh']]['extras']['objectKind'] == 'lampHeads')
            mesh = document['meshes'][node['mesh']]
            primitive = mesh['primitives'][0]
            vertices = read_accessor(document, binary, primitive['attributes']['POSITION']).astype(float)
            vertices *= node.get('scale', [1, 1, 1])
            vertices += node.get('translation', [0, 0, 0])
            indices = read_accessor(document, binary, primitive['indices']).ravel()
            heads = vertices[indices]
            bases = vertices[indices - 1]
            supported = np.zeros(len(heads), bool)
            if directory == 'supplementary-lamps':
                supported = np.array(mesh['extras']['heightEvidence']) == 'AHN selected-flight upper cluster'
            # Reach is illustration. Unsupported/native fixtures retain ordinary reach.
            reach = np.full(len(heads), 18.0)
            reach[supported] = np.clip((heads[supported, 1] - bases[supported, 1]) * 1.4, 24, 70)
            positions.extend(heads)
            radii.extend(reach)
            measured_count += int(supported.sum())
            inventory.append({'path': str(filename.relative_to(PROJECT_ROOT)),
                              'sha256': hashlib.sha256(content).hexdigest(), 'heads': len(heads)})
    return np.asarray(positions), np.asarray(radii), inventory, measured_count


def prepare_tile(tile_x, tile_z, positions, radii, tree, tall_tree, tall_indices):
    columns, rows = np.meshgrid(np.arange(PIXELS), np.arange(PIXELS))
    centres = np.column_stack([
        (tile_x * TILE_METRES + (columns.ravel() + 0.5) * CELL_METRES),
        (tile_z * TILE_METRES + (rows.ravel() + 0.5) * CELL_METRES),
    ])
    _, nearest = tree.query(centres, k=8)
    # Tall heads can outrange nearer ordinary fixtures: consider them separately.
    _, nearest_tall = tall_tree.query(centres, k=min(2, len(tall_indices)))
    nearest_tall = np.asarray(nearest_tall).reshape(len(centres), -1)
    candidates = np.column_stack([nearest, tall_indices[nearest_tall]])
    offsets = positions[candidates][:, :, [0, 2]] - centres[:, None, :]
    score = np.linalg.norm(offsets, axis=2) / radii[candidates]
    ordered = np.argsort(score, axis=1)
    first = candidates[np.arange(len(centres)), ordered[:, 0]]
    # The same source may occur in both candidate sets; never count it twice.
    score[candidates == first[:, None]] = np.inf
    second = candidates[np.arange(len(centres)), np.argmin(score, axis=1)]
    selected = np.column_stack([first, second])
    field = np.zeros((2, PIXELS, PIXELS, 4), dtype='<f2')
    maximum_error = 0.0
    active = 0
    for rank in range(2):
        chosen = selected[:, rank]
        offset = positions[chosen].copy()
        offset[:, 0] -= centres[:, 0]
        offset[:, 2] -= centres[:, 1]
        values = np.column_stack([offset, radii[chosen]])
        distance = np.linalg.norm(offset[:, [0, 2]], axis=1)
        # Include a cell diagonal margin; fragments evaluate exact distance.
        relevant = distance <= radii[chosen] + CELL_METRES / np.sqrt(2)
        values[~relevant] = 0
        quantized = values.astype('<f2')
        maximum_error = max(maximum_error, float(abs(quantized.astype(float) - values).max()))
        field[rank] = quantized.reshape(PIXELS, PIXELS, 4)
        active += int(relevant.sum())
    return field, maximum_error, active


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--bounds', type=float, nargs=4, action='append',
                        metavar=('MIN_X', 'MIN_Z', 'MAX_X', 'MAX_Z'),
                        help='Optional local metre QA bounds; default covers every source influence.')
    arguments = parser.parse_args()
    arguments.output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    positions, radii, inventory, measured_count = source_heads()
    tree = cKDTree(positions[:, [0, 2]])
    tall_indices = np.flatnonzero(radii > 18)
    tall_tree = cKDTree(positions[tall_indices][:, [0, 2]])
    selected_tiles = set()
    if arguments.bounds:
        selection_bounds = arguments.bounds
    else:
        # A cell can be relevant when its centre is within one half diagonal
        # beyond the reach. Include that margin across all source-tile edges.
        selection_bounds = [
            [head[0] - radius - CELL_METRES / np.sqrt(2),
             head[2] - radius - CELL_METRES / np.sqrt(2),
             head[0] + radius + CELL_METRES / np.sqrt(2),
             head[2] + radius + CELL_METRES / np.sqrt(2)]
            for head, radius in zip(positions, radii)
        ]
    for min_x, min_z, max_x, max_z in selection_bounds:
        for tile_x in range(int(np.floor(min_x / TILE_METRES)), int(np.ceil(max_x / TILE_METRES))):
            for tile_z in range(int(np.floor(min_z / TILE_METRES)), int(np.ceil(max_z / TILE_METRES))):
                selected_tiles.add((tile_x, tile_z))
    records = []
    for tile_x, tile_z in sorted(selected_tiles):
        field, error, active = prepare_tile(tile_x, tile_z, positions, radii, tree, tall_tree, tall_indices)
        if not active:
            continue
        raw = field.tobytes()
        compressed = gzip.compress(raw, mtime=0)
        name = f'{tile_x}_{tile_z}.bin.gz'
        (arguments.output / name).write_bytes(compressed)
        records.append({'x': tile_x, 'z': tile_z, 'uri': name, 'bytes': len(compressed),
                        'decodedBytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                        'maximumLookupQuantizationMetres': error})
    manifest = {
        'writtenBy': 'AI, GPT-6.1 Sol, 2026-10-24', 'tileMetres': TILE_METRES,
        'cellMetres': CELL_METRES, 'pixels': PIXELS, 'nearestHeads': 2,
        'sourceHeads': len(positions), 'measuredTallHeads': measured_count,
        'coverage': 'bounded-QA' if arguments.bounds else 'all-source-influence',
        'boundsLocalMetres': arguments.bounds, 'preparedTiles': sorted(selected_tiles),
        'tiles': records, 'sources': inventory,
        'interpretation': 'Observed prepared head anchors; supplementary unsupported heads remain illustrative10m. Reach18m ordinary; supported tall head height*1.4 bounded24..70m. Two candidate heads per8m cell, continuous fragment falloff. No emitter direction, operational state, occlusion or photometry is surveyed. No missing fixtures inserted.',
        'elapsedSeconds': time.monotonic() - started,
    }
    (arguments.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'tiles': len(records), 'gzipBytes': sum(record['bytes'] for record in records),
                      'sourceHeads': len(positions), 'seconds': manifest['elapsedSeconds']}))


if __name__ == '__main__':
    main()
