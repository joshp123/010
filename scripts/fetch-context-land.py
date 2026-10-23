#!/usr/bin/env python3
"""Build coarse surrounding land; requires existing Shapely and pyproj.

Written by AI on 2026-10-24 by model GPT-6.
Natural Earth 1:10 million is context, not measured city geometry.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

from pyproj import Transformer
from shapely.geometry import box, mapping, shape
from shapely.ops import transform, unary_union

PROJECT = Path(__file__).resolve().parents[1]
CACHE = PROJECT / 'work' / 'data-cache'
OUTPUT = PROJECT / 'dist' / 'data' / 'context-land.geojson'
SOURCE_COMMIT = 'ace5fed0eaf3c6c03c951e75b439ba8fffbc218e'
SOURCE_URL = f'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{SOURCE_COMMIT}/geojson/ne_10m_land.geojson'
SOURCE_PAGE = 'https://www.naturalearthdata.com/downloads/10m-physical-vectors/10m-land/'
LICENSE_URL = 'https://www.naturalearthdata.com/about/terms-of-use/'
BOUNDS = [3.3, 51.4, 5.2, 52.4]
SIMPLIFICATION_METRES = 40


def cached_download(filename, url):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / filename
    metadata = path.with_suffix(path.suffix + '.source.json')
    if not path.exists():
        with urlopen(url, timeout=90) as response:
            raw = response.read()
        path.write_bytes(raw)
        metadata.write_text(json.dumps({
            'url': url,
            'retrievedAt': datetime.now(timezone.utc).isoformat(),
            'sha256': hashlib.sha256(raw).hexdigest(),
        }, indent=2) + '\n')
    return path.read_bytes(), json.loads(metadata.read_text())


raw, provenance = cached_download('natural-earth-10m-land.geojson', SOURCE_URL)
cached_download('natural-earth-LICENSE.md', f'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{SOURCE_COMMIT}/LICENSE.md')
collection = json.loads(raw)
clip = box(*BOUNDS)
polygons = []
for feature in collection['features']:
    polygon = shape(feature['geometry'])
    if polygon.intersects(clip):
        polygons.append(polygon.intersection(clip))
land = unary_union(polygons)
to_rd = Transformer.from_crs(4326, 28992, always_xy=True).transform
to_geographic = Transformer.from_crs(28992, 4326, always_xy=True).transform
land = transform(to_geographic, transform(to_rd, land).simplify(SIMPLIFICATION_METRES, preserve_topology=True)).intersection(clip)

# Rotterdam owns its complete administrative area, including source water.
# Subtract the original municipality after simplification to protect that area
# while keeping one continuous surrounding land source.
boundary_bytes = (PROJECT / 'dist' / 'data' / 'municipality.geojson').read_bytes()
boundary_collection = json.loads(boundary_bytes)
municipality = unary_union([shape(feature['geometry']) for feature in boundary_collection['features'] if feature['properties'].get('identificatie') == 'GM0599'])
if municipality.is_empty:
    raise ValueError('Rotterdam GM0599 is missing from municipality.geojson')
land = land.difference(municipality)
if land.is_empty or not land.is_valid:
    raise ValueError('Surrounding land geometry is empty or invalid')
output = {
    'type': 'FeatureCollection',
    'features': [{'type': 'Feature', 'properties': {'kind': 'land'}, 'geometry': mapping(land)}],
    'source': SOURCE_URL,
    'sourcePage': SOURCE_PAGE,
    'sourceCommit': SOURCE_COMMIT,
    'sourceSha256': provenance['sha256'],
    'retrievedAt': provenance['retrievedAt'],
    'sourceScale': '1:10 million',
    'bounds': BOUNDS,
    'excludedMunicipality': 'GM0599',
    'excludedBoundarySource': boundary_collection['source'],
    'excludedBoundarySha256': hashlib.sha256(boundary_bytes).hexdigest(),
    'simplificationMetres': SIMPLIFICATION_METRES,
    'license': 'Public domain',
    'licenseUrl': LICENSE_URL,
    'attribution': 'Made with Natural Earth.',
    'purpose': 'Continuous coarse land outside Rotterdam; the whole municipality, including its water, is excluded.',
}
OUTPUT.write_text(json.dumps(output, separators=(',', ':')) + '\n')
print(json.dumps({'output': str(OUTPUT.relative_to(PROJECT)), 'bytes': OUTPUT.stat().st_size, 'geometryType': land.geom_type, 'valid': land.is_valid, 'excludedMunicipality': 'GM0599'}))
