"""AHN network elevations. Written by AI on 2026-10-26 by model GPT-6 Astra.

Run ``devenv shell -- python pipeline/networks/heights.py`` to archive M1.
No interpolation of missing cells: DTM cell first, DSM cell second, then None.
For an explicit bridge mask only, DSM uses its local 2nd percentile in a 6 m
square to reject suspension cables. This is a measured local deck estimate,
not a survey; validated against the Erasmusbrug and Willemsbrug profiles.
The graph builder owns tunnel tagging and applies the stated -12 m assumption.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import urlencode

import numpy as np
from PIL import Image
import requests

ROOT = Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
CACHE = ROOT / 'sources/network-ahn/2026-10-26'
BOUNDS = (89750, 434750, 96500, 438000)
ENDPOINT = 'https://service.pdok.nl/rws/ahn/wcs/v1_0'
CELL_SIZE = 0.5
BLOCK_SIZE = 1000


def blocks():
    for x in range(89000, 97000, BLOCK_SIZE):
        for y in range(434000, 438000, BLOCK_SIZE):
            yield x, y


def coverage_url(coverage, x, y):
    return ENDPOINT + '?' + urlencode({
        'SERVICE': 'WCS', 'VERSION': '1.0.0', 'REQUEST': 'GetCoverage',
        'COVERAGE': coverage, 'CRS': 'EPSG:28992',
        'BBOX': f'{x},{y},{x+BLOCK_SIZE},{y+BLOCK_SIZE}',
        'WIDTH': 2000, 'HEIGHT': 2000, 'FORMAT': 'image/tiff'})


def archive():
    CACHE.mkdir(parents=True, exist_ok=True)
    manifest_path = CACHE / 'manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
        'dataset': 'PDOK AHN DTM and DSM 0.5 m', 'credit': 'AHN / Rijkswaterstaat / PDOK',
        'license': 'CC0-1.0', 'license_evidence': 'capabilities.xml: ows:AccessConstraints',
        'horizontal_crs': 'EPSG:28992', 'vertical_datum': 'NAP metres',
        'bounds_rd': list(BOUNDS), 'resolution_m': CELL_SIZE, 'files': {}}
    capabilities_url = ENDPOINT + '?service=WCS&request=GetCapabilities'
    jobs = [('capabilities.xml', capabilities_url)] + [
        (f'{coverage}-{x}-{y}.tif', coverage_url(coverage, x, y))
        for coverage in ('dtm_05m', 'dsm_05m') for x, y in blocks()]

    def fetch(job):
        name, url = job
        path = CACHE / name
        if path.exists() and name in manifest['files']:
            raw = path.read_bytes()
            entry = manifest['files'][name]
            if entry['sha256'] != hashlib.sha256(raw).hexdigest() or entry['url'] != url:
                raise ValueError(f'Cached source differs: {path}')
            return name, entry
        response = requests.get(url, timeout=240)
        response.raise_for_status()
        raw = response.content
        if name.endswith('.tif'):
            if raw[:4] not in (b'II*\x00', b'MM\x00*'):
                raise ValueError(f'Not a TIFF: {url}: {raw[:200]!r}')
        elif b'creativecommons.org/publicdomain/zero/1.0' not in raw:
            raise ValueError('AHN service no longer declares CC0')
        path.write_bytes(raw)
        return name, {'url': url, 'bytes': len(raw),
                      'sha256': hashlib.sha256(raw).hexdigest(),
                      'fetched_at': datetime.now(timezone.utc).isoformat()}

    with ThreadPoolExecutor(max_workers=4) as pool:
        for name, entry in pool.map(fetch, jobs):
            manifest['files'][name] = entry
            manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
            print(name, entry['bytes'], flush=True)
    return manifest


@lru_cache(maxsize=64)
def read_block(coverage, x, y):
    path = CACHE / f'{coverage}-{x}-{y}.tif'
    with Image.open(path) as image:
        values = np.array(image, dtype=np.float32)
        nodata = float(image.tag_v2.get(42113, '3.4028234663852886e+38').strip('\x00'))
        scale = image.tag_v2[33550]
        tiepoint = image.tag_v2[33922]
    return values, nodata, scale, tiepoint


class HeightSampler:
    """Read archived 0.5 m AHN cells. Coordinates and elevations are RD/NAP m."""
    def sample_coverage(self, x, y, coverage):
        if not (BOUNDS[0] <= x <= BOUNDS[2] and BOUNDS[1] <= y <= BOUNDS[3]):
            return None
        block_x = math.floor(x / BLOCK_SIZE) * BLOCK_SIZE
        block_y = math.floor(math.nextafter(y, -math.inf) / BLOCK_SIZE) * BLOCK_SIZE
        values, nodata, scale, tiepoint = read_block(coverage, block_x, block_y)
        column = math.floor((x - tiepoint[3]) / scale[0])
        row = math.floor((tiepoint[4] - y) / scale[1])
        if not (0 <= row < values.shape[0] and 0 <= column < values.shape[1]):
            return None
        value = float(values[row, column])
        if not math.isfinite(value) or value == nodata or abs(value) > 10000:
            return None
        return round(value, 1)

    def sample(self, x, y, bridge=False):
        value = self.sample_coverage(x, y, 'dtm_05m')
        if value is not None:
            return value, 'dtm_05m'
        if bridge:
            values = [self.sample_coverage(x+dx, y+dy, 'dsm_05m')
                      for dx in np.arange(-3, 3.1, CELL_SIZE)
                      for dy in np.arange(-3, 3.1, CELL_SIZE)]
            values = [value for value in values if value is not None]
            if values:
                return round(float(np.percentile(values, 2)), 1), 'dsm_05m_bridge_p02_3m'
        else:
            value = self.sample_coverage(x, y, 'dsm_05m')
            if value is not None:
                return value, 'dsm_05m'
        return None, 'nodata'

    def sample_many(self, coordinates, bridge=False):
        return [self.sample(x, y, bridge=bridge) for x, y in coordinates]


if __name__ == '__main__':
    archive()
