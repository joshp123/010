#!/usr/bin/env python3
"""Bind reviewed bridge drawing fields to retained structural planes.
Written by AI on 2026-10-25 by model GPT-6 Astra.
"""
import json,struct,hashlib,shutil
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
context={'__file__':str(ROOT/'scripts/render-erasmus-drawing-source.py'),'__name__':'erasmus_source'}
import sys
sys.argv=['render','--reconciled']
exec((ROOT/'scripts/render-erasmus-drawing-source.py').read_text().split('plans=[]')[0],context)
source=context['source'];views=context['views'];out=context['out'];metadata=context['metadata'];centre=context['centre'];count=len(metadata['triangles']);pages=1+max(t['image'] for t in metadata['triangles']);shift=pages-1
source.images=[np.asarray(Image.open(out/f'native-atlas-{i}.png').convert('RGB')).copy() for i in range(pages)]+source.images[1:]
for i,t in enumerate(source.triangles):t['image']=metadata['triangles'][i]['image'] if i<count else t['image']+shift
masks=[np.zeros(a.shape[:2],bool) for a in source.images]
fields=[('reconciled-views.json','reconciled-north-125','north-125-painted.png'),('views.json','pylon-125','pylon-125-painted.png'),('reconciled-views.json','reconciled-north-305','north-305-painted.png'),('views.json','pylon-305','pylon-305-painted.png')]
for plan,name,filename in fields:
 c=next(v['camera'] for v in json.loads((out/plan).read_text())['views'] if v['name']==name)
 drawing=Image.open(out/filename).convert('RGBA').resize((c['size'],c['size']),Image.Resampling.NEAREST)
 views.apply_source_registered_field(source,source.images,c,np.asarray(drawing),{'br05A040','0599100000750049'},painted_masks=masks)
views.pad_painted_uv_charts(source,source.images,masks)
output=ROOT/'public/data/erasmus-structure-drawing';output.mkdir(parents=True,exist_ok=True)
# The generated UVs only store drawing. Every vertex stays on its original source triangle.
from pyproj import Transformer
rd_to_geo=Transformer.from_crs(28992,4326,always_xy=True);geo_to_earth=Transformer.from_crs(4979,4978,always_xy=True)
lo,la=np.radians([4.49,51.915]);origin=np.array(geo_to_earth.transform(4.49,51.915,0));basis=np.array([[-np.sin(lo),np.cos(lo),0],[np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)],[np.sin(la)*np.cos(lo),np.sin(la)*np.sin(lo),-np.cos(la)]])
doc={'asset':{'version':'2.0'},'scene':0,'scenes':[{'nodes':[0]}],'nodes':[{'mesh':0}],'meshes':[{'name':'Erasmusbrug retained structure','primitives':[]}],'buffers':[{'byteLength':0}],'bufferViews':[],'accessors':[],'images':[],'textures':[],'samplers':[{'magFilter':9728,'minFilter':9987,'wrapS':33071,'wrapT':33071}],'materials':[]};binary=bytearray()
def accessor(array,typ):
 array=np.asarray(array,dtype='<f4');binary.extend(b'\0'*((-len(binary))%4));vi=len(doc['bufferViews']);doc['bufferViews'].append({'buffer':0,'byteOffset':len(binary),'byteLength':array.nbytes});binary.extend(array.tobytes());ai=len(doc['accessors']);doc['accessors'].append({'bufferView':vi,'componentType':5126,'count':len(array),'type':typ,'min':array.min(0).tolist(),'max':array.max(0).tolist()});return ai
for page in range(pages):
 triangles=[t for t in source.triangles[:count] if t['image']==page];local=np.array([t['positions'] for t in triangles]);rd=local[...,[0,2,1]]*[1,-1,1]+centre;lon,lat=rd_to_geo.transform(rd[...,0],rd[...,1]);earth=np.stack(geo_to_earth.transform(lon,lat,rd[...,2]),axis=-1);positions=(earth-origin)@basis.T
 uv=np.array([t['uv'] for t in triangles]);image=source.images[page];height,width=image.shape[:2];loxy=np.maximum(0,np.floor(uv.reshape(-1,2).min(0)*[width,height]).astype(int)-3);hixy=np.minimum([width,height],np.ceil(uv.reshape(-1,2).max(0)*[width,height]).astype(int)+3);image=image[loxy[1]:hixy[1],loxy[0]:hixy[0]];uv=(uv*[width,height]-loxy)/(hixy-loxy);name=f'structure-{page}.png';Image.fromarray(image).save(output/name)
 normals=np.cross(positions[:,1]-positions[:,0],positions[:,2]-positions[:,0]);normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-12)
 pi=accessor(positions.reshape(-1,3),'VEC3');ui=accessor(uv.reshape(-1,2),'VEC2');ni=accessor(np.repeat(normals,3,axis=0),'VEC3');doc['images'].append({'uri':name});doc['textures'].append({'source':page,'sampler':0});doc['materials'].append({'name':'Source-bound pale steel and concrete drawing','pbrMetallicRoughness':{'baseColorTexture':{'index':page},'roughnessFactor':1,'metallicFactor':0},'doubleSided':True});doc['meshes'][0]['primitives'].append({'attributes':{'POSITION':pi,'TEXCOORD_0':ui,'NORMAL':ni},'material':page})
doc['buffers'][0]['byteLength']=len(binary);(output/'structure.glb').write_bytes(views.m.appearance.pack_glb(doc,binary))
# Retain source BAG transform/UVs and clipped geometry, change only observed texture pixels.
shore_out=out/'painted-reconciled-shore';shore_out.mkdir(exist_ok=True);meta=json.loads((out/'reconciled-shore/georeference-and-identities.json').read_text());shutil.copyfile(out/'reconciled-shore/source-bound-row.glb',shore_out/'source-bound-row.glb')
for i,record in enumerate(meta['external_images']):
 Image.fromarray(source.images[pages+i]).save(shore_out/record['uri']);record['sha256']=hashlib.sha256((shore_out/record['uri']).read_bytes()).hexdigest()
(shore_out/'georeference-and-identities.json').write_text(json.dumps(meta,indent=2)+'\n')
for plan,name,_ in fields:
 c=next(v['camera'] for v in json.loads((out/plan).read_text())['views'] if v['name']==name);rgb,_=views.render(source,c);Image.fromarray(rgb).save(out/(name+'-actual-bake.png'))
(output/'manifest.json').write_text(json.dumps({'authorship':'Written by AI on 2026-10-25 by model GPT-6 Astra','nativeSource':metadata['sourceURL'],'nativeSha256':metadata['sourceDecodedSha256'],'originalTriangles':count,'geometry':'Original source triangles; generated plane UVs only','fields':fields,'status':'Unaccepted source-bound visual candidate'},indent=2)+'\n')
print('Bound retained structure and reconciled shore drawing')
