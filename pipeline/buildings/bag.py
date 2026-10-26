"""Written by AI on 2026-10-26 by model GPT-6.1 Sol.

Archive public PDOK BAG facts and follow every pand-to-VBO link, including
links outside the requested area. No geometry inference or storey estimates.
"""
import argparse
import concurrent.futures
import datetime
import hashlib
import gzip
import fcntl
import json
from pathlib import Path
import threading
import time
import struct
from collections import Counter
from urllib.parse import urlencode

import requests
from shapely.geometry import shape, Point

BASE = 'https://api.pdok.nl/kadaster/bag/ogc/v2'
RD = 'http://www.opengis.net/def/crs/EPSG/0/28992'
DIRECTORY = Path(__file__).resolve().parents[3] / 'sources/bag/2026-10-26'
M1 = (89750, 434750, 96500, 438000)


class Archive:
    def __init__(self):
        DIRECTORY.mkdir(parents=True, exist_ok=True)
        self.manifest_path = DIRECTORY / 'manifest.json'
        self.files = {}
        if self.manifest_path.exists():
            self.files = {record['url']: record for record in json.loads(self.manifest_path.read_text())['files']}
        self.lock = threading.Lock()

    def get(self, url):
        filename = hashlib.sha256(url.encode()).hexdigest() + '-wire.json'
        target = DIRECTORY / filename
        if not target.exists():
            for attempt in range(5):
                try:
                    response = requests.get(url, timeout=90, stream=True, headers={'Accept-Encoding': 'identity'})
                    response.raise_for_status()
                    raw = response.raw.read(decode_content=False)
                    break
                except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as error:
                    if isinstance(error, requests.HTTPError) and error.response.status_code not in (429, 500, 502, 503, 504):
                        raise
                    if attempt == 4:
                        raise
                    time.sleep(2 ** attempt)
            json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)
            target.write_bytes(raw)
        raw = target.read_bytes()
        with self.lock:
            previous = self.files.get(url)
            self.files[url] = {
                'path': filename, 'url': url, 'bytes': len(raw),
                'sha256': hashlib.sha256(raw).hexdigest(),
                'fetched_at': datetime.datetime.fromtimestamp(target.stat().st_mtime, datetime.timezone.utc).isoformat(),
                'archive_representation': 'Exact response body bytes; Accept-Encoding identity requested; automatic decoding disabled',
            }
            if previous and previous['path'] != filename:
                self.files[url]['initial_decoded_entity'] = previous
            elif previous and 'initial_decoded_entity' in previous:
                self.files[url]['initial_decoded_entity'] = previous['initial_decoded_entity']
            self.save()
        return json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw), self.files[url]

    def save(self):
        manifest = {
            'dataset': 'Basisregistratie Adressen en Gebouwen (BAG), PDOK OGC API v2',
            'licence': 'Public Domain Mark 1.0',
            'licence_url': 'https://creativecommons.org/publicdomain/mark/1.0/',
            'credit': 'Kadaster (LV-BAG) / PDOK; municipal BAG source holders',
            'source': BASE,
            'files': sorted(self.files.values(), key=lambda record: record['url']),
        }
        self.manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')


def collection_url(collection, bounds):
    params = {'f': 'json', 'limit': 1000, 'bbox': ','.join(str(value) for value in bounds), 'bbox-crs': RD, 'crs': RD}
    return f'{BASE}/collections/{collection}/items?' + urlencode(params)


def pages(archive, url):
    while url:
        document, provenance = archive.get(url)
        for feature in document['features']:
            yield feature, provenance
        url = next((link['href'] for link in document.get('links', []) if link['rel'] == 'next'), None)


def purposes(value):
    if value is None or value == '':
        return []
    if isinstance(value, list):
        return sorted(set(purpose for item in value for purpose in purposes(item)))
    return sorted(set(part.strip() for part in value.replace(';', ',').split(',') if part.strip()))


