#!/usr/bin/env python3
"""Written by AI, gpt-6-astra, 2026-10-24.
Partition dense prepared green/industrial GLBs without changing their triangles.
Requires Nix Python with numpy. Read source assets; write a separate output folder.
"""
import argparse
import copy
import hashlib
import json
import shutil
import struct
from pathlib import Path

import numpy as np

COMPONENT_TYPES = {5120: 'i1', 5121: 'u1', 5122: '<i2', 5123: '<u2', 5125: '<u4', 5126: '<f4'}
COMPONENT_COUNTS = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}


def read_glb(path):
    data = path.read_bytes()
    magic, version, size = struct.unpack_from('<4sII', data)
    assert magic == b'glTF' and version == 2 and size == len(data)
    json_length = struct.unpack_from('<I', data, 12)[0]
    document = json.loads(data[20:20 + json_length])
    binary = data[28 + json_length:]
    return document, binary


def accessor_values(document, binary, accessor_index):
    accessor = document['accessors'][accessor_index]
    view = document['bufferViews'][accessor['bufferView']]
    dtype = np.dtype(COMPONENT_TYPES[accessor['componentType']])
    columns = COMPONENT_COUNTS[accessor['type']]
    offset = view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
    return np.ndarray((accessor['count'], columns), dtype=dtype, buffer=binary, offset=offset,
                      strides=(view.get('byteStride', columns * dtype.itemsize), dtype.itemsize))


def prepared_meshes(path, cell_size):
    document, binary = read_glb(path)
    primitives = []
    assert 'animations' not in document and 'skins' not in document
    for node_index in document['scenes'][document.get('scene', 0)]['nodes']:
        node = document['nodes'][node_index]
        assert not any(key in node for key in ['rotation', 'matrix', 'children'])
        mesh = document['meshes'][node['mesh']]
        for primitive_index, primitive in enumerate(mesh['primitives']):
            assert primitive.get('mode', 4) == 4
            attributes = {name: accessor_values(document, binary, index)
                          for name, index in primitive['attributes'].items()}
            positions = (attributes['POSITION'].astype(float) * node.get('scale', [1, 1, 1]) +
                         node.get('translation', [0, 0, 0]))
            indices = accessor_values(document, binary, primitive['indices']).reshape(-1, 3)
            cells = np.floor(positions[indices].mean(axis=1)[:, [0, 2]] / cell_size).astype(np.int32)
            primitives.append({'node': node, 'mesh': mesh, 'primitive': primitive,
                               'identity': [node_index, primitive_index], 'attributes': attributes,
                               'positions': positions, 'indices': indices, 'cells': cells})
    return document, primitives


def write_glb(path, document, binary):
    binary += b'\0' * (-len(binary) % 4)
    if binary:
        document['buffers'] = [{'byteLength': len(binary)}]
    encoded = json.dumps(document, separators=(',', ':')).encode()
    encoded += b' ' * (-len(encoded) % 4)
    suffix = struct.pack('<I4s', len(binary), b'BIN\0') + binary if binary else b''
    result = (struct.pack('<4sII', b'glTF', 2, 20 + len(encoded) + len(suffix)) +
              struct.pack('<I4s', len(encoded), b'JSON') + encoded + suffix)
    path.write_bytes(result)


def bounding_box(positions):
    # Prepared GLBs are east/up/south. 3D Tiles applies Y-up to Z-up first.
    positions = positions[:, [0, 2, 1]] * [1, -1, 1]
    minimum, maximum = positions.min(axis=0), positions.max(axis=0)
    centre, half = (minimum + maximum) / 2, (maximum - minimum) / 2
    return [*centre, half[0], 0, 0, 0, half[1], 0, 0, 0, half[2]]


def union_boxes(boxes):
    boxes = np.array(boxes)
    minimum = np.min(boxes[:, :3] - boxes[:, [3, 7, 11]], axis=0)
    maximum = np.max(boxes[:, :3] + boxes[:, [3, 7, 11]], axis=0)
    centre, half = (minimum + maximum) / 2, (maximum - minimum) / 2
    return [*centre, half[0], 0, 0, 0, half[1], 0, 0, 0, half[2]]


