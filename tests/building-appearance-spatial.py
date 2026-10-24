#!/usr/bin/env python3
"""Native per-BAG residency: exact texels/triangles, invertible UVs, tight boxes."""
import importlib.util,io,json
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('m',ROOT/'scripts/prepare-building-appearance.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
manifest=json.loads((m.OUTPUT/'manifest.json').read_text());tile_roots=json.loads((m.OUTPUT/'tileset.json').read_text())['root']['children']
def image(doc,binary,ii):
 v=doc['bufferViews'][doc['images'][ii]['bufferView']];return np.asarray(Image.open(io.BytesIO(binary[v['byteOffset']:v['byteOffset']+v['byteLength']])).convert('RGB'))
count=triangles=crops=total=0;max_uv_error=0
for entry,root in zip(manifest['entries'],tile_roots):
 a,ab=m.read_glb((m.OUTPUT/entry['output']).read_bytes());source_images=[image(a,ab,i) for i in range(len(a['images']))]
 nodes={}
 def collect(node):
  for child in node.get('children',[]):
   assert 'transform' not in child;collect(child)
  if not node.get('children'):nodes[node['content']['uri']]=node
 collect(root)
 assert set(nodes)=={x['output'] for x in entry['spatialBuildings']}
 for leaf in entry['spatialBuildings']:
  raw=(m.OUTPUT/leaf['output']).read_bytes();b,bb=m.read_glb(raw);packing=b['extras']['texturePacking'];bag=leaf['bagId']
  assert m.digest(raw)==leaf['sha256'];assert packing['sourceAssetSha256']==m.digest((m.OUTPUT/entry['output']).read_bytes())
  atlas=image(b,bb,0);source_meshes=[(i,x) for i,x in enumerate(a['meshes']) if x['extras']['bagId']==bag]
  assert len(source_meshes)==len(b['meshes']);points=[]
  for (mi,am),bm in zip(source_meshes,b['meshes']):
   for pi,(ap,bp) in enumerate(zip(am['primitives'],bm['primitives'])):
    ai=m.accessor(a,ab,ap['indices'])[:,0].reshape(-1,3);bi=m.accessor(b,bb,bp['indices'])[:,0].reshape(-1,3);assert ai.shape==bi.shape;triangles+=len(ai)
    for semantic in ap['attributes']:
     av=m.accessor(a,ab,ap['attributes'][semantic])[ai];bv=m.accessor(b,bb,bp['attributes'][semantic])[bi]
     if semantic!='TEXCOORD_0':assert np.array_equal(av,bv),(bag,semantic)
     else:
      islands=[r for r in packing['islands'] if r['sourceMesh']==mi and r['sourcePrimitive']==pi]
      for r in islands:
       rows=r['sourceTriangles'];restored=(bv[rows]*packing['atlasSize']-r['packedOrigin']+r['sourceCrop'][:2])/r['sourceSize']
       error=float(np.max(abs(restored-av[rows])));max_uv_error=max(max_uv_error,error);assert error<3e-7
  for r in packing['islands']:
   x,y=r['packedOrigin'];x0,y0,x1,y1=r['sourceCrop'];source=source_images[r['sourceImage']][y0:y1,x0:x1]
   assert np.array_equal(atlas[y:y+len(source),x:x+source.shape[1]],source);crops+=1
  for node in b['nodes']:
   matrix=np.array(node['matrix']).reshape(4,4,order='F')
   for p in b['meshes'][node['mesh']]['primitives']:
    pos=m.accessor(b,bb,p['attributes']['POSITION']);v=np.c_[pos,np.ones(len(pos))]@matrix.T;points.extend(v[:,:3][:,[0,2,1]]*[1,-1,1])
  points=np.asarray(points);box=np.array(leaf['boundingVolume']['box']);c=box[:3];axes=box[3:].reshape(3,3,order='F')
  normalized=(points-c)@np.linalg.inv(axes).T
  assert np.all(abs(normalized)<=1+1e-7)
  half=np.linalg.norm(axes,axis=0);frame=axes/half;projected=points@frame
  assert np.max(abs((projected.max(axis=0)-projected.min(axis=0))/2+.001-half))<1e-7
  assert nodes[leaf['output']]['boundingVolume']==leaf['boundingVolume'];assert nodes[leaf['output']]['geometricError']==0
  # Independent geographic envelope check catches axis/RTC mistakes.
  earth=c+np.array(root['transform'][12:15]);x,y,z=earth;longitude=np.arctan2(y,x);radius=np.hypot(x,y);latitude=np.arctan2(z,radius*(1-.00669437999014))
  for _ in range(8):
   n=6378137/np.sqrt(1-.00669437999014*np.sin(latitude)**2);latitude=np.arctan2(z+.00669437999014*n*np.sin(latitude),radius)
  west,south,east,north=entry['boundingVolume']['region'][:4]
  assert west-2e-6<=longitude<=east+2e-6 and south-2e-6<=latitude<=north+2e-6, (bag,latitude,longitude)
  count+=1;total+=leaf['decodedRgbaBytesIncludingMips']
print(json.dumps({'buildingContents':count,'exactTriangles':triangles,'exactSourcePixelRectangles':crops,'maxInverseUvError':max_uv_error,'allBuildingNativeDecodedMiB':total/1048576},indent=2))
