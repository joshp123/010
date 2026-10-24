#!/usr/bin/env python3
"""Split bound painted artwork by exact BAG, retaining source texels and emission."""
import argparse,copy,importlib.util,io,json,struct
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageChops
spec=importlib.util.spec_from_file_location('appearance',Path(__file__).with_name('prepare-building-appearance.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def write(path,data):path.write_text(json.dumps(data,indent=2)+'\n')
def prepare(source,output):
 output.mkdir(parents=True,exist_ok=True);m.OUTPUT=source
 raw=(source/'model.glb').read_bytes();size=struct.unpack_from('<I',raw,12)[0];src=json.loads(raw[20:20+size]);binary=bytearray(raw[28+size:])
 for image in src['images']:
  if 'uri' not in image:continue
  data=(source/image.pop('uri')).read_bytes();binary.extend(b'\0'*((-len(binary))%4));vi=len(src['bufferViews']);src['bufferViews'].append({'buffer':0,'byteOffset':len(binary),'byteLength':len(data)});binary.extend(data);image['bufferView']=vi
 src['buffers'][0]['byteLength']=len(binary);embedded=m.pack_glb(src,binary)
 images=[]
 for im in src['images']:
  v=src['bufferViews'][im['bufferView']];images.append(Image.open(io.BytesIO(binary[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']])).convert('RGB'))
 source_tile=json.loads((source/'tileset.json').read_text())['root']['children'][0];children=[];records=[]
 m.OUTPUT=output;m.EDITION='legacy'
 for bag,packed,bounds,info in m.spatial_buildings(embedded,'model.glb'):
  doc,body=m.read_glb(packed);body=bytearray(body);emission={};cropping=[]
  for material_index,material in enumerate(doc['materials']):
   texture=material.get('emissiveTexture')
   if not texture:continue
   original_index=texture['index'];uv_name='TEXCOORD_'+str(texture.get('texCoord',0));image=images[src['textures'][original_index]['source']]
   primitives=[p for mesh in doc['meshes'] for p in mesh['primitives'] if p['material']==material_index]
   coverage=Image.new('L',image.size);draw=ImageDraw.Draw(coverage)
   for primitive in primitives:
    uv=m.accessor(doc,body,primitive['attributes'][uv_name])*image.size
    triangles=m.accessor(doc,body,primitive['indices'])[:,0].reshape(-1,3)
    for triangle in triangles:draw.polygon([tuple(point) for point in uv[triangle]],fill=255)
   occupied=ImageChops.multiply(image.convert('L'),coverage).getbbox()
   if occupied:
    lo=np.maximum(0,np.array(occupied[:2])-2);hi=np.minimum(image.size,np.array(occupied[2:])+2)
   else:lo=hi=np.array([0,0])
   if np.any(hi<=lo):
    material.pop('emissiveTexture');material['emissiveFactor']=[0,0,0];continue
   crop=image.crop((*lo,*hi));key=(original_index,*lo,*hi)
   if key not in emission:
    png=io.BytesIO();crop.save(png,format='PNG',optimize=True);body.extend(b'\0'*((-len(body))%4));view_index=len(doc['bufferViews']);doc['bufferViews'].append({'buffer':0,'byteOffset':len(body),'byteLength':len(png.getvalue())});body.extend(png.getvalue())
    image_index=len(doc.setdefault('images',[]));doc['images'].append({'bufferView':view_index,'mimeType':'image/png'});texture_index=len(doc.setdefault('textures',[]));doc['textures'].append({'source':image_index,'sampler':0});emission[key]=texture_index
   texture['index']=emission[key]
   for p in primitives:
    ai=p['attributes'][uv_name];accessor=doc['accessors'][ai];values=m.accessor(doc,body,ai).copy();mapped=np.ascontiguousarray(((values*image.size-lo)/(hi-lo)).astype(values.dtype));view=doc['bufferViews'][accessor['bufferView']];start=view.get('byteOffset',0)+accessor.get('byteOffset',0);body[start:start+mapped.nbytes]=mapped.tobytes()
   cropping.append({'material':material_index,'sourceTexture':original_index,'sourceSize':list(image.size),'sourceCrop':[*map(int,lo),*map(int,hi)],'paddingPixels':2,'texCoord':uv_name})
  doc['extras']['sourceEmissionCrops']=cropping;doc['buffers'][0]['byteLength']=len(body);result=m.pack_glb(doc,body);name='bag'+bag+'.glb';(output/name).write_bytes(m.deployable(result))
  node={'boundingVolume':bounds,'geometricError':0,'content':{'uri':name},'extras':{'bagIds':[bag]}}
  for limit in (1024,512):
   level,level_info=m.texture_lod(result,limit)
   if level_info['maxTextureSize'] >= max(max(image.size) for image in images) and limit==1024:continue
   level_name='bag'+bag+'-tex'+str(limit)+'.glb';(output/level_name).write_bytes(m.deployable(level))
   node={'boundingVolume':bounds,'geometricError':level_info['samplingMetersPerTexel'],'content':{'uri':level_name},'refine':'REPLACE','extras':{'bagIds':[bag]},'children':[node]}
  children.append(node)
  records.append({'bagId':bag,'sourceSha256':m.digest(raw),'output':name,**info,'emissionCrops':cropping})
 tiles=copy.deepcopy(json.loads((source/'tileset.json').read_text()));tiles['root']['children']=[{'boundingVolume':source_tile['boundingVolume'],'transform':source_tile['transform'],'geometricError':0,'refine':'ADD','children':children}]
 write(output/'tileset.json',tiles);write(output/'residency.json',{'nativeTexels':True,'source':str(source),'sourceGLBSha256':m.digest(raw),'buildings':records})
 print(json.dumps({'output':str(output),'buildings':len(records),'baseColourDecodedMipBytes':sum(r['decodedRgbaBytesIncludingMips'] for r in records)}),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args();prepare(a.source,a.output)
