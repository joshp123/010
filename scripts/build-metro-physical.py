#!/usr/bin/env python3
"""Extract retained BRT metro physical forms; no inferred tunnel/depth data."""
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / 'source-data/transport-network.geojson.gz'
network = json.loads(gzip.decompress(source.read_bytes()))
segments = []
for feature in network['features']:
    properties = feature['properties']
    if properties.get('typespoorbaan') not in ('metro', 'sneltram') or properties.get('status') != 'in gebruik':
        continue
    form = properties.get('fysiekvoorkomen', '')
    classification = 'tunnel' if form == 'in tunnel' else 'bridge-covered' if 'brug' in form and 'overkluisd' in form else 'bridge' if 'brug' in form else 'covered' if form == 'overkluisd' else 'unclassified'
    segments.append({'id': properties['lokaal_id'], 'form': classification, 'relativeLevel': properties['hoogteniveau'], 'coordinates': feature['geometry']['coordinates']})
output = {'version': 1, 'source': network['sourceCollections']['spoorbaandeel_lijn'], 'attribution': network['attribution'], 'license': network['license'], 'sourceSha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'simplificationMetres': network['simplificationMetres'], 'depth': None, 'segments': segments}
encoded = json.dumps(output, separators=(',', ':')).encode()
(ROOT / 'public/data/transit/metro-physical.json.gz').write_bytes(gzip.compress(encoded, mtime=0))
print(json.dumps({'segments': len(segments), 'forms': dict(Counter(segment['form'] for segment in segments)), 'gzipBytes': len(gzip.compress(encoded, mtime=0)), 'sourceSha256': output['sourceSha256']}))
