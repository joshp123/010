"""Written by AI on 2026-10-26 by model GPT-6 Astra. Exact GM0599 overview grid."""
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import requests
from pyproj import Transformer
from shapely.geometry import box, mapping, shape
from shapely.ops import transform

ROOT = Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
SCENE = ROOT / 'scene/overview-v1'
ARCHIVE = ROOT / 'sources/overview-boundary/2026-10-26'


def build_index():
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    SCENE.mkdir(parents=True, exist_ok=True)
    source = ARCHIVE / 'municipality.geojson'
    url = 'https://api.pdok.nl/kadaster/brk-bestuurlijke-gebieden/ogc/v1/collections/gemeentegebied/items?naam=Rotterdam&f=json'
    if not source.exists():
        response = requests.get(url, timeout=120)
        response.raise_for_status()
        source.write_bytes(response.content)
        (ARCHIVE / 'manifest.json').write_text(json.dumps({
            'dataset': 'Kadaster / PDOK Bestuurlijke Gebieden GM0599',
            'licence': 'CC BY 4.0', 'credit': 'Kadaster / PDOK',
            'files': [{'path': source.name, 'url': response.url,
                       'sha256': hashlib.sha256(response.content).hexdigest(),
                       'bytes': len(response.content),
                       'fetched_at': datetime.now(timezone.utc).isoformat()}]
        }, indent=2))
    features = json.loads(source.read_text())['features']
    municipality = next(feature for feature in features if feature['properties']['identificatie'] == 'GM0599')
    boundary = transform(Transformer.from_crs(4326, 28992, always_xy=True).transform,
                         shape(municipality['geometry']))
    tiles = {}
    xmin, ymin, xmax, ymax = boundary.bounds
    for x in range(math.floor(xmin / 1000) * 1000, math.ceil(xmax / 1000) * 1000, 1000):
        for y in range(math.floor(ymin / 1000) * 1000, math.ceil(ymax / 1000) * 1000, 1000):
            bounds = [x, y, x + 1000, y + 1000]
            if boundary.intersects(box(*bounds)):
                tiles[f'x{x}_y{y}'] = {'bounds_rd': bounds}
    result = {'municipality': 'GM0599', 'grid': {'size_m': 1000},
              'boundary_rd': mapping(boundary), 'bounds_rd': list(boundary.bounds),
              'boundary_source_manifest': str(ARCHIVE / 'manifest.json'), 'tiles': tiles}
    (SCENE / 'tile-index.json').write_text(json.dumps(result, indent=2))
    print(f'{len(tiles)} tiles; RD bounds {boundary.bounds}', flush=True)
    return result


if __name__ == '__main__':
    build_index()
