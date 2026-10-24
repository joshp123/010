#!/usr/bin/env python3
import argparse,gzip,hashlib,importlib.util,json
from pathlib import Path
import numpy as np
from PIL import Image
R=Path(__file__).resolve().parents[1];s=importlib.util.spec_from_file_location('m',R/'scripts/prepare-building-appearance.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
p=argparse.ArgumentParser();p.add_argument('package',type=Path);a=p.parse_args();meta=json.loads((a.package/'binding.json').read_text());z=np.load(a.package/'source-triangles.npz');P=z['positions'];U=z['uv'];I=z['image_index'];frame=np.array(meta['commonFrame']['ecefToEastUpSouth']);origin=np.array(meta['commonFrame']['originECEF']);yz=np.array([[1,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1]]);images={};total=0
for src in meta['sources']:
 raw=gzip.decompress((R/src['rawPath']).read_bytes());assert hashlib.sha256(raw).hexdigest()==src['sourceSha256'];d,b,bt,ft=list(m.b3dm_parts(raw))[src['part']];matrices={}
 def walk(i,parent):
  n=d['nodes'][i];matrix=parent@np.array(n.get('matrix',np.eye(4).T.ravel())).reshape(4,4).T;matrices[i]=matrix
  for c in n.get('children',[]):walk(c,matrix)
 for i in d['scenes'][d.get('scene',0)]['nodes']:walk(i,np.eye(4))
 rtc=np.eye(4);rtc[:3,3]=ft['RTC_CENTER'];start,end=src['triangleRange']
 for t in range(start,end):
  ref=meta['triangleBindings'][t];pr=d['meshes'][ref['mesh']]['primitives'][ref['primitive']];ix=m.accessor(d,b,pr['indices']).ravel().reshape(-1,3)[ref['sourceTriangle']];assert ix.tolist()==ref['sourceIndices'];pos=m.accessor(d,b,pr['attributes']['POSITION'])[ix];world=(np.c_[pos,np.ones(3)]@(rtc@yz@matrices[ref['node']]).T)[:,:3];np.testing.assert_allclose(P[t],(world-origin)@frame.T,atol=1e-9);assert pr['material']==ref['sourceMaterial'];assert bt['id'][ref['sourceBatchId']]==ref['featureId']
  if 'TEXCOORD_0' in pr['attributes']:np.testing.assert_array_equal(U[t],m.accessor(d,b,pr['attributes']['TEXCOORD_0'])[ix])
  total+=1
 for image in src['images']:
  data=(a.package/image['uri']).read_bytes();assert hashlib.sha256(data).hexdigest()==image['sha256'];images[image['globalImage']]=np.array(Image.open(a.package/image['uri']).convert('RGB'))
checks=0
for name,cam in meta['cameras'].items():
 v=dict(np.load(a.package/f'{name}-projection.npz'));tri=v['triangle_index'];rgb=np.array(Image.open(a.package/f'{name}.png'));yy,xx=np.nonzero(tri>=0);stride=max(1,len(xx)//2000)
 for y,x in zip(yy[::stride],xx[::stride]):
  t=tri[y,x];q=np.c_[P[t],np.ones(3)]@np.array(cam['localToImageDepth']).T;weights=np.linalg.solve(np.vstack([q[:,:2].T,np.ones(3)]),[x,y,1]);np.testing.assert_allclose(weights@U[t],v['uv'][y,x],atol=1e-7,equal_nan=True);point=np.array(cam['imageDepthToLocal'])@[x,y,float(v['depth'][y,x]),1];np.testing.assert_allclose(point[:3],weights@P[t],atol=1e-5)
  if I[t]>=0:
   im=images[I[t]];uv=weights@U[t];px=np.clip(np.floor(uv*[im.shape[1],im.shape[0]]).astype(int),[0,0],[im.shape[1]-1,im.shape[0]-1]);stored=v['source_texel'][y,x];assert np.all(np.abs(stored-px)<=1);np.testing.assert_array_equal(rgb[y,x],im[stored[1],stored[0]])
  checks+=1
for panel in meta['modelPanels']:
 x,y,w,h=panel['viewCropXYWH'];actual=Image.open(a.package/panel['uri']);expected=Image.open(a.package/(panel['view']+'.png')).crop((x,y,x+w,y+h));assert actual.tobytes()==expected.tobytes();matrix=np.array(meta['cameras'][panel['view']]['localToImageDepth']);matrix[0,3]-=x;matrix[1,3]-=y;np.testing.assert_array_equal(matrix,panel['localToPanelDepth'])
print(json.dumps({'trianglesVerified':total,'viewPixelCorrespondencesVerified':checks,'features':len(set(x['featureId'] for x in meta['triangleBindings'])),'sources':len(meta['sources']),'overlappingPanelsVerified':len(meta['modelPanels']),'result':'Exact source XYZ/UV/material/BAG and shared-view inverseprojection/sample identity pass'}))
