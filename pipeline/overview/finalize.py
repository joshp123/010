"""Written by AI on 2026-10-26 by model GPT-6 Astra. Read delivered files and assemble manifest."""
import hashlib
import json
import struct
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
SCENE = ROOT / 'scene/overview-v1'
FILES = ['buildings.glb', 'classes.png', 'ortho.jpg', 'ground.glb', 'objects.json']


def glb_document(path):
    raw = path.read_bytes()
    magic, version, size = struct.unpack_from('<4sII', raw)
    assert magic == b'glTF' and version == 2 and size == len(raw), path
    json_size, json_type = struct.unpack_from('<II', raw, 12)
    assert json_type == 0x4e4f534a, path
    document = json.loads(raw[20:20+json_size])
    binary_offset = 20 + json_size
    binary = raw[binary_offset + 8:] if binary_offset < len(raw) else b''
    def values(accessor_index):
        accessor = document['accessors'][accessor_index]
        view = document['bufferViews'][accessor['bufferView']]
        dtype = {5121: 'u1', 5123: '<u2', 5125: '<u4', 5126: '<f4'}[accessor['componentType']]
        size = {'SCALAR': 1, 'VEC3': 3}[accessor['type']]
        assert accessor['count'] > 0, path
        offset = view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
        return np.frombuffer(binary, dtype=dtype, count=accessor['count'] * size, offset=offset)
    for mesh in document.get('meshes', []):
        for primitive in mesh['primitives']:
            positions = values(primitive['attributes']['POSITION'])
            assert np.isfinite(positions).all(), path
            if 'indices' in primitive:
                assert values(primitive['indices']).max() < len(positions) // 3, path
            if '_FEATURE_ID_0' in primitive['attributes']:
                identifiers = values(primitive['attributes']['_FEATURE_ID_0'])
                assert identifiers.max() < len(document['extras']['features']), path
    return document


