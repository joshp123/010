#!/usr/bin/env python3
"""Prepare NWB road geometry/topology for clearly simulated miniature traffic.
Requires Shapely and pyproj. --download refreshes/resumes municipal source pages.
"""
import argparse
import datetime
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path
import urllib.request
from shapely.geometry import LineString, Point, shape, mapping
from shapely.ops import transform, unary_union
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'work/data-cache/traffic'
SOURCE = ROOT / 'source-data/traffic'
OUTPUT = ROOT / 'public/data/traffic'
URL = 'https://api.pdok.nl/rws/nationaal-wegenbestand-wegen/ogc/v1/collections/wegvakken/items?f=json&gme_naam=Rotterdam&limit=1000'
ROAD_CLASSES = {'ERF', 'HR', 'PAR', 'RB', 'AFR', 'OPR', 'VBD', 'VBI', 'VBK', 'VBR', 'VBS', 'VBW', 'NRB', 'TRB', 'GRB'}
DIRECTIONS = {'H': 1, 'T': 2, 'B': 3}


def acquire():
    CACHE.mkdir(parents=True, exist_ok=True)
    url, index = URL, 0
    while url:
        path = CACHE / f'nwb-rotterdam-{index:03}.json'
        if not path.exists():
            request = urllib.request.Request(url, headers={'User-Agent': '010 Rotterdam miniature source preparation'})
            with urllib.request.urlopen(request, timeout=90) as response:
                path.write_bytes(response.read())
        page = json.loads(path.read_bytes())
        print(f'page {index}: {len(page["features"])} features', flush=True)
        url = next((link['href'] for link in page['links'] if link['rel'] == 'next'), None)
        index += 1


def varint(value):
    encoded = bytearray()
    while value > 127:
        encoded.append((value & 127) | 128)
        value >>= 7
    encoded.append(value)
    return encoded


def integer(field, value):
    return varint(field << 3) + varint(value)


def blob(field, value):
    value = value.encode() if isinstance(value, str) else value
    return varint(field << 3 | 2) + varint(len(value)) + value


