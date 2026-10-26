#!/usr/bin/env python3
# Written by AI on 2026-10-26 by model GPT-6.
"""Retain CC0 GTFS metadata for routes with a stop inside gemeente Rotterdam."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile
from shapely.geometry import Point, shape
from shapely.ops import transform
from shapely.prepared import prep
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('archive', type=Path)
args = parser.parse_args()
source = ROOT / 'source-data/transit'
municipality = shape(json.loads((source / 'municipality.geojson').read_text())['geometry'])
inside = prep(municipality)
project = Transformer.from_crs(4326, 28992, always_xy=True).transform
bounds = transform(project, municipality).bounds
bounds = [round(bounds[0]-2000, 1), round(bounds[1]-2000, 1), round(bounds[2]+2000, 1), round(bounds[3]+2000, 1)]
with zipfile.ZipFile(args.archive) as archive:
    def rows(name):
        return csv.DictReader(io.TextIOWrapper(archive.open(name), encoding='utf-8-sig', newline=''))
    licenses = {row['licensed_table_name']: row['license_spdx_id'] for row in rows('licenses.txt')}
    for table in ['stops.txt', 'stop_times.txt', 'routes.txt', 'trips.txt', 'feed_info.txt']:
        if licenses.get(table, licenses.get('')) != 'CC0-1.0':
            raise ValueError(f'Licence changed for {table}')
    stop_ids = {row['stop_id'] for row in rows('stops.txt') if inside.covers(Point(float(row['stop_lon']), float(row['stop_lat'])))}
    print(f'{len(stop_ids)} stops inside gemeente', flush=True)
    trip_ids = {row['trip_id'] for row in rows('stop_times.txt') if row['stop_id'] in stop_ids}
    route_ids = {row['route_id'] for row in rows('trips.txt') if row['trip_id'] in trip_ids}
    routes = [[row['route_id'], int(row['route_type']), row['route_short_name']] for row in rows('routes.txt') if row['route_id'] in route_ids]
    route_index = {row[0]: index for index, row in enumerate(routes)}
    headsigns = ['']
    headsign_index = {'': 0}
    trips = {}
    trains = {}
    for row in rows('trips.txt'):
        if row['route_id'] not in route_index:
            continue
        headsign = row.get('trip_headsign', '')
        if headsign not in headsign_index:
            headsign_index[headsign] = len(headsigns)
            headsigns.append(headsign)
        link = [route_index[row['route_id']], headsign_index[headsign]]
        trips[row['trip_id']] = link
        if row.get('realtime_trip_id'):
            trips[row['realtime_trip_id']] = link
        if routes[link[0]][1] == 2 and row.get('trip_short_name'):
            trains.setdefault(row['trip_short_name'], set()).add(tuple(link))
    # A repeated service number must not silently select an arbitrary destination.
    train_lookup = {}
    for number, links in trains.items():
        route_names = {routes[link[0]][2] for link in links}
        if len(route_names) == 1:
            route = min(link[0] for link in links)
            headsign_ids = {link[1] for link in links}
            train_lookup[number] = [route, next(iter(headsign_ids)) if len(headsign_ids) == 1 else 0]
    trains = train_lookup
    feed_info = list(rows('feed_info.txt'))
lookup = {'bounds': bounds, 'routes': routes, 'headsigns': headsigns, 'trips': trips, 'trains': trains}
output = source / 'worker-lookup.json'
output.write_text(json.dumps(lookup, ensure_ascii=False, separators=(',', ':'))+'\n')
provenance = {
    'writtenBy': 'AI, GPT-6, 2026-10-26',
    'source': 'https://gtfs.ovapi.nl/nl/gtfs-nl.zip',
    'sha256': hashlib.file_digest(args.archive.open('rb'), 'sha256').hexdigest(),
    'feedInfo': feed_info, 'tablesLicense': 'CC0-1.0',
    'boundary': 'Kadaster / PDOK GM0599, CC BY 4.0; source-data/transit/municipality.geojson',
    'selection': 'Routes with at least one stop covered by the exact municipality polygon; all trips on those routes, including realtime_trip_id aliases. No shapes used.',
    'boundsRdNewWith2kmMargin': bounds,
    'counts': {'routes': len(routes), 'tripKeys': len(trips), 'trainNumbers': len(trains), 'headsigns': len(headsigns)},
    'lookupBytes': output.stat().st_size,
}
(source / 'worker-provenance.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=2)+'\n')
print(json.dumps(provenance), flush=True)
