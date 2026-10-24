#!/usr/bin/env python3
"""Projected source UV footprints, not GPU or environment-visibility measurements."""
import importlib.util,json,struct,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('source',ROOT/'scripts/prepare-building-appearance.py');source=importlib.util.module_from_spec(s);s.loader.exec_module(source)
raw=(ROOT/'public/data/illustrated-row/row.glb').read_bytes();n=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+n]);binary=raw[28+n:]
lat,lon=np.radians([51.915,4.49]);ecef_to_local=np.array([[-np.sin(lon),np.cos(lon),0],[np.cos(lat)*np.cos(lon),np.cos(lat)*np.sin(lon),np.sin(lat)],[np.sin(lat)*np.cos(lon),np.sin(lat)*np.sin(lon),-np.cos(lat)]])
yz=np.array([[1,0,0],[0,0,-1],[0,1,0]])
triangles=[]
def walk(i,parent):
 node=doc['nodes'][i];mat=parent@np.array(node.get('matrix',np.eye(4).T.ravel())).reshape(4,4).T
 if 'mesh' in node:
  for p in doc['meshes'][node['mesh']]['primitives']:
   if 'TEXCOORD_0' not in p['attributes']:continue
   pos=source.accessor(doc,binary,p['attributes']['POSITION']);uv=source.accessor(doc,binary,p['attributes']['TEXCOORD_0']);ix=source.accessor(doc,binary,p['indices']).ravel().reshape(-1,3)
   points=(np.c_[pos,np.ones(len(pos))]@mat.T)[:,:3]@yz.T@ecef_to_local.T
   triangles.extend(zip(points[ix],uv[ix]*2048))
 for child in node.get('children',[]):walk(child,mat)
for i in doc['scenes'][doc.get('scene',0)]['nodes']:walk(i,np.eye(4))
def quantile(values,weights,q):
 order=np.argsort(values);v=np.asarray(values)[order];w=np.asarray(weights)[order];return float(v[np.searchsorted(np.cumsum(w),sum(w)*q)])
result={'geometrySha256':hashlib.sha256(raw).hexdigest(),'assumptions':'Exact orthographic scene direction, span100, source 2048 atlases. Area-weighted projected facade triangles, both orientations because material is DoubleSide. No self/environment occlusion or canvas capture; DPR1/2 are explicit scenarios, not measured devices. Orthographic derivatives independent of target translation and viewport width.','cases':[]}
for bearing in [35,125]:
 direction=np.array([np.sin(np.radians(bearing)),1/np.sqrt(2),np.cos(np.radians(bearing))]);direction/=np.linalg.norm(direction);right=np.cross([0,1,0],direction);right/=np.linalg.norm(right);up=np.cross(direction,right)
 for height in [844,720]:
  for dpr in [1,2]:
   majors=[];minors=[];ratios=[];weights=[]
   for xyz,uv in triangles:
    normal=np.cross(xyz[1]-xyz[0],xyz[2]-xyz[0]);length=np.linalg.norm(normal)
    if length<1e-10 or abs(normal[1]/length)>.2:continue
    screen=xyz@np.array([right,up]).T*(height*dpr/100)
    a=(screen[1:]-screen[0]).T;area=abs(np.linalg.det(a))/2
    if area<.01:continue
    j=(uv[1:]-uv[0]).T@np.linalg.inv(a);sv=np.linalg.svd(j,compute_uv=False)
    if sv[1]<1e-8:continue
    majors.append(sv[0]);minors.append(sv[1]);ratios.append(sv[0]/sv[1]);weights.append(area)
   result['cases'].append({'bearing':bearing,'cssHeight':height,'assumedDpr':dpr,'bufferHeight':height*dpr,'triangles':len(weights),'areaWeightedMedianTexelsPerPixelMajor':quantile(majors,weights,.5),'areaWeightedMedianTexelsPerPixelMinor':quantile(minors,weights,.5),'areaWeightedMedianAnisotropy':quantile(ratios,weights,.5),'areaWeightedP90Anisotropy':quantile(ratios,weights,.9)})
print(json.dumps(result,indent=2))
