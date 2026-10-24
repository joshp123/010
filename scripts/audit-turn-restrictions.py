#!/usr/bin/env python3
"""Acquire centre/bridge OSM turn restrictions and audit unambiguous NWB matches.
Produces review candidates, NEVER silently activates conflated restrictions.
Raw response contains geometry/tags/IDs, not contributor identity (out body).
"""
import argparse,datetime,gzip,hashlib,json,math,urllib.parse,urllib.request
from collections import defaultdict
from pathlib import Path
from pyproj import Transformer
ROOT=Path(__file__).resolve().parents[1];SOURCE=ROOT/'source-data/traffic'
QUERY='[out:json][timeout:45];rel[type=restriction](51.900,4.465,51.930,4.505);(._;>;);out body;'
PROJECT=Transformer.from_crs(4326,28992,always_xy=True).transform

def norm(name): return ' '.join((name or '').casefold().split())
def bearing(points):
    # A short local tangent, not the far end of a winding road.
    origin=points[0]
    for point in points[1:]:
        delta=(point[0]-origin[0],point[1]-origin[1]);length=math.hypot(*delta)
        if length>=4:return delta[0]/length,delta[1]/length
    return None

def match_restrictions(osm,features):
    nodes={n['id']:PROJECT(n['lon'],n['lat']) for n in osm['elements'] if n['type']=='node'}
    ways={w['id']:w for w in osm['elements'] if w['type']=='way'}
    endpoints=defaultdict(list);grid=defaultdict(set)
    for feature in features:
        p=feature['properties'];coords=feature['geometry']['coordinates']
        if feature['geometry']['type']!='LineString':continue
        points=[PROJECT(*xy) for xy in coords]
        for start,junction in [(True,p['jte_id_beg']),(False,p['jte_id_end'])]:
            if not junction:continue
            local=points if start else points[::-1];heading=bearing(local)
            if not heading:continue
            item={'id':p['wvk_id'],'junction':junction,'point':local[0],'heading':heading,'start':start,'direction':p['rijrichtng'],'name':p.get('stt_naam')}
            endpoints[junction].append(item);grid[(int(local[0][0]//10),int(local[0][1]//10))].add(junction)
    results=[]
    for rel in [r for r in osm['elements'] if r['type']=='relation']:
        result={'osmRelation':rel['id'],'tags':rel.get('tags',{}),'status':'unmatched'};results.append(result)
        tags=result['tags'];restriction=tags.get('restriction:motorcar',tags.get('restriction:motor_vehicle',tags.get('restriction')))
        if any('conditional' in key for key in tags) or any(k in tags for k in ['day_on','day_off','hour_on','hour_off']):result['reason']='conditional restriction requires temporal evaluation';continue
        if set(tags.get('except','').split(';')) & {'motorcar','motor_vehicle','vehicle'}:result['reason']='motorcar exempt';continue
        if not restriction or not restriction.startswith(('no_','only_')):result['reason']='unsupported motor restriction type';continue
        roles={role:[m for m in rel.get('members',[]) if m['role']==role] for role in ['from','via','to']}
        if any(len(roles[role])!=1 for role in roles) or roles['via'][0]['type']!='node':result['reason']='multi-member or via-way restriction requires path state';continue
        via=roles['via'][0]['ref'];point=nodes.get(via)
        if point is None:result['reason']='missing via geometry';continue
        nearby=set();gx,gy=int(point[0]//10),int(point[1]//10)
        for x in range(gx-1,gx+2):
            for y in range(gy-1,gy+2):nearby.update(grid[(x,y)])
        candidates=sorted((min(math.dist(point,e['point']) for e in endpoints[j]),j) for j in nearby)
        candidates=[c for c in candidates if c[0]<=8]
        if not candidates or (len(candidates)>1 and candidates[1][0]-candidates[0][0]<2):result['reason']='missing or ambiguous NWB junction within 8m';continue
        distance,junction=candidates[0];matched={};failed=False
        for role in ['from','to']:
            member=roles[role][0];way=ways.get(member['ref']);possibilities=[]
            if not way or via not in way.get('nodes',[]):failed=True;break
            i=way['nodes'].index(via)
            for refs in [way['nodes'][i:],way['nodes'][:i+1][::-1]]:
                pts=[nodes[n] for n in refs if n in nodes];heading=bearing(pts) if len(pts)>1 else None
                if not heading:continue
                for edge in endpoints[junction]:
                    # NWB directions denote motor traffic. Is the edge oriented into/out of this node?
                    required='T' if (role=='from')==edge['start'] else 'H'
                    if edge['direction'] not in ('B',required):continue
                    dot=sum(a*b for a,b in zip(heading,edge['heading']))
                    nwbname,osmname=norm(edge['name']),norm(way.get('tags',{}).get('name'))
                    if nwbname and osmname:
                        if nwbname!=osmname or dot<.94:continue
                    elif distance>2 or dot<.985:continue
                    possibilities.append(edge)
            unique={e['id']:e for e in possibilities}
            if len(unique)!=1:failed=True;break
            matched[role]=next(iter(unique.values()))['id']
        if failed:result['reason']='missing or ambiguous name/direction/local-tangent match';continue
        result.update({'status':'review-candidate','restriction':restriction,'nwbJunction':junction,'fromNWB':matched['from'],'toNWB':matched['to'],'junctionDistanceMetres':round(distance,3)})
    return results

def main():
    p=argparse.ArgumentParser();p.add_argument('--download',action='store_true');p.add_argument('--input',type=Path);p.add_argument('--endpoint',default='https://overpass-api.de/api/interpreter');a=p.parse_args()
    source=SOURCE/'osm-centre-turn-restrictions.json.gz'
    if a.input:raw=a.input.read_bytes()
    elif a.download:
        data=urllib.parse.urlencode({'data':QUERY}).encode()
        request=urllib.request.Request(a.endpoint,data=data,headers={'User-Agent':'010 Rotterdam source audit','Content-Type':'application/x-www-form-urlencoded'})
        with urllib.request.urlopen(request,timeout=60) as response:raw=response.read()
    elif source.exists():raw=gzip.decompress(source.read_bytes())
    else:p.error('Use --download or --input overpass-response.json')
    osm=json.loads(raw)
    if osm.get('remark'):raise SystemExit('Incomplete Overpass response: '+osm['remark'])
    source.write_bytes(gzip.compress(raw,mtime=0))
    features=json.loads(gzip.decompress((SOURCE/'nwb-roads.geojson.gz').read_bytes()))['features']
    results=match_restrictions(osm,features)
    report={'acquiredAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'endpoint':a.endpoint if a.download else None,'query':QUERY,'license':'OpenStreetMap ODbL-1.0; attribution OpenStreetMap contributors required before runtime use','schema':'https://wiki.openstreetmap.org/wiki/Relation:restriction','rawSha256':hashlib.sha256(raw).hexdigest(),'nwbSha256':hashlib.sha256((SOURCE/'nwb-roads.geojson.gz').read_bytes()).hexdigest(),'status':'review only, not activated; matching source geometry is not proof of legal completeness','relations':results}
    (SOURCE/'osm-turn-restriction-audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'relations':len(results),'reviewCandidates':sum(r['status']=='review-candidate' for r in results)}))
if __name__=='__main__':main()
