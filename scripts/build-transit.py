#!/usr/bin/env python3
"""Build municipality-clipped GTFS linkage. Requires Shapely; no web service key.

Raw national archive and live snapshots belong in ignored work/data-cache/transit.
Use --download to acquire/refresh sources; omit it to reproduce retained inputs.
"""
import argparse
import csv
import datetime
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import urllib.request
import zipfile
from shapely.geometry import LineString, shape
from shapely.prepared import prep

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'work/data-cache/transit'
SOURCE = ROOT / 'source-data/transit'
OUTPUT = ROOT / 'dist/data/transit'
GTFS_URL = 'https://gtfs.ovapi.nl/nl/gtfs-nl.zip'
LIVE_URL = 'https://gtfs.ovapi.nl/nl/vehiclePositions.pb'
BOUNDARY_URL = 'https://api.pdok.nl/kadaster/brk-bestuurlijke-gebieden/ogc/v1/collections/gemeentegebied/items?naam=Rotterdam&f=json'


def download(url, path):
    request = urllib.request.Request(url, headers={'User-Agent': '010 Rotterdam miniature https://010.jjpcodes.com @jjpcodes', 'Accept-Encoding': 'gzip'})
    with urllib.request.urlopen(request, timeout=180) as response:
        with path.open('wb') as destination:
            shutil.copyfileobj(response, destination)
        if response.headers.get('Content-Encoding') == 'gzip':
            path.write_bytes(gzip.decompress(path.read_bytes()))
        return {'url': url, 'file': path.name, 'acquired': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'lastModified': response.headers.get('Last-Modified'), 'etag': response.headers.get('ETag'), 'sha256': hashlib.file_digest(path.open('rb'), 'sha256').hexdigest(), 'bytes': path.stat().st_size}


def varint(value):
    result = bytearray()
    while value > 127:
        result.append((value & 127) | 128)
        value >>= 7
    result.append(value)
    return bytes(result)


def number(field, value):
    return varint(field << 3) + varint(value)


def blob(field, value):
    if isinstance(value, str):
        value = value.encode('utf-8')
    return varint(field << 3 | 2) + varint(len(value)) + value


