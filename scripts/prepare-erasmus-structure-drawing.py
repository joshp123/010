#!/usr/bin/env python3
"""Source-plane drawing substrate for the retained Erasmus structure.
Written by AI on 2026-10-25 by model GPT-6 Astra.
Original triangle positions are retained; generated UVs provide drawing storage only.
"""
import importlib.util,json,math
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('bridge',ROOT/'scripts/build-bridge-surfaces.py');bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
review=next(r for r in bridge.reviews['reviews'] if r['name']=='erasmus')
triangles=bridge.load_native_triangles(review['sha256'])
centre=(triangles.reshape(-1,3).min(0)+triangles.reshape(-1,3).max(0))/2
positions=(triangles-centre)[...,[0,2,1]];positions[...,2]*=-1
page_size=4096;pixels_per_metre=6;gutter=3
pages=[];records=[];page=0;x=gutter;y=gutter;row_height=0
normals=np.cross(positions[:,1]-positions[:,0],positions[:,2]-positions[:,0]);normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-12)
parent=np.arange(len(positions));edges={}
def root(i):
 while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
 return i
for i,t in enumerate(positions):
 keys=[tuple(v) for v in np.round(t,3)]
 for a,b in [(0,1),(1,2),(2,0)]:
  key=tuple(sorted((keys[a],keys[b])))
  for other in edges.get(key,[]):
   if normals[i]@normals[other]>.99999:parent[root(i)]=root(other)
  edges.setdefault(key,[]).append(i)
groups={}
for i in range(len(positions)):groups.setdefault(root(i),[]).append(i)
for members in sorted(groups.values(),key=lambda g:len(g),reverse=True):
 t=positions[members[0]];edge=t[1]-t[0];normal=normals[members[0]];length=np.linalg.norm(edge)
 if length<1e-9:continue
 right=edge/length;up=np.cross(normal,right);basis=np.stack([right,up],axis=1)
 local=(positions[members]-t[0])@basis;lo=local.reshape(-1,2).min(0);extent=np.ptp(local.reshape(-1,2),axis=0)
 width,height=np.maximum(1,np.ceil(extent*pixels_per_metre).astype(int))+gutter*2
 if width>page_size or height>page_size:raise ValueError('Source plane exceeds native drawing page')
 if x+width>page_size:x=gutter;y+=row_height;row_height=0
 if y+height>page_size:page+=1;x=gutter;y=gutter;row_height=0
 for i,triangle_local in zip(members,local):
  uv=(triangle_local-lo)*pixels_per_metre+[x+gutter,y+gutter]
  records.append({'sourceTriangle':i,'image':page,'uv':(uv/page_size).tolist(),'identity':'br05A040'})
 x+=int(width);row_height=max(row_height,int(height))
for i in range(page+1):pages.append(np.full((page_size,page_size,3),[194,205,206],np.uint8))
out=ROOT/'source-data/erasmus-structure-drawing';out.mkdir(exist_ok=True)
np.savez_compressed(out/'source-planes.npz',positions=positions,sourceCentreRD=centre)
(out/'source-planes.json').write_text(json.dumps({'authorship':'Written by AI on 2026-10-25 by model GPT-6 Astra','sourceURL':review['url'],'sourceDecodedSha256':review['sha256'],'sourceCentreRD':centre.tolist(),'pixelsPerMetre':pixels_per_metre,'pageSize':page_size,'triangles':records},separators=(',',':'))+'\n')
for i,image in enumerate(pages):Image.fromarray(image).save(out/f'native-atlas-{i}.png')
print(json.dumps({'pages':len(pages),'sourceTriangles':len(triangles),'retainedTriangles':len(records)}))
