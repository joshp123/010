#!/usr/bin/env python3
"""Bounded/resumable OSM turn acquisition over the exact municipality footprint.
Each response and query is retained. No runtime rule is automatically activated.
"""
import argparse,datetime,gzip,hashlib,json,math,urllib.parse,urllib.request
from pathlib import Path
from shapely.geometry import box,shape,Point,LineString
ROOT=Path(__file__).resolve().parents[1];SOURCE=ROOT/'source-data/traffic'
BOUNDARY=ROOT/'source-data/transit/municipality.geojson'
def sha(data):return hashlib.sha256(data).hexdigest()
def make_tiles(boundary):
    west,south,east,north=boundary.bounds;tiles=[]
    # About 8x6km at Rotterdam latitude, clipped by footprint intersection.
    for y in range(math.floor(south/.06),math.ceil(north/.06)):
        for x in range(math.floor(west/.12),math.ceil(east/.12)):
            w,s,e,n=round(x*.12,6),round(y*.06,6),round((x+1)*.12,6),round((y+1)*.06,6)
            if not boundary.intersects(box(w,s,e,n)):continue
            bbox=f'{s},{w},{n},{e}';query=f'[out:json][timeout:45];rel[type=restriction]({bbox});(._;>;);out body;'
            tiles.append({'id':f'{x}-{y}','bbox':[s,w,n,e],'query':query})
    return tiles

def merge_responses(responses,boundary):
    elements={};conflicts=set()
    for response in responses:
        for element in response['elements']:
            key=(element['type'],element['id'])
            if key in elements and elements[key]!=element:conflicts.add(key)
            else:elements[key]=element
    if conflicts:raise ValueError(f'Conflicting source snapshots for {len(conflicts)} elements; reacquire conflicting tiles together: {sorted(conflicts)[:12]}')
    retained=[];outside=0
    for key,relation in elements.items():
        if key[0]!='relation':continue
        inside=False
        for member in relation.get('members',[]):
            if member['role']!='via':continue
            via=elements.get((member['type'],member['ref']))
            if via is None:raise ValueError('Incomplete relation member geometry')
            if member['type']=='node':inside |= boundary.covers(Point(via['lon'],via['lat']))
            elif member['type']=='way':
                points=[elements.get(('node',node)) for node in via.get('nodes',[])]
                if any(p is None for p in points):raise ValueError('Incomplete via-way geometry')
                if len(points)>1:inside |= boundary.intersects(LineString([(p['lon'],p['lat']) for p in points]))
        if inside:retained.append(relation)
        else:outside+=1
    needed={('relation',r['id']) for r in retained}
    for relation in retained:
        for member in relation['members']:needed.add((member['type'],member['ref']))
    for key in list(needed):
        element=elements.get(key)
        if element is None:raise ValueError('Incomplete retained member')
        if key[0]=='way':needed.update(('node',node) for node in element.get('nodes',[]))
    if any(key not in elements for key in needed):raise ValueError('Incomplete retained nodes')
    return {'version':.6,'generator':'010 retained municipal Overpass merge','elements':[elements[key] for key in sorted(needed)]},outside

def main():
    p=argparse.ArgumentParser();p.add_argument('--download',action='store_true');p.add_argument('--max-tiles',type=int,default=4,help='Maximum new HTTP requests this run; rerun to resume');p.add_argument('--endpoint',default='https://overpass-api.de/api/interpreter');a=p.parse_args()
    boundary_json=json.loads(BOUNDARY.read_bytes());boundary=shape(boundary_json['features'][0]['geometry'] if 'features' in boundary_json else boundary_json.get('geometry',boundary_json))
    directory=SOURCE/'osm-municipality-tiles';directory.mkdir(exist_ok=True)
    tiles=make_tiles(boundary);requests=0;responses=[];allow_download=True
    for tile in tiles:
        path=directory/f"{tile['id']}.json.gz";meta_path=directory/f"{tile['id']}.source.json"
        if not path.exists() and a.download and allow_download and requests<max(0,a.max_tiles):
            requests+=1;data=urllib.parse.urlencode({'data':tile['query']}).encode()
            request=urllib.request.Request(a.endpoint,data=data,headers={'User-Agent':'010 Rotterdam retained traffic source audit','Content-Type':'application/x-www-form-urlencoded'})
            try:
                with urllib.request.urlopen(request,timeout=60) as response:raw=response.read()
                parsed=json.loads(raw)
                if parsed.get('remark') or 'elements' not in parsed:raise ValueError('Incomplete Overpass response')
            except Exception as error:
                print(f"{tile['id']}: {type(error).__name__}: {error}");allow_download=False;continue
            path.write_bytes(gzip.compress(raw,mtime=0));meta_path.write_text(json.dumps({**tile,'endpoint':a.endpoint,'retrievedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'rawSha256':sha(raw)},indent=2)+'\n')
        if path.exists():
            raw=gzip.decompress(path.read_bytes());parsed=json.loads(raw)
            if parsed.get('remark'):raise ValueError('Retained tile response incomplete')
            if not meta_path.exists():raise ValueError(f'Missing exact query metadata: {meta_path}')
            metadata=json.loads(meta_path.read_bytes())
            if metadata['query']!=tile['query'] or metadata['rawSha256']!=sha(raw):raise ValueError('Retained tile metadata mismatch')
            responses.append(parsed);tile.update({'file':str(path.relative_to(ROOT)),'rawSha256':sha(raw)})
    manifest={'license':'ODbL-1.0','attribution':'© OpenStreetMap contributors','boundarySha256':sha(BOUNDARY.read_bytes()),'tiles':tiles,'completed':len(responses),'required':len(tiles),'complete':len(responses)==len(tiles)}
    (SOURCE/'osm-municipality-turn-plan.json').write_text(json.dumps(manifest,indent=2)+'\n')
    if manifest['complete']:
        merged,outside=merge_responses(responses,boundary);raw=json.dumps(merged,separators=(',',':')).encode();output=SOURCE/'osm-municipality-turn-restrictions.json.gz';output.write_bytes(gzip.compress(raw,mtime=0))
        manifest.update({'outputSha256':sha(raw),'excludedOutsideMunicipality':outside,'elements':len(merged['elements']),'relations':sum(e['type']=='relation' for e in merged['elements'])})
        (SOURCE/'osm-municipality-turn-acquisition.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'completed':manifest['completed'],'required':manifest['required'],'newRequests':requests,'complete':manifest['complete']}))
if __name__=='__main__':main()
