#!/usr/bin/env python3
"""Compare exact georeferenced native observations without assuming shared UVs."""
import importlib.util,gzip,json
from pathlib import Path
import numpy as np
from pyproj import Transformer
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('m',ROOT/'scripts/prepare-building-appearance.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
ecef=Transformer.from_crs(4978,4979,always_xy=True);rd=Transformer.from_crs(4326,28992,always_xy=True);yz=np.array([[1,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1]])
def inspect(path,bag):
 raw=gzip.decompress(path.read_bytes());points=[];triangles=0
 for d,b,bt,f in m.b3dm_parts(raw):
  ids=[x.removeprefix('ID_').removeprefix('BAG_') for x in bt['id']]
  if bag not in ids:continue
  bid=ids.index(bag);rtc=np.eye(4);rtc[:3,3]=d.get('extensions',{}).get('CESIUM_RTC',{}).get('center',f.get('RTC_CENTER'))
  def walk(i,mat):
   nonlocal triangles
   n=d['nodes'][i];mat=mat@np.array(n.get('matrix',np.eye(4).T.ravel())).reshape(4,4).T
   if 'mesh' in n:
    for p in d['meshes'][n['mesh']]['primitives']:
     ids=m.accessor(d,b,p['attributes']['_BATCHID'])[:,0];ix=(m.accessor(d,b,p['indices'])[:,0] if 'indices' in p else np.arange(len(ids))).reshape(-1,3);ix=ix[ids[ix[:,0]]==bid];triangles+=len(ix)
     if len(ix):
      v=m.accessor(d,b,p['attributes']['POSITION'])[ix.ravel()];v=np.c_[v,np.ones(len(v))]@(rtc@yz@mat).T;lon,lat,z=ecef.transform(v[:,0],v[:,1],v[:,2]);x,y=rd.transform(lon,lat);points.extend(np.c_[x,y,z])
   for c in n.get('children',[]):walk(c,mat)
  for i in d['scenes'][d.get('scene',0)]['nodes']:walk(i,np.eye(4))
 assert points,path
 p=np.array(points);return {'sourceSha256':m.digest(raw),'triangles':triangles,'boundsRDandEllipsoidalHeight':[p.min(0).tolist(),p.max(0).tolist()]}
rows=[]
for bag,old,new in [('0599100000670808','17_134310_27737.cmpt.gz','current-building-evidence/raw/18_268621_55475.b3dm.gz'),('0599100000671675','17_134310_27736.cmpt.gz','current-row-evidence/raw/18_268620_55473.b3dm.gz')]:
 a=inspect(ROOT/'source-data/building-appearance/raw'/old,bag);b=inspect(ROOT/'source-data'/new,bag);rows.append({'bagId':bag,'legacy':a,'current':b,'boundsDeltaMeters':(np.array(b['boundsRDandEllipsoidalHeight'])-np.array(a['boundsRDandEllipsoidalHeight'])).tolist()})
result={'note':'Native geometry compared in RD xy and ellipsoidal height; no matching topology or UV assumed. These deltas do not establish which survey is more accurate.','buildings':rows};(ROOT/'source-data/current-building-evidence/edition-shape-comparison.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
