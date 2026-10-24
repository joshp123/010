"""Check delivered geometry/identity and native texture samples, not art acceptance."""
import collections,importlib.util,json,struct
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];spec=importlib.util.spec_from_file_location('source',ROOT/'scripts/prepare-building-appearance.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def read(path):
 b=path.read_bytes();n=struct.unpack_from('<I',b,12)[0];return json.loads(b[20:20+n]),b[28+n:]
image_cache={}
def samples(folder,doc,texture,uv,guard=False):
 if texture is None:return np.zeros((len(uv),3),dtype='uint8')
 path=folder/doc['images'][doc['textures'][texture['index']]['source']]['uri']
 if path not in image_cache:image_cache[path]=np.array(Image.open(path).convert('RGB'))
 image=image_cache[path];transform=texture.get('extensions',{}).get('KHR_texture_transform',{});mapped=uv*np.array(transform.get('scale',[1,1]))+transform.get('offset',[0,0]);pixels=mapped*[image.shape[1],image.shape[0]]-.5;lo=np.floor(pixels).astype(int);fraction=pixels-lo;color=np.zeros((len(uv),3),dtype=float)
 for dx,dy in [(0,0),(0,1),(1,0),(1,1)]:
  weight=(fraction[:,0] if dx else 1-fraction[:,0])*(fraction[:,1] if dy else 1-fraction[:,1]);color+=image[np.clip(lo[:,1]+dy,0,image.shape[0]-1),np.clip(lo[:,0]+dx,0,image.shape[1]-1)]*weight[:,None]
 if guard:color[np.any((mapped<0)|(mapped>1),axis=1)]=0
 return color
for label,out in [('row-v5','illustrated-neighbourhood/row'),('apartment','illustrated-neighbourhood/apartment'),('tank','illustrated-tank')]:
 folder=ROOT/'source-data/bound-artwork'/label;meta=json.loads((folder/'georeference-and-identities.json').read_text());src,sb=read(folder/meta['geometry_asset']);target=ROOT/'public/data'/out;doc,db=read(target/'model.glb');key='bagId' if meta['identity_namespace']=='BAG' else 'featureId';expected=collections.Counter();actual=collections.Counter();count=0
 assert doc['nodes'][0]['matrix']==src['nodes'][0]['matrix'];assert 'CESIUM_RTC' not in doc.get('extensions',{});assert json.loads((target/'tileset.json').read_text())['root']['children'][0]['transform'][12:15]==meta['rtc_ecef_m'];assert 'KHR_texture_transform' in doc['extensionsRequired']
 for mi,mesh in enumerate(src['meshes']):
  for pi,p in enumerate(mesh['primitives']):
   ix=m.accessor(src,sb,p['indices'])[:,0].reshape(-1,3);names=sorted(p['attributes']);values=[m.accessor(src,sb,p['attributes'][n]) for n in names]
   for tri in ix:expected[(mi,pi,b''.join(v[tri].tobytes() for v in values))]+=1
 for mesh in doc['meshes']:
  ex=mesh['extras'];mi,pi=ex['sourceMesh'],ex['sourcePrimitive'];original=src['meshes'][mi]['primitives'][pi];source_material=src['materials'][original['material']]
  for p in mesh['primitives']:
   assert p['extras'][key]==ex[key];assert (key=='bagId' and ex[key].isdigit()) or (key=='featureId' and ex[key].startswith('OST_'))
   ix=m.accessor(doc,db,p['indices'])[:,0].reshape(-1,3);names=sorted(p['attributes']);assert names==sorted(original['attributes']);values=[m.accessor(doc,db,p['attributes'][n]) for n in names]
   for tri in ix:actual[(mi,pi,b''.join(v[tri].tobytes() for v in values))]+=1
   count+=len(ix);mat=doc['materials'][p['material']]
   if 'TEXCOORD_0' in p['attributes']:
    uv=m.accessor(doc,db,p['attributes']['TEXCOORD_0'])[ix].mean(axis=1)
    for channel in ('base','emission'):
     a=source_material.get('pbrMetallicRoughness',{}).get('baseColorTexture') if channel=='base' else source_material.get('emissiveTexture');b=mat.get('pbrMetallicRoughness',{}).get('baseColorTexture') if channel=='base' else mat.get('emissiveTexture');
     try:np.testing.assert_allclose(samples(folder,src,a,uv),samples(target,doc,b,uv,channel=='emission'),atol=.001)
     except AssertionError:
      print('FAIL',label,ex,'material',p['material'],channel,'uv',uv,'source',a,'target',b);raise
   if mat.get('emissiveTexture'):assert label=='row-v5' and mat['extras']['emissionCropGuard'] and mat['emissiveFactor']==[1,1,1]
 assert actual==expected and count==meta['triangles'];assert all('.writing.' not in im['uri'] and (target/im['uri']).exists() for im in doc['images'])
 print(label,': exact triangle attributes/UV/identity, RTC once, native colour+guarded emission samples pass; triangles',count)
