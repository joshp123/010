#!/usr/bin/env python3
"""Native source triangle/pixel/identity and per-OST residency checks."""
import importlib.util,json,gzip,io
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'public/data/current-tank-appearance'
s=importlib.util.spec_from_file_location('m',ROOT/'scripts/prepare-building-appearance.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);m.OUTPUT=OUT
manifest=json.loads((OUT/'manifest.json').read_text());tiles=json.loads((OUT/'tileset.json').read_text());raw=gzip.decompress((ROOT/manifest['retainedRaw']).read_bytes());assert m.digest(raw)==manifest['sourceSha256'];a,ab,bt,ft=next(m.b3dm_parts(raw));n,nb=m.read_glb((OUT/manifest['nativeReference']['output']).read_bytes());assert n['materials']==a['materials'];assert set(manifest['featureIds'])==set(bt['id']);assert tiles['root']['children'][0]['transform'][12:15]==ft['RTC_CENTER'];expected=[]
for mesh in a['meshes']:
 groups={}
 for p in mesh['primitives']:
  ix=m.accessor(a,ab,p['indices'])[:,0].reshape(-1,3);bid=m.accessor(a,ab,p['attributes']['_BATCHID'])[:,0]
  for i in range(len(bt['id'])):
   chosen=ix[bid[ix[:,0]]==i]
   if len(chosen):groups.setdefault(i,[]).append((p,chosen))
 for i,prims in groups.items():expected.append((bt['id'][i],prims))
assert len(expected)==len(n['meshes']);triangles=0
for (fid,prims),mesh in zip(expected,n['meshes']):
 assert mesh['extras']['featureId']==fid and mesh['name']==fid
 for (p,ix),q in zip(prims,mesh['primitives']):
  j=m.accessor(n,nb,q['indices'])[:,0].reshape(-1,3);triangles+=len(j)
  for k,ai in q['attributes'].items():np.testing.assert_array_equal(m.accessor(a,ab,p['attributes'][k])[ix],m.accessor(n,nb,ai)[j])
def image(d,b,ii):
 v=d['bufferViews'][d['images'][ii]['bufferView']];return np.array(Image.open(io.BytesIO(b[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']])).convert('RGB'))
images=[image(n,nb,i) for i in range(len(n['images']))]
for i,im in enumerate(images):np.testing.assert_array_equal(im,image(a,ab,i))
crops=0;leaf_triangles=0
for e in manifest['features']:
 p=OUT/e['output'];assert m.digest(p.read_bytes())==e['sha256'];d,b=m.read_glb(p.read_bytes());packing=d['extras']['texturePacking'];assert packing['featureId']==e['featureId'];assert 'bagId' not in json.dumps(d) and 'BAG_' not in json.dumps(d);assert packing['sourceAssetSha256']==manifest['nativeReference']['sha256'];im=image(d,b,0)
 source=[(i,x) for i,x in enumerate(n['meshes']) if x['extras']['featureId']==e['featureId']]
 for (mi,sm),dm in zip(source,d['meshes']):
  for pi,(sp,dp) in enumerate(zip(sm['primitives'],dm['primitives'])):
   si=m.accessor(n,nb,sp['indices'])[:,0].reshape(-1,3);di=m.accessor(d,b,dp['indices'])[:,0].reshape(-1,3);leaf_triangles+=len(di)
   for k in sp['attributes']:
    av=m.accessor(n,nb,sp['attributes'][k])[si];bv=m.accessor(d,b,dp['attributes'][k])[di]
    if k!='TEXCOORD_0':np.testing.assert_array_equal(av,bv)
    else:
     for r in packing['islands']:
      if r['sourceMesh']!=mi or r['sourcePrimitive']!=pi:continue
      rows=r['sourceTriangles'];restored=(bv[rows]*packing['atlasSize']-r['packedOrigin']+r['sourceCrop'][:2])/r['sourceSize'];assert np.max(abs(restored-av[rows])*r['sourceSize'])<.001
 for r in packing['islands']:
  x,y=r['packedOrigin'];x0,y0,x1,y1=r['sourceCrop'];np.testing.assert_array_equal(im[y:y+y1-y0,x:x+x1-x0],images[r['sourceImage']][y0:y1,x0:x1]);crops+=1
 points=[]
 for node in d['nodes']:
  mat=np.array(node['matrix']).reshape(4,4,order='F')
  for p in d['meshes'][node['mesh']]['primitives']:
   pos=m.accessor(d,b,p['attributes']['POSITION']);points.extend((np.c_[pos,np.ones(len(pos))]@mat.T)[:,:3][:,[0,2,1]]*[1,-1,1])
 box=np.array(e['boundingVolume']['box']);axes=box[3:].reshape(3,3,order='F');assert np.all(abs((np.array(points)-box[:3])@np.linalg.inv(axes).T)<=1+1e-7)
assert triangles==leaf_triangles==2996
for p in OUT.iterdir():
 if p.is_file():assert p.stat().st_size<=25*1024*1024
print(json.dumps({'literalOSTFeatures':len(manifest['features']),'exactSourceAndLeafTriangles':triangles,'exactSourceImages':len(images),'exactPixelCrops':crops,'maxAssetBytes':manifest['largestAssetBytes']}))

report=json.loads((ROOT/'source-data/tank-reconciliation/report.json').read_text());assert not report['missing'] and set(report['matched'])==set(manifest['featureIds'])
oldpath=ROOT/'source-data/tank-reconciliation/raw/16_67119_13875.b3dm.gz';oldraw=gzip.decompress(oldpath.read_bytes());oldids=set()
for _,_,batch,_ in m.b3dm_parts(oldraw):oldids.update(batch['id'])
assert oldids==set(manifest['featureIds'])
print('Exact old/current OST replacement identities verified:14')
