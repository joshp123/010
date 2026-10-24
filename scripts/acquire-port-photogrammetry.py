#!/usr/bin/env python3
"""Written by AI, gpt-6-astra, 2026-10-24. Retain a real municipal port mesh and its source hierarchy."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import urlopen

BASE = 'https://www.3drotterdam.nl/3dmesh/datasource-data/'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--region', choices=['Rotterdam_West'], default='Rotterdam_West')
    parser.add_argument('--lon', type=float, required=True)
    parser.add_argument('--lat', type=float, required=True)
    parser.add_argument('--error', type=float, default=3)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--render', action='store_true')
    args = parser.parse_args()
    raw = args.output / 'raw'
    raw.mkdir(parents=True, exist_ok=True)
    evidence, inaccessible, candidates = {}, [], []
    longitude, latitude = math.radians(args.lon), math.radians(args.lat)
    root_url = BASE + args.region + '/tileset.json'

    def retain(url):
        relative = url.removeprefix(BASE + args.region + '/')
        path = raw / relative.replace('/', '_')
        if not path.exists():
            path.write_bytes(urlopen(url, timeout=30).read())
        data = path.read_bytes()
        evidence[url] = {'url': url, 'file': str(path.relative_to(args.output)),
                         'sha256': hashlib.sha256(data).hexdigest()}
        return data

    def inspect(tile, document_url):
        bounds = tile['boundingVolume']['region']
        if not (bounds[0] <= longitude <= bounds[2] and bounds[1] <= latitude <= bounds[3]):
            return
        content = tile.get('content', {}).get('uri')
        if content and content.endswith('.json'):
            url = urljoin(document_url, content)
            try:
                inspect(json.loads(retain(url))['root'], url)
            except HTTPError as error:
                if error.code != 403:
                    raise
                inaccessible.append({'url': url, 'status': error.code})
            return
        if content and content.endswith('.glb'):
            candidates.append((tile['geometricError'], urljoin(document_url, content), tile))
        if tile.get('geometricError', math.inf) > args.error:
            for child in tile.get('children', []):
                inspect(child, document_url)

    inspect(json.loads(retain(root_url))['root'], root_url)
    # The public West root also includes untextured coarse geometry in branch 1.
    textured = [item for item in candidates if '/2/' in item[1]]
    error, url, tile = min(textured, key=lambda item: item[0])
    retain(url)
    local_tile = {key: value for key, value in tile.items() if key != 'children'}
    local_tile['content'] = {'uri': evidence[url]['file']}
    (args.output / 'tileset.json').write_text(json.dumps({
        'asset': {'version': '1.1'}, 'geometricError': error, 'root': local_tile
    }, indent=2) + '\n')
    (args.output / 'acquisition.json').write_text(json.dumps({
        'writtenBy': 'AI, gpt-6-astra, 2026-10-24',
        'location': [args.lon, args.lat], 'selectedGeometricErrorMetres': error,
        'sourceRole': 'Observed textured surface including ground; no BAG/object identities. Offline interpretation input, not an automatic building replacement.',
        'photographyCaptureDate': 'Not established',
        'license': 'Mesh-specific terms not established; do not infer from the older building catalogue.',
        'inaccessibleFinerSources': inaccessible,
        'sourceEvidence': list(evidence.values())
    }, indent=2) + '\n')
    print(url)
    if args.render:
        render_source(args.output, evidence[url]['file'])


def render_source(output, source_file):
    import importlib.util
    import struct
    import numpy as np

    helper = Path(__file__).with_name('inspect-current-building-evidence.py')
    specification = importlib.util.spec_from_file_location('building_source', helper)
    renderer = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(renderer)
    renderer.OUT = output
    source = (output / source_file).read_bytes()
    document_length = struct.unpack_from('<I', source, 12)[0]
    document = json.loads(source[20:20 + document_length])
    binary = bytearray(source[28 + document_length:])
    # TerraExplorer uses the glTF ECEF frame (X, Z, -Y). Rotate only the
    # temporary rasterization buffer into a local tangent frame.
    up = np.asarray(document['nodes'][0]['translation'])
    up /= np.linalg.norm(up)
    east = np.cross([0, 1, 0], up)
    east /= np.linalg.norm(east)
    north = np.cross(up, east)
    local_basis = np.array([east, up, -north]).T
    positions = {primitive['attributes']['POSITION']
                 for mesh in document['meshes'] for primitive in mesh['primitives']}
    for index in positions:
        accessor = document['accessors'][index]
        view = document['bufferViews'][accessor['bufferView']]
        vertices = np.ndarray((accessor['count'], 3), dtype='<f4', buffer=binary,
                              offset=view.get('byteOffset', 0) + accessor.get('byteOffset', 0),
                              strides=(view.get('byteStride', 12), 4))
        vertices[:] = vertices @ local_basis
    renderer.render(document, binary, 'source-view.png', [1, .8, 1])


if __name__ == '__main__':
    main()
