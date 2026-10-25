# Written by AI on 2026-10-25 by model GPT-6.
"""Bake the 16 core scene tiles. Run inside devenv shell; source stays untouched."""
import argparse
import copy
import hashlib
import io
import json
import math
from pathlib import Path
import struct
import subprocess
import tempfile

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import maximum_filter

FILES = ('buildings.glb', 'ground.glb', 'classes.png', 'ortho.jpg', 'objects.json')
DTYPES = {5121: 'u1', 5123: '<u2', 5125: '<u4', 5126: '<f4'}
COMPONENTS = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}


def read_glb(path):
    data = path.read_bytes()
    length = struct.unpack_from('<I', data, 12)[0]
    document = json.loads(data[20:20 + length])
    return document, bytearray(data[28 + length:])


def write_glb(path, document, binary):
    document['buffers'] = [{'byteLength': len(binary)}]
    metadata = json.dumps(document, separators=(',', ':')).encode()
    metadata += b' ' * (-len(metadata) % 4)
    binary += b'\0' * (-len(binary) % 4)
    path.write_bytes(struct.pack('<III', 0x46546c67, 2, 28 + len(metadata) + len(binary))
                     + struct.pack('<II', len(metadata), 0x4e4f534a) + metadata
                     + struct.pack('<II', len(binary), 0x004e4942) + binary)


def accessor_array(document, binary, index):
    accessor = document['accessors'][index]
    view = document['bufferViews'][accessor['bufferView']]
    dtype = np.dtype(DTYPES[accessor['componentType']])
    components = COMPONENTS[accessor['type']]
    return np.ndarray((accessor['count'], components), dtype=dtype, buffer=binary,
                      offset=view.get('byteOffset', 0) + accessor.get('byteOffset', 0),
                      strides=(view.get('byteStride', components * dtype.itemsize), dtype.itemsize)).copy()


def append_view(document, binary, data, **properties):
    binary.extend(b'\0' * (-len(binary) % 4))
    index = len(document['bufferViews'])
    document['bufferViews'].append({'buffer': 0, 'byteOffset': len(binary), 'byteLength': len(data), **properties})
    binary.extend(data)
    return index


def image_bytes(document, binary, image):
    view = document['bufferViews'][image['bufferView']]
    return binary[view.get('byteOffset', 0):view.get('byteOffset', 0) + view['byteLength']]


def texture_scales(document, binary, metres_per_texel):
    """Area-weighted density per source atlas; collapsed UVs cannot set its resolution."""
    areas = {}
    for mesh in document['meshes']:
        for primitive in mesh['primitives']:
            material = document['materials'][primitive['material']]
            texture = material.get('pbrMetallicRoughness', {}).get('baseColorTexture')
            if texture is None:
                continue
            image_index = document['textures'][texture['index']]['source']
            image = Image.open(io.BytesIO(image_bytes(document, binary, document['images'][image_index])))
            positions = accessor_array(document, binary, primitive['attributes']['POSITION'])
            uvs = accessor_array(document, binary, primitive['attributes']['TEXCOORD_0'])
            indices = (accessor_array(document, binary, primitive['indices']).ravel()
                       if 'indices' in primitive else np.arange(len(positions)))
            triangles = positions[indices].astype(float).reshape(-1, 3, 3)
            uv_triangles = (uvs[indices].astype(float) * image.size).reshape(-1, 3, 2)
            world_area = np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1)
            edges = uv_triangles[:, 1:] - uv_triangles[:, :1]
            uv_area = abs(edges[:, 0, 0] * edges[:, 1, 1] - edges[:, 0, 1] * edges[:, 1, 0])
            valid = (uv_area > 1) & (world_area > 0.001)
            old_world, old_uv = areas.get(image_index, (0, 0))
            areas[image_index] = (old_world + world_area[valid].sum(), old_uv + uv_area[valid].sum())
    return {index: min(1.0, math.sqrt(world / uv) / metres_per_texel) for index, (world, uv) in areas.items()}