def _load_facts(bounds, building_ids=()):
    """Return pand16id -> facts. Exceptions mean unavailable, never empty use.

    Optional building_ids adds exact-ID lookups for scene buildings absent from
    the spatial query. Missing current BAG records receive explicit unavailable
    coverage rather than fabricated factual values.
    """
    archive = Archive()
    archive.get(BASE + '?f=json')
    archive.get(BASE + '/collections/pand?f=json')
    archive.get(BASE + '/collections/verblijfsobject?f=json')
    pand_records = dict((feature['properties']['identificatie'], (feature, provenance)) for feature, provenance in pages(archive, collection_url('pand', bounds)))
    missing_ids = set(map(str, building_ids)) - set(pand_records)
    absent_records = {}
    for identifier in sorted(missing_ids):
        url = BASE + '/collections/pand/items?' + urlencode({'f': 'json', 'identificatie': identifier, 'limit': 10})
        result, provenance = archive.get(url)
        if result['features']:
            if len(result['features']) != 1:
                raise ValueError(f'Multiple current BAG pand records for {identifier}')
            pand_records[identifier] = result['features'][0], provenance
        else:
            absent_records[identifier] = {'bag_coverage': 'unavailable_current_record', 'provenance': {'query_url': url, 'response_sha256': provenance['sha256'], 'response_path': str(DIRECTORY / provenance['path'])}}
    print(f'BAG pand records: {len(pand_records)}', flush=True)
    # Fetch VBOs once over complete selected pand extents, then follow every
    # missing explicit link; no spatial assumption determines link completeness.
    extents = [shape(feature['geometry']).bounds for feature, _ in pand_records.values()]
    vbo_bounds = (min([bounds[0]] + [extent[0] for extent in extents]), min([bounds[1]] + [extent[1] for extent in extents]), max([bounds[2]] + [extent[2] for extent in extents]), max([bounds[3]] + [extent[3] for extent in extents]))
    vbo_records = {}
    for feature, provenance in pages(archive, collection_url('verblijfsobject', vbo_bounds)):
        url = BASE + '/collections/verblijfsobject/items/' + feature['id']
        vbo_records[url] = feature, provenance
    linked_urls = set(url for feature, _ in pand_records.values() for url in (feature['properties'].get('verblijfsobject.href') or []))
    missing_urls = sorted(linked_urls - set(vbo_records))
    print(f'BAG VBO records in footprint extents: {len(vbo_records)}; missing linked records to fetch: {len(missing_urls)}', flush=True)
    def fetch_link(url):
        feature, provenance = archive.get(url + '?f=json')
        if feature.get('type') != 'Feature':
            raise ValueError(f'Expected linked BAG VBO feature: {url}')
        return url, (feature, provenance)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        for url, result in executor.map(fetch_link, missing_urls):
            vbo_records[url] = result
    facts = dict(absent_records)
    for identifier, (feature, pand_provenance) in pand_records.items():
        properties = feature['properties']
        linked = properties.get('verblijfsobject.href')
        if linked is None:
            # No link property plus explicit count zero is a complete no-VBO fact.
            if properties.get('aantal_verblijfsobjecten') == 0:
                linked = []
            else:
                raise ValueError(f'BAG pand missing VBO links/count: {identifier}')
        if len(linked) != properties['aantal_verblijfsobjecten']:
            raise ValueError(f'BAG pand VBO count/link disagreement: {identifier}')
        use = sorted(set(purpose for url in linked for purpose in purposes(vbo_records[url][0]['properties'].get('gebruiksdoel'))))
        if linked and not use:
            raise ValueError(f'BAG linked VBOs have no use values: {identifier}')
        facts[identifier] = {
            'year': properties.get('bouwjaar'), 'use': use, 'status': properties['status'],
            'bag_coverage': 'complete', 'vbo_count': len(linked),
            'provenance': {
                'dataset': 'Kadaster LV-BAG / PDOK', 'pand_url': BASE + '/collections/pand/items/' + feature['id'],
                'pand_response_path': str(DIRECTORY / pand_provenance['path']), 'pand_response_sha256': pand_provenance['sha256'],
                'vbo_records': [{'url': url, 'bag_id': vbo_records[url][0]['properties']['identificatie'], 'response_path': str(DIRECTORY / vbo_records[url][1]['path']), 'response_sha256': vbo_records[url][1]['sha256']} for url in linked],
                'year_field': 'pand.bouwjaar (BAG oorspronkelijk bouwjaar)',
                'use_method': 'Sorted union of gebruiksdoel across every explicitly linked VBO; no VBO spatial clipping',
                'storeys': 'Not provided by this BAG source; omitted',
            },
        }
        if facts[identifier]['year'] is not None and type(facts[identifier]['year']) is not int:
            raise ValueError(f'BAG bouwjaar is not an integer for {identifier}')
    archive.save()
    report = {'bounds_rd': bounds, 'pand_count': len(pand_records), 'linked_vbo_count': len(linked_urls), 'linked_vbos_fetched_outside_spatial_pages': len(missing_urls), 'no_vbo_pands': sum(value.get('vbo_count') == 0 for value in facts.values()), 'unavailable_requested_ids': sorted(absent_records), 'source_manifest': str(archive.manifest_path), 'source_manifest_sha256': hashlib.sha256(archive.manifest_path.read_bytes()).hexdigest()}
    name = 'facts-' + '-'.join(str(int(value)) for value in bounds)
    (DIRECTORY / (name + '.json')).write_text(json.dumps({'report': report, 'facts': facts}, separators=(',', ':')) + '\n')
    print(json.dumps(report), flush=True)
    return facts


