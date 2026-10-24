#!/usr/bin/env python3
"""Inline native external tileset metadata; preserve every wrapper/root transform.
All content geometry remains at its original absolute public source URL.
"""
import copy
import datetime
import gzip
import hashlib
import json
from pathlib import Path
from urllib.parse import urljoin, urlsplit
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'source-data/building-index'
OUTPUT = ROOT / 'public/data/building-index'
SOURCE_URL = 'https://www.3drotterdam.nl/datasource-data/8b5d0ded-a222-4e44-bc70-2992bc2192fc/tileset.json'


def build():
    SOURCE.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest_path = SOURCE / 'provenance.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {'source': SOURCE_URL, 'sources': []}
    retained = {entry['url']: entry for entry in manifest['sources']}
    def fetch(url):
        if url in retained:
            return json.loads(gzip.decompress((SOURCE / retained[url]['file']).read_bytes()))
        request = urllib.request.Request(url, headers={'User-Agent': '010 Rotterdam miniature metadata preparation', 'Accept-Encoding': 'gzip'})
        with urllib.request.urlopen(request, timeout=60) as response:
            wire = response.read()
            raw = gzip.decompress(wire) if wire[:2] == b'\x1f\x8b' else wire
            filename = f'source-{len(retained):02}.json.gz'
            (SOURCE / filename).write_bytes(gzip.compress(raw, mtime=0))
            entry = {'url': url, 'file': filename, 'acquiredAt': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'sha256': hashlib.sha256(raw).hexdigest(), 'decodedBytes': len(raw), 'wireBytes': len(wire), 'headers': {name:response.headers.get(name) for name in ('ETag','Last-Modified','Content-Type','Content-Encoding')}}
            retained[url] = entry
            manifest['sources'].append(entry)
            manifest_path.write_text(json.dumps(manifest, indent=2)+'\n')
            return json.loads(raw)
    original = fetch(SOURCE_URL)
    output = copy.deepcopy(original)
    expected_axis = original.get('asset', {}).get('gltfUpAxis', 'Y').upper()
    inlined = 0
    geometry_urls = []
    def inline(node, base):
        nonlocal inlined
        content = node.get('content')
        if content:
            field = 'uri' if 'uri' in content else 'url'
            url = urljoin(base, content[field])
            if urlsplit(url).path.endswith('.json'):
                external = fetch(url)
                if external.get('asset', {}).get('gltfUpAxis', 'Y').upper() != expected_axis:
                    raise ValueError('External tileset up axis differs; explicit composition required')
                if external.get('extensionsRequired') or external.get('extensionsUsed'):
                    raise ValueError('External tileset extensions require explicit composition')
                # Keep the original wrapper node intact except its external
                # content pointer. Its transform still parents the full external
                # root, including the external root's own transform and bounds.
                del node['content']
                external_root = copy.deepcopy(external['root'])
                inline(external_root, url)
                node.setdefault('children', []).append(external_root)
                inlined += 1
            else:
                content[field] = url
                geometry_urls.append(url)
        for child in node.get('children', []):
            # Inlined descendants already have absolute geometry URLs; walking
            # again is harmless and does not remove any wrapper hierarchy.
            inline(child, base)
    inline(output['root'], SOURCE_URL)
    raw = json.dumps(output, separators=(',', ':')).encode()
    path = OUTPUT / 'tileset.json'
    path.write_bytes(raw)
    manifest.update({'outputSha256': hashlib.sha256(raw).hexdigest(), 'outputBytes': len(raw), 'outputGzipBytes': len(gzip.compress(raw,mtime=0)), 'inlinedExternalIndexes': inlined, 'uniqueGeometryUrls': len(set(geometry_urls)), 'processing': 'External JSON content pointer replaced by external root as child; all source wrapper/root fields, transforms, bounds, geometric errors and refinement retained. Geometry content URLs made absolute. No geometry asset changed.', 'sourceLicense': 'Existing 3D Rotterdam native building source terms and attribution remain unchanged.'})
    manifest_path.write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps({key:value for key,value in manifest.items() if key!='sources'}, indent=2))


if __name__ == '__main__':
    build()
