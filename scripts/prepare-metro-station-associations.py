#!/usr/bin/env python3
"""Associate exact GTFS metro station reference fixes with retained BRT tracks.
Written by AI, GPT-6, 2026-10-24. No track geometry or elevation is generated.
"""
import argparse,csv,gzip,hashlib,io,json,math,zipfile
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--gtfs',type=Path,required=True)
args=parser.parse_args()
physical_path=ROOT/'public/data/transit/metro-physical.json.gz'
physical=json.loads(gzip.decompress(physical_path.read_bytes()))
with zipfile.ZipFile(args.gtfs) as archive:
 def rows(name):return csv.DictReader(io.TextIOWrapper(archive.open(name)))
 agencies={r['agency_id'] for r in rows('agency.txt') if r['agency_name']=='RET'}
 routes={r['route_id']:r for r in rows('routes.txt') if r['agency_id'] in agencies and r['route_type']=='1'}
 trips={r['trip_id']:r['route_id'] for r in rows('trips.txt') if r['route_id'] in routes}
 stops={r['stop_id']:r for r in rows('stops.txt')}
 journeys=defaultdict(list)
 for row in rows('stop_times.txt'):
  if row['trip_id'] in trips:journeys[row['trip_id']].append((int(row['stop_sequence']),row['stop_id']))
 neighbours=defaultdict(set)
 for trip,entries in journeys.items():
  ordered=[stop for _,stop in sorted(entries)]
  for index,stop in enumerate(ordered):
   key=(trips[trip],stop)
   if index:neighbours[key].add(ordered[index-1])
   if index+1<len(ordered):neighbours[key].add(ordered[index+1])
associations=[]
for (route_id,stop_id),adjacent_ids in sorted(neighbours.items()):
 stop=stops[stop_id];lon,lat=float(stop['stop_lon']),float(stop['stop_lat'])
 sx=111320*math.cos(math.radians(lat));sy=111320
 directions=[];lengths=[]
 for adjacent_id in adjacent_ids:
  adjacent=stops[adjacent_id];dx=(float(adjacent['stop_lon'])-lon)*sx;dz=(lat-float(adjacent['stop_lat']))*sy
  if math.hypot(dx,dz)>1:directions.append(math.atan2(dx,dz));lengths.append(math.hypot(dx,dz))
 if not directions:continue
 candidates=[]
 for segment in physical['segments']:
  for a,b in zip(segment['coordinates'],segment['coordinates'][1:]):
   ax,az=(a[0]-lon)*sx,(lat-a[1])*sy;dx,dz=(b[0]-a[0])*sx,(a[1]-b[1])*sy
   if dx*dx+dz*dz==0:continue
   heading=math.atan2(dx,dz)
   alignment=max(abs(math.cos(heading-direction)) for direction in directions)
   if alignment<math.cos(math.radians(30)):continue
   fraction=max(0,min(1,-(ax*dx+az*dz)/(dx*dx+dz*dz)))
   distance=math.hypot(ax+fraction*dx,az+fraction*dz)
   # Station association only: never extrapolate across an interstation gap.
   if distance>min(100,min(lengths)/4):continue
   candidates.append((distance,segment['id']))
 if not candidates:continue
 distance,segment_id=min(candidates)
 associations.append({'stopId':stop_id,'name':stop['stop_name'],'routeId':route_id,'line':routes[route_id]['route_short_name'],'longitude':lon,'latitude':lat,'physicalSegmentId':segment_id,'referenceOffsetMetres':round(distance,2),'adjacentStopIds':sorted(adjacent_ids)})
output={'version':1,'method':'Exact service station reference coordinate to nearest BRT track compatible with an adjacent service station direction; approximate track position, never surveyed train location or depth','gtfsSource':'https://gtfs.ovapi.nl/nl/gtfs-nl.zip','gtfsSha256':hashlib.file_digest(args.gtfs.open('rb'),'sha256').hexdigest(),'physicalSource':physical['source'],'physicalSha256':hashlib.sha256(physical_path.read_bytes()).hexdigest(),'licenses':{'gtfs':'CC0-1.0','physical':'CC BY 4.0, Kadaster / PDOK'},'stations':associations}
(ROOT/'public/data/transit/metro-station-associations.json.gz').write_bytes(gzip.compress(json.dumps(output,separators=(',',':')).encode(),mtime=0))
for station in associations:
 if station['name'].endswith('Beurs'):print(station)
