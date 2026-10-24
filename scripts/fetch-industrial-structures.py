#!/usr/bin/env python3
"""Written by AI, gpt-6-astra, 2026-10-24. Spatial AHN queries around measured crane rails.

Retains raw returns and BGT responses in ignored SSD cache. Selects one observed
flight per connected terminal area before geometry generation.
"""
import argparse
import collections
import concurrent.futures
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs
from urllib.request import urlopen

import laspy
from laspy.copc import Bounds
import numpy as np
from pyproj import Transformer
from shapely import contains_xy
from shapely.geometry import shape, mapping, box
from shapely.ops import transform, unary_union

PROJECT = Path(__file__).resolve().parents[1]
CACHE = PROJECT / 'work/data-cache/industrial-structures'
SOURCE = PROJECT / 'source-data/industrial-structures'
INDEX_URL = 'https://basisdata.nl/hwh-portal/20230609_tmp/links/nationaal/Nederland/AHN6_KM_PC_COPC.json'
TO_RD = Transformer.from_crs(4326, 28992, always_xy=True).transform
TO_GEO = Transformer.from_crs(28992, 4326, always_xy=True).transform
SNAPSHOT = '2026-10-24T00:00:00Z'


def cached_bytes(url, path):
    if not path.exists():
        with urlopen(url, timeout=120) as response:
            path.write_bytes(response.read())
    return path.read_bytes()


def bgt_features(collection, bounds):
    corners = np.array([TO_GEO(x, y) for x, y in [(bounds[0], bounds[1]), (bounds[0], bounds[3]),
                                                (bounds[2], bounds[1]), (bounds[2], bounds[3])]])
    bbox = ','.join(str(value) for value in [*corners.min(axis=0), *corners.max(axis=0)])
    url = f'https://api.pdok.nl/kadaster/bgt/ogc/v1/collections/{collection}/items?' + urlencode({
        'bbox': bbox, 'datetime': SNAPSHOT, 'limit': 1000, 'f': 'json'})
    features, requests = [], []
    while url:
        requests.append(url)
        path = CACHE / (hashlib.sha256(url.encode()).hexdigest() + '.json')
        response = json.loads(cached_bytes(url, path))
        features.extend(response['features'])
        url = next((link['href'] for link in response.get('links', []) if link['rel'] == 'next'), None)
        if url and parse_qs(urlparse(url).query).get('bbox') != [bbox]:
            raise ValueError('BGT next link lost the requested spatial filter')
    return features, requests


def utc(gps_time):
    return (datetime(1980, 1, 6, tzinfo=timezone.utc) + timedelta(seconds=float(gps_time) + 1e9 - 18)).isoformat()