def partition_glb(source, output, cell_size):
    original, primitives = prepared_meshes(source, cell_size)
    cells = sorted({tuple(cell) for primitive in primitives for cell in np.unique(primitive['cells'], axis=0)})
    coverage = [np.zeros(len(primitive['indices']), dtype=np.uint8) for primitive in primitives]
    chunks, reports = {}, []
    for cell in cells:
        document = {key: copy.deepcopy(value) for key, value in original.items()
                    if key not in ['nodes', 'meshes', 'scenes', 'accessors', 'bufferViews', 'buffers']}
        document.update({'scene': 0, 'scenes': [{'nodes': []}], 'nodes': [], 'meshes': [],
                         'accessors': [], 'bufferViews': []})
        binary = bytearray()
        expected, world_positions = [], []

        def add_values(values, template, target):
            nonlocal binary
            binary += b'\0' * (-len(binary) % 4)
            byte_offset = len(binary)
            if target == 34962:
                stride = (values.shape[1] * values.dtype.itemsize + 3) // 4 * 4
                packed = bytearray(len(values) * stride)
                array = np.ndarray(values.shape, dtype=values.dtype, buffer=packed,
                                   strides=(stride, values.dtype.itemsize))
                array[:] = values
                binary.extend(packed)
            else:
                stride = None
                binary.extend(values.tobytes())
            view = {'buffer': 0, 'byteOffset': byte_offset, 'byteLength': len(binary) - byte_offset, 'target': target}
            if stride:
                view['byteStride'] = stride
            view_index = len(document['bufferViews'])
            document['bufferViews'].append(view)
            accessor = {key: value for key, value in template.items()
                        if key not in ['bufferView', 'byteOffset', 'count', 'min', 'max']}
            accessor.update({'bufferView': view_index, 'count': len(values)})
            if 'min' in template:
                accessor['min'], accessor['max'] = values.min(axis=0).tolist(), values.max(axis=0).tolist()
            index = len(document['accessors'])
            document['accessors'].append(accessor)
            return index

        for primitive_index, source_primitive in enumerate(primitives):
            selected = np.flatnonzero(np.all(source_primitive['cells'] == cell, axis=1))
            if not len(selected):
                continue
            coverage[primitive_index][selected] += 1
            source_indices = source_primitive['indices'][selected]
            used, remapped = np.unique(source_indices, return_inverse=True)
            primitive = copy.deepcopy(source_primitive['primitive'])
            primitive['attributes'] = {}
            for name, values in source_primitive['attributes'].items():
                template = original['accessors'][source_primitive['primitive']['attributes'][name]]
                primitive['attributes'][name] = add_values(values[used], template, 34962)
            indices = remapped.astype('<u2' if len(used) <= 65535 else '<u4').reshape(-1, 1)
            primitive['indices'] = add_values(indices, {'componentType': 5123 if len(used) <= 65535 else 5125,
                                                        'type': 'SCALAR'}, 34963)
            mesh = copy.deepcopy(source_primitive['mesh'])
            mesh['primitives'] = [primitive]
            node = copy.deepcopy(source_primitive['node'])
            node['mesh'] = len(document['meshes'])
            document['meshes'].append(mesh)
            document['scenes'][0]['nodes'].append(len(document['nodes']))
            document['nodes'].append(node)
            expected.append((source_primitive, selected))
            world_positions.append(source_primitive['positions'][used])
        output_name = f'{source.stem}--{cell[0]}_{cell[1]}.glb'
        path = output / output_name
        write_glb(path, document, binary)
        written, written_binary = read_glb(path)
        triangle_count = 0
        # Compare the actual written file, not an intermediate geometry array.
        for node, (source_primitive, selected) in zip(written['nodes'], expected):
            primitive = written['meshes'][node['mesh']]['primitives'][0]
            indices = accessor_values(written, written_binary, primitive['indices']).reshape(-1, 3)
            source_indices = source_primitive['indices'][selected]
            triangle_count += len(indices)
            assert node.get('translation') == source_primitive['node'].get('translation')
            assert node.get('scale') == source_primitive['node'].get('scale')
            assert written['meshes'][node['mesh']].get('extras') == source_primitive['mesh'].get('extras')
            for name, values in source_primitive['attributes'].items():
                actual = accessor_values(written, written_binary, primitive['attributes'][name])[indices]
                assert np.array_equal(actual, values[source_indices]), (source.name, cell, name)
            assert written.get('materials') == original.get('materials')
        bounds = bounding_box(np.concatenate(world_positions))
        chunks[cell] = {'boundingVolume': {'box': bounds}, 'content': {'uri': output_name}}
        reports.append({'uri': output_name, 'bytes': path.stat().st_size, 'triangles': triangle_count,
                        'cell': [int(value) for value in cell]})
    assert all(np.all(counts == 1) for counts in coverage), source.name
    report = {'source': source.name, 'sourceSha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'sourceBytes': source.stat().st_size, 'sourceTriangles': sum(len(p['indices']) for p in primitives),
              'outputBytes': sum(chunk['bytes'] for chunk in reports), 'chunks': reports,
              'validation': 'Every source triangle appears exactly once; all written vertex attributes, node transforms and materials equal the original values.'}
    return chunks, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cell-metres', type=float, default=250)
    parser.add_argument('--minimum-bytes', type=int, default=1000000)
    arguments = parser.parse_args()
    assert arguments.input.resolve() != arguments.output.resolve()
    arguments.output.mkdir(parents=True, exist_ok=True)
    tileset = json.loads((arguments.input / 'tileset.json').read_text())
    children, reports = [], []
    empty_written = False

    def empty_content(bounds):
        nonlocal empty_written
        if not empty_written:
            write_glb(arguments.output / 'empty.glb', {'asset': {'version': '2.0'}, 'scene': 0,
                                                     'scenes': [{'nodes': []}], 'nodes': []}, bytearray())
            empty_written = True
        return {'boundingVolume': {'box': bounds}, 'content': {'uri': 'empty.glb'}}

    for tile in tileset['root']['children']:
        levels = [tile, *tile.get('children', [])]
        assert len(levels) <= 2 and all('content' in level and 'uri' in level['content'] for level in levels)
        files = [arguments.input / level['content']['uri'] for level in levels]
        if max(path.stat().st_size for path in files) <= arguments.minimum_bytes:
            children.append(tile)
            for path in files:
                shutil.copy2(path, arguments.output / path.name)
            continue
        partitioned = []
        for path in files:
            chunks, report = partition_glb(path, arguments.output, arguments.cell_metres)
            partitioned.append(chunks)
            reports.append(report)
            print(json.dumps({key: report[key] for key in ['source', 'sourceBytes', 'sourceTriangles', 'outputBytes']} |
                             {'chunks': len(chunks)}), flush=True)
        for cell in sorted(set().union(*[set(level) for level in partitioned])):
            bounds = union_boxes([level[cell]['boundingVolume']['box'] for level in partitioned if cell in level])
            coarse = copy.deepcopy(partitioned[0][cell]) if cell in partitioned[0] else empty_content(bounds)
            coarse.update({'boundingVolume': {'box': bounds}, 'geometricError': tile['geometricError']})
            if len(levels) == 2:
                fine = copy.deepcopy(partitioned[1][cell]) if cell in partitioned[1] else empty_content(bounds)
                fine['geometricError'] = levels[1]['geometricError']
                coarse.update({'refine': tile.get('refine', 'REPLACE'), 'children': [fine]})
                assert coarse['refine'] == 'REPLACE'
            children.append(coarse)
    for tile in children:
        for level in [tile, *tile.get('children', [])]:
            assert (arguments.output / level['content']['uri']).is_file(), level['content']['uri']
    tileset['root']['children'] = children
    tileset['root']['boundingVolume']['box'] = union_boxes([tile['boundingVolume']['box'] for tile in children])
    (arguments.output / 'tileset.json').write_text(json.dumps(tileset, separators=(',', ':')))
    manifest = json.loads((arguments.input / 'manifest.json').read_text())
    manifest['tilesBeforeSubdivision'] = manifest.pop('tiles')
    manifest['spatialSubdivision'] = {'writtenBy': 'AI, gpt-6-astra, 2026-10-24', 'cellMetres': arguments.cell_metres,
        'minimumSourceBytes': arguments.minimum_bytes, 'assignment': 'Uncut source triangles assigned once by centroid; original quantized attributes and node transforms retained.',
        'lod': 'Original coarse/fine errors and REPLACE retained per cell; empty content preserves empty portions of either LOD.',
        'sourceTilesetSha256': hashlib.sha256((arguments.input / 'tileset.json').read_bytes()).hexdigest(), 'sources': reports}
    (arguments.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'partitionedFiles': len(reports), 'rootChildren': len(children),
                      'sourceBytes': sum(p.stat().st_size for p in arguments.input.glob('*.glb')),
                      'outputBytes': sum(p.stat().st_size for p in arguments.output.glob('*.glb'))}), flush=True)


if __name__ == '__main__':
    main()
