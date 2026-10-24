#!/usr/bin/env python3
"""Rebuild a separate decorative cycling network from retained NWB FP features.
Uses the existing traffic acquisition cache; requires complete municipal pages on
first run. Later runs use source-data/traffic/nwb-cycleways.geojson.gz.
"""
import argparse, datetime, gzip, hashlib, importlib.util, json
from pathlib import Path
from shapely.geometry import LineString, Point, shape
from shapely.ops import transform, unary_union
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('traffic_build', ROOT / 'scripts/build-traffic.py')
traffic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(traffic)
parser = argparse.ArgumentParser()
parser.add_argument('--download',action='store_true',help='Acquire/resume all municipal NWB pages; does not rebuild motor roads')
options = parser.parse_args()
if options.download: traffic.acquire()
source = ROOT / 'source-data/traffic/nwb-cycleways.geojson.gz'
pages = sorted(traffic.CACHE.glob('nwb-rotterdam-*.json'))
if source.exists() and not options.download:
    features = json.loads(gzip.decompress(source.read_bytes()))['features']
else:
    if not pages or any(link['rel'] == 'next' for link in json.loads(pages[-1].read_bytes())['links']):
        raise SystemExit('Complete NWB municipal acquisition required before first cycle build')
    features = [f for p in pages for f in json.loads(p.read_bytes())['features'] if f['properties'].get('bst_code') == 'FP']
    source.write_bytes(gzip.compress(json.dumps({'type':'FeatureCollection','features':features},separators=(',',':')).encode(),mtime=0))

boundary_path = ROOT / 'source-data/transit/municipality.geojson'
boundary_json = json.loads(boundary_path.read_bytes())
boundary = shape(boundary_json['features'][0]['geometry'] if 'features' in boundary_json else boundary_json.get('geometry',boundary_json))
to_metres = Transformer.from_crs(4326,28992,always_xy=True).transform
from_metres = Transformer.from_crs(28992,4326,always_xy=True).transform
boundary = transform(to_metres,boundary)
brt_path = ROOT / 'source-data/transport-network.geojson.gz'
brt = json.loads(gzip.decompress(brt_path.read_bytes()))
tunnels = unary_union([transform(to_metres,shape(f['geometry'])) for f in brt['features'] if f['properties'].get('kind') == 'road' and f['properties'].get('fysiekvoorkomen') == 'in tunnel']).buffer(2)
records=[]; unknown=0; length=0
for feature in features:
    props=feature['properties']
    if isinstance(props.get('rel_hoogte'),(float,int)) and props['rel_hoogte'] < 0: continue
    if props.get('rijrichtng') not in traffic.DIRECTIONS:
        unknown+=1
        continue
    direction=traffic.DIRECTIONS[props['rijrichtng']]
    lines=feature['geometry']['coordinates'] if feature['geometry']['type']=='MultiLineString' else [feature['geometry']['coordinates']]
    for points in lines:
        original=transform(to_metres,LineString(points))
        clipped=original.intersection(boundary).difference(tunnels)
        for part in list(clipped.geoms) if hasattr(clipped,'geoms') else [clipped]:
            if part.geom_type!='LineString' or part.length<.1: continue
            start=props['jte_id_beg'] if Point(part.coords[0]).distance(Point(original.coords[0])) < .05 else 0
            end=props['jte_id_end'] if Point(part.coords[-1]).distance(Point(original.coords[-1])) < .05 else 0
            geographic=list(transform(from_metres,part).coords)
            record=traffic.integer(1,int(props['wvk_id']))+traffic.integer(2,int(start or 0))+traffic.integer(3,int(end or 0))+traffic.integer(4,direction)+traffic.blob(5,traffic.coordinates(geographic))+traffic.blob(6,'FP')
            records.append(record);length+=part.length
output=ROOT/'public/data/traffic/cycleways.pb.gz'
output.write_bytes(gzip.compress(traffic.integer(1,1)+b''.join(traffic.blob(2,r) for r in records),mtime=0))
report={'preparedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source':traffic.URL,'sourceLicense':'NWB CC0; boundary and BRT tunnel mask Kadaster CC BY 4.0','selectedFPFeatures':len(features),'runtimePieces':len(records),'kilometres':length/1000,'unspecifiedDirectionFeatures':unknown,'directionInterpretation':'Only source H/T/B directions retained; O/unknown excluded from runtime, preserved in raw source','processing':'Same NWB source vertices and source junctions; exact municipality clip; exclude unknown directions, explicit BRT tunnels and negative rel_hoogte; omit degenerate fragments <0.1m; quantize 1e-7 degrees','sourceSha256':hashlib.sha256(source.read_bytes()).hexdigest(),'boundarySha256':hashlib.sha256(boundary_path.read_bytes()).hexdigest(),'tunnelMaskSourceSha256':hashlib.sha256(brt_path.read_bytes()).hexdigest(),'outputSha256':hashlib.sha256(output.read_bytes()).hexdigest(),'outputBytes':output.stat().st_size,'rawPageSha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in pages}}
(ROOT/'source-data/traffic/cycling-provenance.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='rawPageSha256'},indent=2))