def acquire_tile(item, regions, resolution):
    tile_geometry = shape(item['geometry'])
    selections = [(index, region.intersection(tile_geometry)) for index, region in enumerate(regions)
                  if region.intersects(tile_geometry)]
    geometry = unary_union([region for _, region in selections])
    bounds = geometry.bounds
    name = Path(urlparse(item['properties']['file']).path).name.replace('.COPC.LAZ', '')
    point_path = CACHE / f'{name}-{resolution:g}m.laz'
    if not point_path.exists():
        with laspy.CopcReader.open(item['properties']['file'], http_num_threads=3) as reader:
            points = reader.query(bounds=Bounds(np.array([bounds[0], bounds[1], -10]),
                                               np.array([bounds[2], bounds[3], 300])), resolution=resolution)
            header = reader.header.copy()
            header.vlrs = [record for record in header.vlrs if record.user_id != 'copc']
            laspy.LasData(header, points=points).write(point_path)
    ground_name = name.replace('_C_', '_M_') + '.TIF'
    ground_url = 'https://fsn1.your-objectstorage.com/hwh-ahn/AHN6/02a_DTM_50cm/' + ground_name
    ground_path = CACHE / ground_name
    cached_bytes(ground_url, ground_path)
    exclusions, exclusion_records, requests = [], [], []
    for collection in ['pand', 'overigbouwwerk', 'begroeidterreindeel', 'vegetatieobject_punt', 'vegetatieobject_vlak']:
        features, urls = bgt_features(collection, bounds)
        requests.extend(urls)
        for feature in features:
            properties = feature['properties']
            if collection == 'overigbouwwerk' and properties.get('type') not in ['opslagtank', 'silo', 'overkapping', 'windturbine']:
                continue
            geometry_rd = transform(TO_RD, shape(feature['geometry']))
            # Points locate existing trees; their display exclusion is explicit, not a surveyed crown polygon.
            padding = 5 if collection == 'vegetatieobject_punt' else 1.5
            exclusions.append(geometry_rd.buffer(padding))
            exclusion_records.append({'collection': collection, 'id': properties.get('lokaal_id'),
                                      'version': properties.get('version'), 'bufferMetres': padding})
    exclusion_geometry = unary_union(exclusions)
    exclusion_path = CACHE / (name + '-exclusions.json')
    exclusion_path.write_text(json.dumps({'geometryRD': mapping(exclusion_geometry),
                                          'records': exclusion_records, 'requests': requests}))
    cloud = laspy.read(point_path)
    x, y = np.asarray(cloud.x), np.asarray(cloud.y)
    gps, source_ids = np.asarray(cloud.gps_time), np.asarray(cloud.point_source_id)
    groups = []
    for region_id, selection in selections:
        inside = contains_xy(selection, x, y)
        for source_id in np.unique(source_ids[inside]):
            subset = inside & (source_ids == source_id)
            for day in np.unique(np.floor(gps[subset] / 86400).astype(int)):
                keep = subset & (np.floor(gps / 86400).astype(int) == day)
                cells = np.unique(np.floor(np.stack([x[keep], y[keep]], axis=1) / 10).astype(int), axis=0)
                groups.append({'region': region_id, 'pointSourceId': int(source_id), 'gpsDay': int(day),
                               'cells': cells.tolist(), 'points': int(keep.sum()),
                               'gpsRange': [float(gps[keep].min()), float(gps[keep].max())]})
    report = {'name': name, 'source': item['properties']['file'], 'sourceIndexRecord': item['properties'],
              'boundsRD_NAP': [[bounds[0], bounds[1], -10], [bounds[2], bounds[3], 300]],
              'queryResolutionMetres': resolution, 'rawPointCloudCache': str(point_path.relative_to(PROJECT)),
              'rawGroundCache': str(ground_path.relative_to(PROJECT)), 'groundSource': ground_url,
              'exclusionCache': str(exclusion_path.relative_to(PROJECT)),
              'sourceCropSha256': hashlib.sha256(point_path.read_bytes()).hexdigest(),
              'sourceCropBytes': point_path.stat().st_size, 'groups': groups}
    print(json.dumps({'tile': name, 'points': len(cloud.points), 'bytes': point_path.stat().st_size,
                      'bgtExclusions': len(exclusion_records)}), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resolution', type=float, default=1)
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--limit', type=int)
    arguments = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    SOURCE.mkdir(parents=True, exist_ok=True)
    collection = json.loads(gzip.decompress((PROJECT / 'source-data/industrial-ground.geojson.gz').read_bytes()))
    rails = unary_union([transform(TO_RD, shape(feature['geometry'])) for feature in collection['features']
                         if feature['properties'].get('plus_functie') == '(haven)kraan'])
    municipality = json.loads((PROJECT / 'public/data/municipality.json').read_text())
    municipality = transform(TO_RD, unary_union([shape(feature['geometry']) for feature in municipality['features']]))
    selection = rails.buffer(80).intersection(municipality)
    regions = sorted(list(selection.geoms), key=lambda polygon: (polygon.centroid.x, polygon.centroid.y))
    index = json.loads(cached_bytes(INDEX_URL, CACHE / 'ahn6-copc-index.json'))
    tiles = sorted([item for item in index['features'] if shape(item['geometry']).intersects(selection)],
                   key=lambda item: shape(item['geometry']).bounds)
    if arguments.limit:
        tiles = tiles[:arguments.limit]
    print(json.dumps({'sourceTiles': len(tiles), 'regions': len(regions), 'selectionAreaKm2': selection.area / 1e6}), flush=True)
    reports = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=arguments.workers) as pool:
        futures = [pool.submit(acquire_tile, item, regions, arguments.resolution) for item in tiles]
        for future in concurrent.futures.as_completed(futures):
            reports.append(future.result())
            (CACHE / 'acquisition-progress.json').write_text(json.dumps(reports))
    reports.sort(key=lambda report: report['name'])
    candidates = collections.defaultdict(lambda: {'cells': set(), 'points': 0, 'gpsRange': [float('inf'), -float('inf')]})
    for report in reports:
        for group in report['groups']:
            candidate = candidates[(group['region'], group['pointSourceId'], group['gpsDay'])]
            candidate['cells'].update(tuple(cell) for cell in group['cells'])
            candidate['points'] += group['points']
            candidate['gpsRange'] = [min(candidate['gpsRange'][0], group['gpsRange'][0]),
                                     max(candidate['gpsRange'][1], group['gpsRange'][1])]
    selected = {}
    for region_id in range(len(regions)):
        choices = [(key, value) for key, value in candidates.items() if key[0] == region_id]
        if choices:
            selected[region_id] = max(choices, key=lambda pair: (len(pair[1]['cells']), pair[1]['gpsRange'][1]))
    configs, coverage = [], []
    for region_id, (key, evidence) in selected.items():
        selection_path = SOURCE / f'region-{region_id}.geojson'
        selection_path.write_text(json.dumps({'type': 'Feature', 'properties': {'selection': '80 m around BGT crane rails, municipality clipped', 'horizontalCRS': 'EPSG:28992'},
                                              'geometry': mapping(regions[region_id])}, separators=(',', ':')))
        coverage.append({'region': region_id, 'areaMetres2': regions[region_id].area, 'pointSourceId': key[1],
                         'gpsDay': key[2], 'surveyTimeUTC': [utc(value) for value in evidence['gpsRange']],
                         'measured10mCells': len(evidence['cells']), 'sourcePoints': evidence['points'],
                         'selectionReason': 'Single source strip with greatest measured 10 m cell coverage across this connected terminal area.'})
        for report in reports:
            if not any((group['region'], group['pointSourceId'], group['gpsDay']) == key for group in report['groups']):
                continue
            config = {field: value for field, value in report.items() if field != 'groups'}
            config.update({'region': region_id, 'pointSourceId': key[1], 'gpsDay': key[2],
                           'surveyTimeUTC': [utc(value) for value in evidence['gpsRange']],
                           'selectionMask': str(selection_path.relative_to(PROJECT)),
                           'groundClearanceMetres': .8, 'unknownGroundMinimumNAP': 2,
                           'license': 'CC BY 4.0', 'attribution': 'Actueel Hoogtebestand Nederland / Het Waterschapshuis — AHN6',
                           'sourceEdition': 'AHN6 2026'})
            configs.append(config)
    (SOURCE / 'selection.json').write_text(json.dumps(configs, indent=2) + '\n')
    (SOURCE / 'coverage.json').write_text(json.dumps({'policy': 'One flight per terminal area; no cross-date hole filling.',
        'sourceTileCount': len(reports), 'requestedAreaKm2': selection.area / 1e6, 'regions': coverage}, indent=2) + '\n')
    print(json.dumps({'selectedSegments': len(configs), 'selectedRegions': len(coverage),
                      'rawBytes': sum(report['sourceCropBytes'] for report in reports)}), flush=True)


if __name__ == '__main__':
    main()
