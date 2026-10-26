"""Overview orthophotos and municipal tree points. Written by AI, GPT-6, 2026-10-26."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import threading
import time
from urllib.parse import urlencode

import numpy as np
from PIL import Image
import requests
from shapely.geometry import shape, Point

ROOT = Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
SCENE = ROOT / 'scene/overview-v1'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'buildings'))
from objects import decoded, select_contents, parts, read_instances
from transform import ecef_to_rdnap


class Archive:
    def __init__(self, dataset, credit, licence):
        self.directory = ROOT / 'sources' / dataset / datetime.date.today().isoformat()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.directory / 'manifest.json'
        self.files = json.loads(self.manifest_path.read_text()).get('files', []) if self.manifest_path.exists() else []
        self.records = {r['path']: r for r in self.files}
        self.metadata = {'dataset': dataset, 'credit': credit, 'licence': licence}
        self.lock = threading.Lock()

    def get(self, url, relative):
        path = self.directory / relative
        with self.lock:
            record = self.records.get(relative)
        if path.exists() and record:
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() == record['sha256']:
                return raw
            raise ValueError(f'Archived source hash mismatch: {path}')
        for attempt in range(4):
            try:
                response = requests.get(url, timeout=120)
                response.raise_for_status()
                raw = response.content
                break
            except requests.RequestException:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        record = {'path': relative, 'url': response.url, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw), 'fetched_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'content_type': response.headers.get('Content-Type'), 'last_modified': response.headers.get('Last-Modified')}
        with self.lock:
            self.records[relative] = record
            self.save()
        return raw

    def save(self):
        temporary = self.manifest_path.with_suffix('.tmp')
        temporary.write_text(json.dumps({**self.metadata, 'files': sorted(self.records.values(), key=lambda r: r['path'])}, indent=2) + '\n')
        temporary.replace(self.manifest_path)

    def reference(self):
        raw = self.manifest_path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        snapshot = self.directory / f'manifest-{digest}.json'
        if not snapshot.exists():
            snapshot.write_bytes(raw)
        return {'source_manifest': str(snapshot), 'source_manifest_sha256': digest}


def imagery(index, workers):
    archive = Archive('overview-ortho-2026', 'Samenwerkingsverband Beeldmateriaal / PDOK — Luchtfoto 2026', 'CC BY 4.0')
    def tile(item):
        tile_id, record = item
        bounds = record['bounds_rd']
        parameters = {'SERVICE': 'WMS', 'VERSION': '1.3.0', 'REQUEST': 'GetMap', 'LAYERS': '2026_orthoHR', 'STYLES': '', 'CRS': 'EPSG:28992', 'BBOX': ','.join(map(str, bounds)), 'WIDTH': 1000, 'HEIGHT': 1000, 'FORMAT': 'image/jpeg'}
        url = 'https://service.pdok.nl/hwh/luchtfotorgb/wms/v1_0?' + urlencode(parameters)
        raw = archive.get(url, tile_id + '.jpg')
        image = Image.open(io.BytesIO(raw))
        if image.size != (1000, 1000) or image.format != 'JPEG':
            raise ValueError(f'Unexpected WMS image {tile_id}: {image.size} {image.format}')
        directory = SCENE / 'tiles' / tile_id
        directory.mkdir(parents=True, exist_ok=True)
        (directory / 'ortho.jpg').write_bytes(raw)
        pixels = np.asarray(image)
        return tile_id, {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'white_pixel_fraction': float(np.all(pixels >= 250, axis=2).mean()), 'black_pixel_fraction': float(np.all(pixels <= 3, axis=2).mean())}
    results = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for future in as_completed([executor.submit(tile, item) for item in index['tiles'].items()]):
            tile_id, record = future.result()
            results[tile_id] = record
            if len(results) % 25 == 0:
                print(f'ortho {len(results)}/{len(index["tiles"])}', flush=True)
    report = {'source': 'PDOK 2026_orthoHR WMS', 'resolution_m': 1, 'source_crs': 'EPSG:28992', 'method': 'Direct 1000 by 1000 WMS request for each complete 1000 m RD tile; exact JPEG response copied without re-encoding.', 'tiles': results, 'source_white_gaps': [tile_id for tile_id, record in sorted(results.items()) if record['white_pixel_fraction'] > 0.9], 'limitations': ['PDOK WMS returns white no-imagery areas offshore beyond aerial acquisition coverage. Small rectangular white gaps also occur in waterways; original response pixels retained.'], **archive.reference()}
    (SCENE / 'imagery-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'ortho complete: {len(results)} tiles', flush=True)


def trees(index, workers):
    archive = Archive('overview-trees', 'Gemeente Rotterdam', 'Public domain')
    base = 'https://www.3drotterdam.nl/datasource-data/b9294d5b-79e0-4744-ac88-b61e3e90d5bc/'
    tileset = json.loads(decoded(archive.get(base + 'tileset.json', 'tileset.json')))
    boundary = shape(index['boundary_rd'])
    contents = select_contents(tileset, boundary.bounds)
    transform = ecef_to_rdnap()
    def read_content(item):
        uri, matrix = item
        raw = decoded(archive.get(base + uri, uri))
        records = []
        for part_index, part in enumerate(parts(raw)):
            if part[:4] != b'i3dm':
                raise ValueError(f'Unexpected tree content {uri}: {part[:4]}')
            rows, model = read_instances(part)
            positions = np.array([row[0] for row in rows])
            positions = (matrix @ np.column_stack([positions, np.ones(len(positions))]).T).T[:, :3]
            rd = np.array(transform.transform(positions[:, 0], positions[:, 1], positions[:, 2])).T
            for instance, ((_, source_id, attributes), point) in enumerate(zip(rows, rd)):
                if attributes.get('tree_part') != 'stam':
                    continue
                x, y, z = map(float, point)
                if not all(math.isfinite(value) for value in point):
                    raise ValueError(f'Nonfinite source tree position {uri} {source_id}')
                if not boundary.covers(Point(x, y)):
                    continue
                tile_id = f'x{math.floor(x/1000)*1000}_y{math.floor(y/1000)*1000}'
                if tile_id not in index['tiles']:
                    raise ValueError(f'Tree outside selected tile grid: {tile_id}')
                record = {'x': round(x, 4), 'y': round(y, 4), 'z': round(z, 4), 'height_m': attributes.get('height'), 'crown_m': attributes.get('crownDiameter'), 'source_id': source_id, 'source': {'dataset': 'trees', 'tile': uri, 'part': part_index, 'instance': instance, 'creation_date': attributes.get('creationDate')}}
                records.append((str(attributes.get('Boom_id', source_id)), tile_id, record))
        return records
    unique = {}
    duplicates = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for done, future in enumerate(as_completed([executor.submit(read_content, item) for item in contents]), 1):
            for key, tile_id, record in future.result():
                if key in unique:
                    duplicates += 1
                    # Deterministic source selection independent of concurrent completion.
                    if unique[key][1]['source_id'] <= record['source_id']:
                        continue
                unique[key] = (tile_id, record)
            if done % 50 == 0:
                print(f'trees {done}/{len(contents)}', flush=True)
    tiles = {tile_id: {'trees': [], 'lamps': []} for tile_id in index['tiles']}
    for tile_id, record in unique.values():
        tiles[tile_id]['trees'].append(record)
    counts = {}
    for tile_id, objects in tiles.items():
        objects['trees'].sort(key=lambda r: r['source_id'])
        directory = SCENE / 'tiles' / tile_id
        directory.mkdir(parents=True, exist_ok=True)
        raw = (json.dumps(objects, separators=(',', ':')) + '\n').encode()
        (directory / 'objects.json').write_bytes(raw)
        counts[tile_id] = {'trees': len(objects['trees']), 'lamps': 0, 'bytes': len(raw)}
    report = {'trees': len(unique), 'source_tiles': len(contents), 'duplicates_collapsed': duplicates, 'tiles': counts, 'method': 'One tree_part=stam instance per Boom_id; source instance positions transformed from municipal ECEF into RD. Municipal exporter encodes NAP as geodetic height: preserve decoded height using existing detailed transform. Source height and crownDiameter retained, including zero or null dimensions. Only points inside exact GM0599 retained; no inferred trees. No mesh prototypes needed for point extraction.', 'limitations': ['Municipal managed-tree register does not represent all privately owned trees or complete forest canopy.', 'No lamps requested for overview.'], **archive.reference()}
    (SCENE / 'objects-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'trees complete: {len(unique)} points, {len(tiles)} tile files', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--layer', choices=['ortho', 'trees', 'all'], default='all')
    parser.add_argument('--workers', type=int, default=6)
    args = parser.parse_args()
    index = json.loads((SCENE / 'tile-index.json').read_text())
    if args.layer in ('ortho', 'all'):
        imagery(index, args.workers)
    if args.layer in ('trees', 'all'):
        trees(index, min(args.workers, 4))


if __name__ == '__main__':
    main()
