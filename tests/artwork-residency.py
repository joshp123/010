#!/usr/bin/env python3
"""Check retained artwork geometry, colour texels and glazing across residency cuts."""
import importlib.util,io,json,struct
from pathlib import Path
import numpy as np
from PIL import Image,ImageChops
spec=importlib.util.spec_from_file_location('appearance',Path(__file__).resolve().parents[1]/'scripts/prepare-building-appearance.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def load(path):
 raw=path.read_bytes();size=struct.unpack_from('<I',raw,12)[0];d=json.loads(raw[20:20+size]);b=raw[28+size:];images=[]
 for im in d['images']:
  if 'uri' in im:data=(path.parent/im['uri']).read_bytes()
  else:
   v=d['bufferViews'][im['bufferView']];data=b[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']]
  images.append(Image.open(io.BytesIO(data)).convert('RGB'))
 return d,b,images
for name in ['adjoining32','north18']:
 folder=Path(__file__).resolve().parents[1]/'public/data/illustrated-neighbourhood'
 src,sb,si=load(folder/name/'model.glb');count=0
 for record in json.loads((folder/(name+'-spatial')/'residency.json').read_text())['buildings']:
  out,ob,oi=load(folder/(name+'-spatial')/record['output']);source_meshes=[mesh for mesh in src['meshes'] if mesh['extras']['bagId']==record['bagId']]
  assert len(source_meshes)==len(out['meshes'])
  for source_mesh,mesh in zip(source_meshes,out['meshes']):
   assert len(source_mesh['primitives'])==len(mesh['primitives'])
   for p,q in zip(source_mesh['primitives'],mesh['primitives']):
    ix=m.accessor(src,sb,p['indices'])[:,0];jx=m.accessor(out,ob,q['indices'])[:,0]
    assert np.array_equal(m.accessor(src,sb,p['attributes']['POSITION'])[ix],m.accessor(out,ob,q['attributes']['POSITION'])[jx])
    if 'emissiveTexture' in out['materials'][q['material']]:
     crop=next(c for c in out['extras']['sourceEmissionCrops'] if c['material']==q['material']);uv_name=crop['texCoord'];lo=np.array(crop['sourceCrop'][:2]);hi=np.array(crop['sourceCrop'][2:]);size=np.array(crop['sourceSize'])
     original=m.accessor(src,sb,p['attributes'][uv_name])[ix];recovered=(m.accessor(out,ob,q['attributes'][uv_name])[jx]*(hi-lo)+lo)/size
     assert np.allclose(original,recovered,atol=2e-6)
     texture=out['materials'][q['material']]['emissiveTexture']['index'];packed=oi[out['textures'][texture]['source']];expected=si[src['textures'][crop['sourceTexture']]['source']].crop(crop['sourceCrop'])
     assert ImageChops.difference(packed,expected).getbbox() is None
  for island in out['extras']['texturePacking']['islands']:
   x,y=island['packedOrigin'];w,h=island['width'],island['height'];expected=si[island['sourceImage']].crop(island['sourceCrop']);actual=oi[0].crop((x,y,x+w,y+h));assert ImageChops.difference(actual,expected).getbbox() is None
  count+=1
 print(name,count,'buildings preserve triangle positions, colour texels and observed glazing mapping')
