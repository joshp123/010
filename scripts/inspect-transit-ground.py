#!/usr/bin/env python3
"""Exact source triangle intersections at lon lat; retained native BGT evidence, no scene mutation."""
import importlib.util,gzip,numpy as np,collections,json,sys
from pyproj import Transformer
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if '--refresh-report' in sys.argv:
 import subprocess
 report_path=ROOT/'source-data/transit-ground-evidence/inspection.json'
 report=json.loads(report_path.read_text())
 terrain={'Begroeid terreindeel','Onbegroeid terreindeel','Wegdeel','Ondersteunend wegdeel','Waterdeel','Ondersteunend waterdeel'}
 for sample in report['samples']:
  hits=json.loads(subprocess.check_output([sys.executable,__file__,str(sample['longitude']),str(sample['latitude'])]))
  eligible=[h for h in hits if h['attributes']['KLASSE_IMG'] in terrain and not any(term in (h['attributes'].get('KLASSE','')+' '+h['attributes'].get('FYSIEKVK','')).lower() for term in ['kade','muur','damwand','keerwand'])]
  sample.update(allIntersections=hits,highestAll=hits[0] if hits else None,highestSemanticTerrain=eligible[0] if eligible else None)
 report_path.write_text(json.dumps(report,indent=2)+'\n')
 print(report_path)
 raise SystemExit
spec=importlib.util.spec_from_file_location('centre',str(ROOT/'scripts/inspect-current-centre.py'));c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c);m=c.m
raw=gzip.decompress(open(ROOT/'source-data/transit-ground-evidence/33589-6931.b3dm.gz','rb').read());doc,binary,batch,feature=next(m.b3dm_parts(raw));lon,lat=map(float,sys.argv[1:3]) if len(sys.argv)>1 else (4.5126138,51.9251404)
xyz=Transformer.from_crs(4979,4978,always_xy=True).transform(lon,lat,0);lo,la=np.radians([lon,lat]);basis=np.array([[-np.sin(lo),np.cos(lo),0],[-np.sin(la)*np.cos(lo),-np.sin(la)*np.sin(lo),np.cos(la)],[np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)]])
yz=np.array([[1,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1]]);shift=np.eye(4);shift[:3,3]=feature['RTC_CENTER'];hits=[]
def visit(i,parent):
 n=doc['nodes'][i];mat=parent@np.array(n.get('matrix',np.eye(4).T.ravel())).reshape(4,4).T
 if 'mesh'in n:
  for p in doc['meshes'][n['mesh']]['primitives']:
   v=m.accessor(doc,binary,p['attributes']['POSITION']);idx=m.accessor(doc,binary,p['indices'])[:,0].reshape(-1,3);ids=m.accessor(doc,binary,p['attributes']['_BATCHID'])[:,0];world=(np.c_[v,np.ones(len(v))]@(shift@yz@mat).T)[:,:3];local=(world-np.array(xyz))@basis.T;tri=local[idx]
   possible=(tri[:,:,0].min(axis=1)<=0)&(tri[:,:,0].max(axis=1)>=0)&(tri[:,:,1].min(axis=1)<=0)&(tri[:,:,1].max(axis=1)>=0)
   for ix in np.where(possible)[0]:
    a,b,d=tri[ix];matrix=np.column_stack((b[:2]-a[:2],d[:2]-a[:2]));det=np.linalg.det(matrix)
    if abs(det)<1e-8:continue
    u,vv=np.linalg.solve(matrix,-a[:2])
    if u>=0 and vv>=0 and u+vv<=1:
     bid=int(ids[idx[ix,0]]);hits.append({'height':float(a[2]+u*(b[2]-a[2])+vv*(d[2]-a[2])),'id':batch['id'][bid],'attributes':batch['attributes'][bid]})
 for child in n.get('children',[]):visit(child,mat)
for root in doc['scenes'][doc.get('scene',0)]['nodes']:visit(root,np.eye(4))
print(json.dumps(sorted(hits,key=lambda x:x['height'],reverse=True),indent=2))