def remove_unused_texels(document, binary, image_index, photo):
    """Remove atlas content never sampled by this tile, with a 16-texel filter margin."""
    mask = Image.new('L', photo.size)
    draw = ImageDraw.Draw(mask)
    for mesh in document['meshes']:
        for primitive in mesh['primitives']:
            texture = document['materials'][primitive['material']].get('pbrMetallicRoughness', {}).get('baseColorTexture')
            if texture is None or document['textures'][texture['index']]['source'] != image_index:
                continue
            uvs = accessor_array(document, binary, primitive['attributes']['TEXCOORD_0'])
            indices = (accessor_array(document, binary, primitive['indices']).ravel()
                       if 'indices' in primitive else np.arange(len(uvs)))
            assert uvs.min() >= -1e-6 and uvs.max() <= 1.000001, 'UV wrapping needs the complete atlas'
            for triangle in (uvs[indices] * photo.size).reshape(-1, 3, 2):
                draw.polygon([tuple(vertex) for vertex in triangle], fill=255)
    used = maximum_filter(np.asarray(mask), size=33) != 0
    pixels = np.asarray(photo).copy()
    pixels[~used] = np.round(pixels[used].mean(axis=0)).astype(np.uint8)
    return Image.fromarray(pixels), float(used.mean())


def bake_geometry(source, target, work, metres_per_texel, quality):
    document, binary = read_glb(source)
    original = copy.deepcopy(document)
    custom_name = '_FEATURE_ID_0' if source.name == 'buildings.glb' else '_CLASS'
    expected_values = set()
    # gltfpack does not retain custom attributes. Floating UVs preserve integer IDs exactly.
    for mesh in document['meshes']:
        for primitive in mesh['primitives']:
            attribute_index = primitive['attributes'].pop(custom_name)
            values = accessor_array(document, binary, attribute_index).ravel()
            expected_values.update(map(int, values))
            surrogate = np.column_stack((values, np.zeros(len(values)))).astype('<f4')
            view = append_view(document, binary, surrogate.tobytes(), target=34962)
            document['accessors'].append({'bufferView': view, 'componentType': 5126,
                                          'count': len(values), 'type': 'VEC2'})
            primitive['attributes']['TEXCOORD_1'] = len(document['accessors']) - 1
    for index, material in enumerate(document['materials']):
        material['name'] = f'source-material-{index}'
    texture_report = []
    for index, scale in texture_scales(original, binary, metres_per_texel).items():
        image = document['images'][index]
        photo = Image.open(io.BytesIO(image_bytes(document, binary, image))).convert('RGB')
        old_size = photo.size
        size = tuple(max(1, math.ceil(dimension * scale)) for dimension in old_size)
        photo = photo.resize(size, Image.Resampling.LANCZOS)
        photo, used_fraction = remove_unused_texels(original, binary, index, photo)
        encoded = io.BytesIO()
        photo.save(encoded, 'WEBP', quality=quality, method=6)
        image['bufferView'] = append_view(document, binary, encoded.getvalue())
        image['mimeType'] = 'image/webp'
        texture_report.append({'image': index, 'before': old_size, 'after': size,
                               'used_fraction_with_margin': used_fraction, 'bytes': len(encoded.getvalue())})
    if texture_report:
        document.setdefault('extensionsUsed', []).append('EXT_texture_webp')
        document.setdefault('extensionsRequired', []).append('EXT_texture_webp')
        for texture in document['textures']:
            texture['extensions'] = {'EXT_texture_webp': {'source': texture.pop('source')}}
    prepared = work / source.name
    write_glb(prepared, document, binary)
    subprocess.run(['gltfpack', '-i', str(prepared), '-o', str(target), '-cc', '-ce', 'ext',
                    '-kv', '-ke', '-km', '-vp', '16', '-vtf', '-vn', '10'], check=True)
    packed, compressed = read_glb(target)
    for mesh in packed['meshes']:
        for primitive in mesh['primitives']:
            index = primitive['attributes'].pop('TEXCOORD_1')
            primitive['attributes'][custom_name] = index
            accessor = packed['accessors'][index]
            assert accessor['componentType'] == 5126 and not accessor.get('normalized')
            view = packed['bufferViews'][accessor['bufferView']]
            # Access the first float in each float2; keep meshopt's stride and byte length.
            view.setdefault('byteStride', 8)
            accessor['type'] = 'SCALAR'
            for bound in ('min', 'max'):
                if bound in accessor:
                    accessor[bound] = accessor[bound][:1]
    if 'extras' in original:
        packed['extras'] = original['extras']
    assert len(packed['materials']) == len(original['materials']), 'Source materials merged'
    write_glb(target, packed, compressed)
    # Decode actual output buffers using the same decoder the browser uses.
    result = subprocess.run(['node', str(Path(__file__).with_name('verify.mjs').resolve()), str(target), custom_name],
                            text=True, capture_output=True, check=True)
    assert set(json.loads(result.stdout)) == expected_values, f'{custom_name} values changed'
    return texture_report