def coordinates(points):
    values = bytearray()
    previous = [0, 0]
    for point in points:
        for axis in range(2):
            value = round(point[axis] * 10**7)
            difference = value - previous[axis]
            values.extend(varint(difference * 2 if difference >= 0 else -difference * 2 - 1))
            previous[axis] = value
    return bytes(values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true')
    args = parser.parse_args()
    for directory in [CACHE, SOURCE, OUTPUT]:
        directory.mkdir(parents=True, exist_ok=True)
    if args.download:
        acquisitions = [download(GTFS_URL, CACHE / 'gtfs-nl.zip')]
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        acquisitions.append(download(LIVE_URL, CACHE / ('vehiclePositions-' + timestamp + '.pb')))
        acquisitions.append(download('https://gtfs.ovapi.nl/README', CACHE / 'README.txt'))
        (CACHE / 'acquisition.json').write_text(json.dumps({'sources': acquisitions}, indent=2) + '\n')
    boundary_file = ROOT / 'work/data-cache' / (hashlib.sha256(BOUNDARY_URL.encode()).hexdigest() + '.json')
    if not boundary_file.exists():
        download(BOUNDARY_URL, boundary_file)
    boundary_source = json.loads(boundary_file.read_bytes())
    feature = boundary_source['features'][0]
    assert feature['properties']['identificatie'] == 'GM0599'
    municipality = shape(feature['geometry'])
    prepared = prep(municipality)
    (SOURCE / 'municipality.geojson').write_text(json.dumps(feature, separators=(',', ':')) + '\n')
    archive = CACHE / 'gtfs-nl.zip'
    selected_shapes = {}
    source_shape_count = 0
    with zipfile.ZipFile(archive) as zipped:
        zipped_license = zipped.read('licenses.txt')
        license_rows = list(csv.DictReader(io.StringIO(zipped_license.decode('utf-8-sig'))))
        licenses = {row['licensed_table_name']: row['license_spdx_id'] for row in license_rows}
        if licenses.get('') != 'CC0-1.0' or licenses.get('shapes.txt') != 'ODbL-1.0':
            raise ValueError('Upstream licences changed; inspect licenses.txt before publishing')
        for table in ['agency.txt', 'routes.txt', 'trips.txt', 'feed_info.txt']:
            if licenses.get(table, licenses['']) != 'CC0-1.0':
                raise ValueError(f'Upstream licence changed for {table}; inspect licenses.txt')
        def rows(name):
            return csv.DictReader(io.TextIOWrapper(zipped.open(name), encoding='utf-8-sig', newline=''))
        def retain_shape(identifier, points):
            nonlocal source_shape_count
            source_shape_count += 1
            if len(points) < 2:
                return
            points.sort()
            line = LineString([(longitude, latitude) for _, longitude, latitude in points])
            if not prepared.intersects(line):
                return
            clipped = line.intersection(municipality)
            lines = [clipped] if clipped.geom_type == 'LineString' else [part for part in clipped.geoms if part.geom_type == 'LineString'] if hasattr(clipped, 'geoms') else []
            if lines:
                selected_shapes[identifier] = [list(line.coords) for line in lines if line.length]
        current = None
        points = []
        for row in rows('shapes.txt'):
            identifier = row['shape_id']
            if current is not None and identifier != current:
                if current in selected_shapes:
                    raise ValueError('Source shapes are not grouped by shape_id')
                retain_shape(current, points)
                points = []
            current = identifier
            points.append((int(row['shape_pt_sequence']), float(row['shape_pt_lon']), float(row['shape_pt_lat'])))
        if current is not None:
            retain_shape(current, points)
        print(f'Shapes: {len(selected_shapes):,} intersect Rotterdam / {source_shape_count:,} national', flush=True)
        trips = []
        national_trips = trips_without_shape = 0
        for row in rows('trips.txt'):
            national_trips += 1
            if not row.get('shape_id'):
                trips_without_shape += 1
            if row.get('shape_id') in selected_shapes:
                trips.append(row)
        route_ids = {row['route_id'] for row in trips}
        routes = [row for row in rows('routes.txt') if row['route_id'] in route_ids]
        agencies = {row['agency_id']: row for row in rows('agency.txt')}
        feed_info = list(rows('feed_info.txt')) if 'feed_info.txt' in zipped.namelist() else []
    used_shapes = {row['shape_id'] for row in trips}
    selected_shapes = {key: value for key, value in selected_shapes.items() if key in used_shapes}
    route_indices = {row['route_id']: index for index, row in enumerate(routes)}
    shape_indices = {identifier: index for index, identifier in enumerate(selected_shapes)}
    output = bytearray()
    for route in routes:
        route_data = blob(1, route['route_id']) + blob(2, route.get('route_short_name', '')) + blob(3, route.get('route_long_name', '')) + number(4, int(route['route_type'])) + blob(5, route.get('agency_id', '')) + blob(6, agencies.get(route.get('agency_id'), {}).get('agency_name', ''))
        output.extend(blob(1, route_data))
    for identifier, lines in selected_shapes.items():
        shape_data = blob(1, identifier) + b''.join(blob(2, blob(1, coordinates(line))) for line in lines)
        output.extend(blob(2, shape_data))
    for trip in trips:
        trip_data = blob(1, trip['trip_id']) + number(2, route_indices[trip['route_id']]) + number(3, shape_indices[trip['shape_id']])
        output.extend(blob(3, trip_data))
    for polygon in municipality.geoms if municipality.geom_type == 'MultiPolygon' else [municipality]:
        polygon_data = b''.join(blob(1, blob(1, coordinates(ring.coords))) for ring in [polygon.exterior, *polygon.interiors])
        output.extend(blob(4, polygon_data))
    output.extend(number(5, 1))
    (CACHE / 'map.pb').write_bytes(output)
    compressed = gzip.compress(output, mtime=0)
    (OUTPUT / 'map.pb.gz').write_bytes(compressed)
    counts_by_type = {}
    for route in routes:
        counts_by_type[route['route_type']] = counts_by_type.get(route['route_type'], 0) + 1
    acquisition = json.loads((CACHE / 'acquisition.json').read_text()) if (CACHE / 'acquisition.json').exists() else {}
    manifest = {'writtenBy': 'AI, GPT-6, 2026-10-24', 'sources': acquisition.get('sources', []), 'sourceArchive': {'url': GTFS_URL, 'sha256': hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest(), 'bytes': archive.stat().st_size, 'retainedPath': 'work/data-cache/transit/gtfs-nl.zip'}, 'boundary': {'url': BOUNDARY_URL, 'sha256': hashlib.sha256(boundary_file.read_bytes()).hexdigest(), 'municipality': 'GM0599'}, 'feedInfo': feed_info, 'licenses': {'shapes.txt': 'ODbL-1.0', 'otherUsedGtfsTables': 'CC0-1.0', 'municipalBoundary': 'CC-BY-4.0', 'derivedShapeDatabase': 'ODbL-1.0'}, 'counts': {'routes': len(routes), 'trips': len(trips), 'shapes': len(selected_shapes), 'routesByGtfsType': counts_by_type}, 'output': {'protobufBytes': len(output), 'gzipBytes': len(compressed), 'sha256': hashlib.sha256(output).hexdigest()}, 'transformation': 'Source GTFS shapes intersected with exact Kadaster municipality polygon. Interior vertices retained; boundary intersections interpolated by GEOS. No simplification. Coordinates quantized to 1e-7 degrees; at most 0.007 m displacement. Trips retain IDs, route indices and source-shape indices; no schedule positions are generated.'}
    (SOURCE / 'GTFS-LICENSE.txt').write_bytes(zipped_license)
    manifest['sourceCompleteness'] = {'nationalTrips': national_trips, 'tripsWithoutShapeId': trips_without_shape, 'limitation': 'Geographic selection uses source shapes; trips without shape IDs cannot establish municipal geometry. Unmatched municipal observations remain available with null route/shape metadata.'}
    (SOURCE / 'provenance.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(manifest['counts']), flush=True)
    print(f'Output: {len(output):,} protobuf bytes; {len(compressed):,} gzip bytes', flush=True)


if __name__ == '__main__':
    main()