def main():
    index = json.loads((SCENE / 'tile-index.json').read_text())
    reports = {name: json.loads((SCENE / f'{name}-report.json').read_text())
               for name in ['buildings', 'surfaces', 'imagery', 'objects']}
    tiles = {}
    for tile, record in index['tiles'].items():
        directory = SCENE / 'tiles' / tile
        files = {}
        for filename in FILES:
            raw = (directory / filename).read_bytes()
            files[filename] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        with Image.open(directory / 'classes.png') as image:
            assert image.size == (1000, 1000) and image.mode == 'RGBA', tile
            pixels = np.asarray(image)
            assert pixels[:, :, 0].max() <= 16 and pixels[:, :, 1].max() <= 3, tile
            assert not pixels[:, :, 2].any() and (pixels[:, :, 3] == 255).all(), tile
        with Image.open(directory / 'ortho.jpg') as image:
            assert image.size == (1000, 1000) and image.format == 'JPEG', tile
        building = glb_document(directory / 'buildings.glb')
        features = building['extras']['features']
        for mesh in building.get('meshes', []):
            for primitive in mesh['primitives']:
                accessor = building['accessors'][primitive['attributes']['_FEATURE_ID_0']]
                assert accessor['count'] == building['accessors'][primitive['attributes']['POSITION']]['count'], tile
                assert accessor['componentType'] in (5121, 5123, 5125), tile
        ground = glb_document(directory / 'ground.glb')
        objects = json.loads((directory / 'objects.json').read_text())
        tiles[tile] = {**record, **reports['buildings']['tiles'][tile],
                       'ground': reports['surfaces']['tiles'][tile],
                       'objects': {'trees': len(objects['trees']), 'lamps': len(objects['lamps'])},
                       'files': files, 'bytes': sum(v['bytes'] for v in files.values())}
        assert len(features) == tiles[tile]['buildings']['count'], tile
    sources = {}
    archive_paths = {Path(index['boundary_source_manifest'])}
    coordinate_manifest = ROOT / 'sources/coordinate-grids/2026-10-25/manifest.json'
    if coordinate_manifest.exists():
        archive_paths.add(coordinate_manifest)
    for report in reports.values():
        for source in report.get('sources', {}).values():
            if isinstance(source, dict) and 'manifest' in source:
                archive_paths.add(Path(source['manifest']))
        for key in ['manifest', 'source_manifest']:
            if isinstance(report.get(key), str):
                archive_paths.add(Path(report[key]))
    # Pin exact source manifests used, even if a future download extends the archive.
    pinned = SCENE / 'source-manifests'
    pinned.mkdir(exist_ok=True)
    for source in sorted(archive_paths):
        raw = source.read_bytes()
        name = source.parent.parent.name
        destination = pinned / f'{name}.json'
        destination.write_bytes(raw)
        metadata = json.loads(raw)
        sources[name] = {'manifest': str(destination), 'archive_manifest': str(source),
                         'sha256': hashlib.sha256(raw).hexdigest(),
                         'licence': metadata.get('licence', metadata.get('license')),
                         'credit': metadata.get('credit')}
    tile_bytes = np.array([record['bytes'] for record in tiles.values()])
    layer_bytes = {filename: {'total': sum(t['files'][filename]['bytes'] for t in tiles.values()),
                             'min': min(t['files'][filename]['bytes'] for t in tiles.values()),
                             'median': int(np.median([t['files'][filename]['bytes'] for t in tiles.values()])),
                             'max': max(t['files'][filename]['bytes'] for t in tiles.values())}
                   for filename in FILES}
    totals = {'tiles': len(tiles), 'bytes': int(tile_bytes.sum()),
              'bytes_per_tile': {'min': int(tile_bytes.min()), 'median': int(np.median(tile_bytes)),
                                 'p95': int(np.percentile(tile_bytes, 95)), 'max': int(tile_bytes.max())},
              'layer_bytes': layer_bytes, 'buildings': reports['buildings']['totals'],
              'trees': reports['objects']['trees'],
              'building_tiles_above_1_5_MB': [name for name, tile in tiles.items() if tile['files']['buildings.glb']['bytes'] > 1500000]}
    manifest = {'written_by': 'AI, GPT-6 Astra, 2026-10-26',
                'built_at': datetime.now(timezone.utc).isoformat(),
                'crs': {'horizontal': 'EPSG:28992', 'vertical': 'EPSG:5709', 'compound': 'EPSG:7415'},
                'grid': {'size_m': 1000, 'tile_name': 'x{xmin}_y{ymin}',
                         'gltf_axes': {'X': 'RD east minus tile xmin', 'Y': 'NAP metres', 'Z': 'negative RD north offset from tile ymin'}},
                'area': {'GM0599': {'bounds_rd': index['bounds_rd'], 'boundary': 'tile-index.json',
                                   'selection': 'Every 1000 m RD grid tile intersecting the exact municipality polygon'}},
                'class_legend': reports['surfaces']['class_legend'],
                'raster': {'size_px': [1000, 1000], 'resolution_m': 1, 'north_up': True,
                           'channels': {'R': 'surface class', 'G': {'1': 'tram rail', '2': 'train or metro rail'}, 'B': 0, 'A': 255}},
                'code_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                'code_note': 'Overview implementation is uncommitted as requested; pipeline/overview is the rebuild source.',
                'code_source_sha256': {str(path.relative_to(Path.cwd())): hashlib.sha256(path.read_bytes()).hexdigest()
                                       for path in sorted([*Path('pipeline/overview').resolve().glob('*.py'),
                                                           Path('pipeline/buildings/build.py').resolve(),
                                                           Path('pipeline/buildings/transform.py').resolve(),
                                                           Path('pipeline/buildings/objects.py').resolve()])},
                'sources': sources, 'tiles': tiles, 'totals': totals,
                'reports': {name: f'{name}-report.json' for name in reports},
                'coverage_report': 'imagery-coverage-report.json',
                'coverage_findings': 'coverage-findings.json',
                'rebuild_command': 'devenv shell -- python pipeline/overview/rebuild.py'}
    (SCENE / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    (SCENE / 'summary.json').write_text(json.dumps(totals, indent=2))
    print(json.dumps(totals, indent=2), flush=True)


if __name__ == '__main__':
    main()