def bake_classes(source, target):
    rgba = np.asarray(Image.open(source).convert('RGBA'))
    assert rgba.shape == (2500, 2500, 4)
    blocks = rgba.reshape(1250, 2, 1250, 2, 4).transpose(0, 2, 1, 3, 4).reshape(1250, 1250, 4, 4)
    classes = blocks[..., 0]
    # For 2:2 or four-way ties, use the earliest source pixel (NW, NE, SW, SE).
    votes = (classes[..., :, None] == classes[..., None, :]).sum(axis=-1)
    majority = np.take_along_axis(classes, votes.argmax(axis=-1)[..., None], axis=-1)[..., 0]
    output = np.zeros((1250, 1250, 4), dtype=np.uint8)
    output[..., 0] = majority
    output[..., 1] = np.bitwise_or.reduce(blocks[..., 1], axis=-1)
    output[..., 3] = 255
    Image.fromarray(output).save(target, compress_level=9, optimize=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path('/Volumes/Josh Extreme Pro USB4 4TB/010/scene/v1'))
    parser.add_argument('--output', type=Path, default=Path('/Volumes/Josh Extreme Pro USB4 4TB/010/scene/web-v1'))
    parser.add_argument('--metres-per-texel', type=float, default=0.15)
    parser.add_argument('--texture-quality', type=int, default=80)
    args = parser.parse_args()
    assert args.output.resolve() != args.source.resolve()
    manifest = json.loads((args.source / 'manifest.json').read_text())
    tile_ids = [f'x{x}_y{y}' for x in range(89750, 90750, 250) for y in range(435750, 436750, 250)]
    manifest['tiles'] = {name: manifest['tiles'][name] for name in tile_ids}
    manifest['web_bake'] = {'author': 'Written by AI on 2026-10-25 by model GPT-6',
                            'metres_per_texel': args.metres_per_texel, 'texture_quality': args.texture_quality,
                            'formats': ['EXT_meshopt_compression', 'KHR_mesh_quantization', 'EXT_texture_webp'],
                            'class_tie_break': 'first source pixel in NW, NE, SW, SE order',
                            'gltfpack_version': subprocess.check_output(['gltfpack', '-v'], text=True).strip()}
    args.output.mkdir(parents=True, exist_ok=True)
    for tile_id in tile_ids:
        source = args.source / 'tiles' / tile_id
        target = args.output / 'tiles' / tile_id
        target.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='010-web-') as directory:
            work = Path(directory)
            textures = bake_geometry(source / 'buildings.glb', target / 'buildings.glb', work, args.metres_per_texel, args.texture_quality)
            bake_geometry(source / 'ground.glb', target / 'ground.glb', work, args.metres_per_texel, args.texture_quality)
        bake_classes(source / 'classes.png', target / 'classes.png')
        photo = Image.open(source / 'ortho.jpg').convert('RGB').resize((1000, 1000), Image.Resampling.LANCZOS)
        photo.save(target / 'ortho.jpg', quality=80, optimize=True)
        (target / 'objects.json').write_text(json.dumps(json.loads((source / 'objects.json').read_text()), separators=(',', ':')))
        before = {name: (source / name).stat().st_size for name in FILES}
        after = {name: (target / name).stat().st_size for name in FILES}
        record = manifest['tiles'][tile_id]
        record['web_bake'] = {'bytes_before': sum(before.values()), 'bytes_after': sum(after.values()),
                               'files_before': before, 'files_after': after, 'textures': textures,
                               'source_sha256': {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in FILES},
                               'sha256': {name: hashlib.sha256((target / name).read_bytes()).hexdigest() for name in FILES}}
        # Source counts remain valid; old file hashes and texture byte count do not.
        for key, filename in [('buildings', 'buildings.glb'), ('ground', 'ground.glb')]:
            if key in record and 'sha256' in record[key]:
                record[key]['sha256'] = record['web_bake']['sha256'][filename]
        record['buildings']['texture_bytes'] = sum(texture['bytes'] for texture in textures)
        print(f'{tile_id}: {sum(before.values()):,} -> {sum(after.values()):,}', flush=True)
    manifest['web_bake']['bytes_before'] = sum(t['web_bake']['bytes_before'] for t in manifest['tiles'].values())
    manifest['web_bake']['bytes_after'] = sum(t['web_bake']['bytes_after'] for t in manifest['tiles'].values())
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
