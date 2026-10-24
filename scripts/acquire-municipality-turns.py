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
def tile_record(tile_id,bounds,parent=None):
    s,w,n,e=bounds
    tile={'id':tile_id,'bbox':bounds,'query':f'[out:json][timeout:45];rel[type=restriction]({s},{w},{n},{e});(._;>;);out body;'}
    if parent is not None:tile['parentId']=parent
    return tile

def subdivide_tile(tile):
    s,w,n,e=tile['bbox'];mid_y=round((s+n)/2,9);mid_x=round((w+e)/2,9)
    return [tile_record(f"{tile['id']}.{i}",bounds,tile['id']) for i,bounds in enumerate([[s,w,mid_y,mid_x],[s,mid_x,mid_y,e],[mid_y,w,n,mid_x],[mid_y,mid_x,n,e]])]

def expand_tiles(base,splits):
    used=set();leaves=[]
    def visit(tile):
        if tile['id'] in splits:
            if tile['id'].count('.')>=2:raise ValueError('Subdivision is bounded to two levels per original tile')
            used.add(tile['id'])
            for child in subdivide_tile(tile):visit(child)
        else:leaves.append(tile)
    for tile in base:visit(tile)
    if used!=set(splits):raise ValueError(f'Unknown subdivision IDs or unsplit parents: {sorted(set(splits)-used)}')
    return leaves

def make_tiles(boundary):
    west,south,east,north=boundary.bounds;tiles=[]
    # About 8x6km at Rotterdam latitude, clipped by footprint intersection.
    for y in range(math.floor(south/.06),math.ceil(north/.06)):
        for x in range(math.floor(west/.12),math.ceil(east/.12)):
            w,s,e,n=round(x*.12,6),round(y*.06,6),round((x+1)*.12,6),round((y+1)*.06,6)
            if not boundary.intersects(box(w,s,e,n)):continue
            tiles.append(tile_record(f'{x}-{y}',[s,w,n,e]))
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

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--download',action='store_true');p.add_argument('--max-tiles',type=int,default=4,help='Maximum new HTTP requests this run; rerun to resume');p.add_argument('--endpoint',default='https://overpass-api.de/api/interpreter');p.add_argument('--continue-on-error',action='store_true',help='Use remaining request budget on independent tiles after a failure');p.add_argument('--tile',action='append',default=[],help='Download only this tile or its active children; repeatable');p.add_argument('--subdivide',action='append',default=[],help='Persist four exact child bboxes for a failed tile; repeatable, at most two levels');a=p.parse_args(argv)
    boundary_json=json.loads(BOUNDARY.read_bytes());boundary=shape(boundary_json['features'][0]['geometry'] if 'features' in boundary_json else boundary_json.get('geometry',boundary_json))
    directory=SOURCE/'osm-municipality-tiles';directory.mkdir(exist_ok=True)
    base=make_tiles(boundary);split_path=SOURCE/'osm-municipality-subdivisions.json';splits=set()
    if split_path.exists():
        saved=json.loads(split_path.read_bytes())
        if saved['boundarySha256']!=sha(BOUNDARY.read_bytes()):raise ValueError('Subdivision boundary source changed; review saved bboxes before proceeding')
        splits.update(saved['splitIds'])
    splits.update(a.subdivide);tiles=expand_tiles(base,splits)
    if any(not any(t['id']==selected or t['id'].startswith(selected+'.') for t in tiles) for selected in a.tile):p.error('--tile must identify an active tile or a subdivided parent')
    if a.subdivide:split_path.write_text(json.dumps({'boundarySha256':sha(BOUNDARY.read_bytes()),'splitIds':sorted(splits),'coverage':'Each split replaces its parent with four exact children; original responses remain archived'},indent=2)+'\n')
    requests=0;responses=[];allow_download=True;errors=[]
    for tile in tiles:
        path=directory/f"{tile['id']}.json.gz";meta_path=directory/f"{tile['id']}.source.json"
        selected=not a.tile or any(tile['id']==choice or tile['id'].startswith(choice+'.') for choice in a.tile)
        if not path.exists() and selected and a.download and allow_download and requests<max(0,a.max_tiles):
            requests+=1;data=urllib.parse.urlencode({'data':tile['query']}).encode()
            request=urllib.request.Request(a.endpoint,data=data,headers={'User-Agent':'010 Rotterdam retained traffic source audit','Content-Type':'application/x-www-form-urlencoded'})
            try:
                with urllib.request.urlopen(request,timeout=60) as response:raw=response.read()
                parsed=json.loads(raw)
                if parsed.get('remark') or 'elements' not in parsed:raise ValueError('Incomplete Overpass response')
            except Exception as error:
                failure={'tile':tile['id'],'endpoint':a.endpoint,'querySha256':sha(tile['query'].encode()),'attemptedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'error':f'{type(error).__name__}: {error}'}
                errors.append(failure);tile['lastError']=failure['error']
                with (directory/f"{tile['id']}.errors.jsonl").open('a') as log:log.write(json.dumps(failure)+'\n')
                print(f"{tile['id']}: {failure['error']}");allow_download=a.continue_on_error;continue
            path.write_bytes(gzip.compress(raw,mtime=0));meta_path.write_text(json.dumps({**tile,'endpoint':a.endpoint,'retrievedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'rawSha256':sha(raw)},indent=2)+'\n')
        if path.exists():
            raw=gzip.decompress(path.read_bytes());parsed=json.loads(raw)
            if parsed.get('remark'):raise ValueError('Retained tile response incomplete')
            if not meta_path.exists():raise ValueError(f'Missing exact query metadata: {meta_path}')
            metadata=json.loads(meta_path.read_bytes())
            if metadata['query']!=tile['query'] or metadata['rawSha256']!=sha(raw):raise ValueError('Retained tile metadata mismatch')
            responses.append(parsed);tile.update({'file':str(path.relative_to(ROOT)),'rawSha256':sha(raw)})
    manifest={'license':'ODbL-1.0','attribution':'© OpenStreetMap contributors','boundarySha256':sha(BOUNDARY.read_bytes()),'originalTiles':len(base),'subdividedTiles':sorted(splits),'selection':a.tile,'requestBudget':max(0,a.max_tiles),'errorsThisRun':errors,'tiles':tiles,'completed':len(responses),'required':len(tiles),'complete':len(responses)==len(tiles)}
    (SOURCE/'osm-municipality-turn-plan.json').write_text(json.dumps(manifest,indent=2)+'\n')
    if manifest['complete']:
        merged,outside=merge_responses(responses,boundary);raw=json.dumps(merged,separators=(',',':')).encode();output=SOURCE/'osm-municipality-turn-restrictions.json.gz';output.write_bytes(gzip.compress(raw,mtime=0))
        manifest.update({'outputSha256':sha(raw),'excludedOutsideMunicipality':outside,'elements':len(merged['elements']),'relations':sum(e['type']=='relation' for e in merged['elements'])})
        (SOURCE/'osm-municipality-turn-acquisition.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'completed':manifest['completed'],'required':manifest['required'],'newRequests':requests,'complete':manifest['complete'],'failedRequests':len(errors)}))
if __name__=='__main__':main()
