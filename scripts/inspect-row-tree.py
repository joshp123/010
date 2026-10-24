#!/usr/bin/env python3
"""Decode retained i3dm instance dimensions/placement against the actual phone view."""
import gzip,struct,json,hashlib,importlib.util
from pathlib import Path
import numpy as np
from pyproj import Transformer
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'work/public-space-pilot';OUT.mkdir(exist_ok=True)
b=gzip.decompress((ROOT/'source-data/vegetation-style/15_33577_6934.cmpt.gz').read_bytes());p=16;geo=Transformer.from_crs(4978,4979,always_xy=True);earth=Transformer.from_crs(4979,4978,always_xy=True);rd=Transformer.from_crs(4978,28992,always_xy=True)
origin=np.array(earth.transform(4.49,51.915,0));lo,la=np.radians([4.49,51.915]);basis=np.array([[-np.sin(lo),np.cos(lo),0],[np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)],[np.sin(la)*np.cos(lo),np.sin(la)*np.sin(lo),-np.cos(la)]]);target=(np.array(earth.transform(4.44711,51.90963,0))-origin)@basis.T
bearing=np.radians(125);back=np.array([np.sin(bearing),1/np.sqrt(2),np.cos(bearing)]);back/=np.linalg.norm(back);right=np.cross([0,1,0],back);right/=np.linalg.norm(right);up=np.cross(back,right);camera=np.array([right,-up,back]);rows=[]
s=importlib.util.spec_from_file_location('m',ROOT/'scripts/prepare-building-appearance.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
for n in range(struct.unpack_from('<I',b,12)[0]):
 q=b[p:];length,fj,fb,bj,bb,fmt=struct.unpack_from('<6I',q,8);ft=json.loads(q[32:32+fj]);buf=q[32+fj:32+fj+fb];bt=json.loads(q[32+fj+fb:32+fj+fb+bj]);uri=q[32+fj+fb+bj+bb:length].decode().strip('\x00 ')
 def arr(key,dtype,ncomp=3):return np.frombuffer(buf,dtype,ft['INSTANCES_LENGTH']*ncomp,ft[key]['byteOffset']).reshape(-1,ncomp)
 pos=arr('POSITION_QUANTIZED','<u2')/65535*np.array(ft['QUANTIZED_VOLUME_SCALE'])+ft['QUANTIZED_VOLUME_OFFSET'];sc=arr('SCALE_NON_UNIFORM','<f4');normalup=arr('NORMAL_UP','<f4');normalright=arr('NORMAL_RIGHT','<f4');lon,lat,z=geo.transform(*pos.T);xx,yy,zz=rd.transform(*pos.T)
 # Decode actual GLB prototype positions, including node matrix; all raw bytes retained.
 raw=gzip.decompress((ROOT/'source-data/vegetation-style'/(Path(uri).name+'.gz')).read_bytes());jl=struct.unpack_from('<I',raw,12)[0];d=json.loads(raw[20:20+jl]);binary=raw[28+jl:];vertices=[]
 def visit(i,parent):
  node=d['nodes'][i];mat=parent@np.array(node.get('matrix',np.eye(4).T.ravel())).reshape(4,4).T
  if 'mesh'in node:
   for prim in d['meshes'][node['mesh']]['primitives']:
    v=m.accessor(d,binary,prim['attributes']['POSITION']);vertices.extend((np.c_[v,np.ones(len(v))]@mat.T)[:,:3])
  for child in node.get('children',[]):visit(child,mat)
 for root in d['scenes'][d.get('scene',0)]['nodes']:visit(root,np.eye(4))
 vertices=np.array(vertices);adjust=np.array([[1,0,0],[0,0,-1],[0,1,0]])
 for i,a in enumerate(bt['attributes']):
  if a['tree_part']!='kruin':continue
  rotation=np.column_stack([normalright[i],normalup[i],np.cross(normalright[i],normalup[i])]);linear=rotation@np.diag(sc[i])@adjust;world=vertices@linear.T+pos[i];local=(world-origin)@basis.T;projected=(local-target)@camera.T;screen=projected[:,:2]*8.44+[195,422];bound=[*screen.min(0),*screen.max(0)];centre=(pos[i]-origin)@basis.T;dist=np.linalg.norm((centre-target)[[0,2]])
  if dist>180:continue
  crownLo,crownLa,crownZ=geo.transform(*world.T);row={'id':bt['id'][i],'prototype':uri,'instance':i,'distance':float(dist),'lonlat':[float(lon[i]),float(lat[i])],'rd':[float(xx[i]),float(yy[i])],'sourceCrownBaseHeight':float(z[i]),'sourceScale':sc[i].tolist(),'attributes':a,'actualPrototypeBounds':[vertices.min(0).tolist(),vertices.max(0).tolist()],'crownWorldHeightRange':[float(np.min(crownZ)),float(np.max(crownZ))],'screenBounds390x844':bound,'rotationColumnLengths':np.linalg.norm(rotation,axis=0).tolist()};rows.append(row)
 p+=length
rows.sort(key=lambda a:np.linalg.norm((np.array(a['screenBounds390x844'][:2])+np.array(a['screenBounds390x844'][2:]))/2-[153,110]));report={'sourceSha256':hashlib.sha256(b).hexdigest(),'camera':{'lat':51.90963,'lon':4.44711,'span':100,'bearing':125,'viewport':[390,844]},'method':'Exact i3dm quantized POSITION, NORMAL_RIGHT/UP, SCALE_NON_UNIFORM, glTF prototype positions+node transforms, source Y-up-to-Z-up adjustment, then same local Earth and orthographic camera frame. Does not yet compare live renderer matrices.','nearestToObservedCrown':rows[:5],'nearbySourceCrowns':rows};(OUT/'tree-instance-audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(rows[:3],indent=2))