def load_facts(bounds, building_ids=()):
    """Serialize archive writers across geometry and standalone BAG runs."""
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    with (DIRECTORY / 'fetch.lock').open('a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        return _load_facts(bounds, building_ids)


def audit_scene(bounds=M1):
    """Read actual GLB facts and independently join archived BAG response links."""
    manifest_path = DIRECTORY / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    pands, vbos = {}, {}
    for record in manifest['files']:
        raw = (DIRECTORY / record['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != record['sha256']:
            raise ValueError(f"BAG archive hash mismatch: {record['path']}")
        document = json.loads(gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw)
        features = document.get('features', [document] if document.get('type') == 'Feature' else [])
        for feature in features:
            properties = feature['properties']
            if 'bouwjaar' in properties:
                pands[properties['identificatie']] = feature, record
            elif 'pand.href' in properties:
                vbos[BASE + '/collections/verblijfsobject/items/' + feature['id']] = properties, record
    scene = DIRECTORY.parents[2] / 'scene/v1/tiles'
    mismatches, selected, status_counts = [], [], Counter()
    unavailable, zero_vbo = [], 0
    tile_count = 0
    for x in range(bounds[0], bounds[2], 250):
        for y in range(bounds[1], bounds[3], 250):
            tile = f'x{x}_y{y}'
            path = scene / tile / 'buildings.glb'
            with path.open('rb') as stream:
                header = stream.read(20)
                document = json.loads(stream.read(struct.unpack_from('<I', header, 12)[0]))
            tile_count += 1
            for feature in document['extras']['features']:
                if feature['kind'] != 'building':
                    continue
                identifier = feature['bag_id']
                if identifier not in pands:
                    unavailable.append(identifier)
                    continue
                raw_feature, raw_record = pands[identifier]
                properties = raw_feature['properties']
                urls = properties.get('verblijfsobject.href') or []
                expected_use = sorted(set(purpose.strip() for url in urls for purpose in vbos[url][0]['gebruiksdoel'].split(',') if purpose.strip()))
                expected = {'year': properties['bouwjaar'], 'status': properties['status'], 'use': expected_use}
                for field, value in expected.items():
                    if feature.get(field) != value or feature.get('bag', {}).get(field) != value:
                        mismatches.append({'bag_id': identifier, 'field': field, 'expected': value, 'actual': feature.get(field)})
                bag = feature.get('bag', {})
                if bag.get('vbo_count') != len(urls) or bag.get('bag_coverage') != 'complete':
                    mismatches.append({'bag_id': identifier, 'field': 'link_count_or_coverage'})
                provenance = bag['provenance']
                if provenance['pand_response_sha256'] != raw_record['sha256']:
                    mismatches.append({'bag_id': identifier, 'field': 'pand_provenance'})
                declared_vbo_records = {record['url']: record for record in provenance['vbo_records']}
                if set(declared_vbo_records) != set(urls):
                    mismatches.append({'bag_id': identifier, 'field': 'vbo_link_provenance'})
                for url in urls:
                    if declared_vbo_records[url]['response_sha256'] != vbos[url][1]['sha256'] or declared_vbo_records[url]['bag_id'] != vbos[url][0]['identificatie']:
                        mismatches.append({'bag_id': identifier, 'field': 'vbo_response_provenance'})
                status_counts[properties['status']] += 1
                zero_vbo += not urls
                selected.append({'tile': tile, 'bag_id': identifier, 'year': expected['year'], 'use': expected_use, 'status': expected['status'], 'vbo_count': len(urls), 'facade_area_m2': feature.get('facade_area_m2', 0), 'photo_facade_area_m2': feature.get('photo_facade_area_m2', 0), 'pand_response_sha256': raw_record['sha256']})
    def nearest(point):
        return min(selected, key=lambda record: shape(pands[record['bag_id']][0]['geometry']).distance(Point(*point)))
    largest_untextured = sorted((record for record in selected if record['photo_facade_area_m2'] == 0), key=lambda record: (-record['facade_area_m2'], record['bag_id']))[:20]
    report = {'bounds_rd': bounds, 'tiles_read': tile_count, 'buildings_read': len(selected) + len(unavailable), 'matched_archived_BAG_pands': len(selected), 'zero_vbo_buildings': zero_vbo, 'status_counts': dict(status_counts), 'unavailable_bag_ids': unavailable, 'mismatches': mismatches, 'samples': {'rotterdam_centraal': nearest((91840, 437724)), 'building_near_erasmusbrug': nearest((93044, 436039)), 'largest_without_photo': largest_untextured}, 'source_manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(), 'method': 'Independently read every GLB JSON chunk; derive year/status directly from archived pand fields and use from every linked VBO raw gebruiksdoel; compare embedded facts, linked record counts, IDs, and response SHA256.'}
    (DIRECTORY / 'scene-m1-facts-audit.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2), flush=True)
    if mismatches or unavailable:
        raise ValueError(f'BAG scene audit failed: {len(mismatches)} mismatches, {len(unavailable)} unavailable IDs')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bounds', nargs=4, type=int, default=M1)
    parser.add_argument('--audit-scene', action='store_true')
    args = parser.parse_args()
    if args.audit_scene:
        audit_scene(tuple(args.bounds))
    else:
        load_facts(tuple(args.bounds))