def coordinates(points):
    encoded = bytearray()
    previous = [0, 0]
    for point in points:
        for axis in (0, 1):
            value = round(point[axis] * 1e7)
            delta = value - previous[axis]
            encoded += varint(delta * 2 if delta >= 0 else -delta * 2 - 1)
            previous[axis] = value
    return encoded


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--download', action='store_true')
    options = parser.parse_args()
    if options.download:
        acquire()
    source_path = SOURCE / 'nwb-roads.geojson.gz'
    previous_report_path = SOURCE / 'provenance.json'
    previous_report = json.loads(previous_report_path.read_bytes()) if previous_report_path.exists() else {}
    pages = sorted(CACHE.glob('nwb-rotterdam-*.json'))
    retained = not options.download and source_path.exists()
    if retained:
        features = json.loads(gzip.decompress(source_path.read_bytes()))['features']
    else:
        if not pages:
            raise SystemExit('No retained source or municipal pages. Use --download.')
        if any(link['rel'] == 'next' for link in json.loads(pages[-1].read_bytes())['links']):
            raise SystemExit('Source acquisition incomplete. Resume with --download.')
        features = [feature for path in pages for feature in json.loads(path.read_bytes())['features']]
    boundary_path = ROOT / 'source-data/transit/municipality.geojson'
    boundary_json = json.loads(boundary_path.read_bytes())
    boundary = shape(boundary_json['features'][0]['geometry'] if 'features' in boundary_json else boundary_json['geometry'] if 'geometry' in boundary_json else boundary_json)
    to_metres = Transformer.from_crs(4326, 28992, always_xy=True).transform
    from_metres = Transformer.from_crs(28992, 4326, always_xy=True).transform
    boundary = transform(to_metres, boundary)
    brt_path = ROOT / 'source-data/transport-network.geojson.gz'
    brt = json.loads(gzip.decompress(brt_path.read_bytes()))
    tunnels = unary_union([transform(to_metres, shape(feature['geometry'])) for feature in brt['features'] if feature['properties'].get('kind') == 'road' and feature['properties'].get('fysiekvoorkomen') == 'in tunnel']).buffer(2)
    selected, roads, removed = [], [], Counter()
    for feature in features:
        props = feature['properties']
        if props.get('bst_code') not in ROAD_CLASSES or props.get('rijrichtng') not in DIRECTIONS:
            removed[props.get('bst_code', 'unknown')] += 1
            continue
        selected.append({"type": "Feature", "id": feature["id"], "properties": {key: props.get(key) for key in ("wvk_id", "jte_id_beg", "jte_id_end", "rijrichtng", "bst_code", "stt_naam", "rel_hoogte", "bronjaar", "wvk_begdat")}, "geometry": feature["geometry"]})
        lines = feature['geometry']['coordinates'] if feature['geometry']['type'] == 'MultiLineString' else [feature['geometry']['coordinates']]
        for points in lines:
            original = transform(to_metres, LineString(points))
            clipped = original.intersection(boundary).difference(tunnels)
            parts = list(clipped.geoms) if hasattr(clipped, 'geoms') else [clipped]
            for part in parts:
                if part.geom_type != 'LineString' or part.length < .1:
                    continue
                source_start = props['jte_id_beg'] if Point(part.coords[0]).distance(Point(original.coords[0])) < .05 else 0
                source_end = props['jte_id_end'] if Point(part.coords[-1]).distance(Point(original.coords[-1])) < .05 else 0
                geographic = list(transform(from_metres, part).coords)
                record = integer(1, int(props['wvk_id'])) + integer(2, int(source_start or 0)) + integer(3, int(source_end or 0)) + integer(4, DIRECTIONS[props['rijrichtng']]) + blob(5, coordinates(geographic)) + blob(6, props['bst_code'])
                roads.append({'bytes': record, 'length': part.length, 'coordinates': geographic, 'sourceId': props['wvk_id'], 'start': source_start, 'end': source_end})
    SOURCE.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    source_bytes = json.dumps({'type': 'FeatureCollection', 'features': selected}, separators=(',', ':')).encode()
    source_path = SOURCE / 'nwb-roads.geojson.gz'
    source_path.write_bytes(gzip.compress(source_bytes, mtime=0))
    output = integer(1, 1) + b''.join(blob(2, road['bytes']) for road in roads)
    (OUTPUT / 'roads.pb.gz').write_bytes(gzip.compress(output, mtime=0))
    vertices = [point for road in roads for point in road['coordinates']]
    report = {'source': URL, 'sourceDescription': 'Rijkswaterstaat / PDOK NWB roads, municipal selection Rotterdam', 'license': 'NWB source CC0 1.0; boundary and BRT tunnel exclusion CC BY 4.0', 'preparedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'rawPages': len(pages), 'rawFeatures': len(features), 'selectedSourceFeatures': len(selected), 'outputRoads': len(roads), 'sourceVertices': len(vertices), 'kilometres': sum(road['length'] for road in roads)/1000, 'excludedClasses': dict(removed), 'bounds': [min(p[0] for p in vertices),min(p[1] for p in vertices),max(p[0] for p in vertices),max(p[1] for p in vertices)], 'outputGzipBytes': len(gzip.compress(output,mtime=0)), 'sourceSha256': hashlib.sha256(source_path.read_bytes()).hexdigest(), 'boundarySha256': hashlib.sha256(boundary_path.read_bytes()).hexdigest(), 'brtTunnelSourceSha256': hashlib.sha256(brt_path.read_bytes()).hexdigest(), 'rawPageSha256': {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in pages}, 'processing': 'Original NWB vertices, exact municipality clip, subtract explicitly BRT-tagged tunnel polygons with 2m buffer, discard degenerate pieces shorter than 0.1m, retain original junction IDs only at unchanged original endpoints, quantize coordinates 1e-7 degrees. No route shortcut or line simplification.'}
    if retained:
        for key in ('rawPages', 'rawFeatures', 'excludedClasses', 'rawPageSha256'):
            if key in previous_report:
                report[key] = previous_report[key]
            else:
                report.pop(key, None)
    report['preparationInput'] = 'retained selected NWB source' if retained else 'complete municipal source pages'
    report['outputSha256'] = hashlib.sha256((OUTPUT / 'roads.pb.gz').read_bytes()).hexdigest()
    (SOURCE / 'provenance.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='rawPageSha256'}, indent=2))


if __name__ == '__main__':
    main()
