#!/usr/bin/env python3
"""Project model-observed source pane interiors into original glTF UVs.
Written by AI on 2026-10-25 by model GPT-6.
"""
import argparse,hashlib,importlib.util,json,shutil,struct
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw

def load(path):return json.loads(path.read_text())
def save(path,data):path.write_text(json.dumps(data,indent=2)+'\n')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

def prepare(source_path,views_path,observations_path,handoff,output,painter_scripts):
 painter=module('source_view_painter',painter_scripts/'source-view-painter.py');source=painter.m.Source(source_path)
 views=load(views_path);observations=load(observations_path)
 assert painter.m.digest(source.raw)==observations['sourceSha256']==views['sourceSha256']
 masks=[np.zeros(image.shape[:2],np.uint8) for image in source.images]
 projected=[];view_records={view['name']:view for view in views['views']}
 output.mkdir(parents=True,exist_ok=True)
 for observed in observations['views']:
  view=view_records[observed['name']];camera=view['camera'];size=camera['size'];source_image=views_path.parent/view['source']
  assert digest(source_image)==observed['sourceImageSha256']
  mask=Image.new('L',(size,size));drawing=ImageDraw.Draw(mask)
  for pane in observed['panes']:drawing.polygon(pane['polygon'],fill=255)
  mask=np.asarray(mask);depth=np.load(views_path.parent/view['depth']);toward=np.array(camera['basis'])[:,2]
  for index,triangle in enumerate(source.triangles):
   if abs(source.normals[index,1])>.6 or source.normals[index]@toward<.6:continue
   atlas=masks[triangle['image']];height,width=atlas.shape
   for x0,y0,x1,y1,weights,inside in painter.m.raster_triangle(triangle['uv']*[width,height],width,height):
    q,xy=painter.project(weights@triangle['positions'],camera);pixel=np.rint(xy).astype(int)
    valid=inside&(pixel[:,:,0]>=0)&(pixel[:,:,0]<size)&(pixel[:,:,1]>=0)&(pixel[:,:,1]<size)
    pixel[:,:,0]=pixel[:,:,0].clip(0,size-1);pixel[:,:,1]=pixel[:,:,1].clip(0,size-1)
    valid&=abs(q[:,:,2]-depth[pixel[:,:,1],pixel[:,:,0]])<.12
    valid&=mask[pixel[:,:,1],pixel[:,:,0]]>0
    atlas[y0:y1+1,x0:x1+1][valid]=255
    if np.any(valid):projected.append(triangle['identity'])
  save(output/(observed['name']+'-observation.json'),{**observed,'camera':camera,'depthSha256':digest(views_path.parent/view['depth'])})
 # The source geometry/accessors/UVs and the current daytime artwork are retained.
 for path in handoff.iterdir():
  if path.is_file():shutil.copyfile(path,output/path.name)
 geometry_name=load(handoff/'georeference-and-identities.json')['geometry_asset'];raw=(handoff/geometry_name).read_bytes();json_size=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+json_size]);binary=raw[28+json_size:]
 emission_textures={}
 for index,mask in enumerate(masks):
  if not np.any(mask):continue
  uri=f'observed-apertures-{index}.png';emission=np.zeros((*mask.shape,3),np.uint8);emission[mask>0]=[175,130,75]
  Image.fromarray(emission).save(output/uri)
  image_index=len(doc['images']);doc['images'].append({'uri':uri});texture_index=len(doc['textures']);doc['textures'].append({'source':image_index,'sampler':0});emission_textures[index]=texture_index
 for material in doc['materials']:
  base=material.get('pbrMetallicRoughness',{}).get('baseColorTexture')
  if not base:continue
  image=doc['textures'][base['index']]['source']
  if image in emission_textures:
   material['emissiveTexture']={'index':emission_textures[image]};material['emissiveFactor']=[1,1,1]
   material.setdefault('extras',{}).update(sourceObservedApertures=True,nightMeaning='Illustrated glazing response; neither occupancy nor live interior lighting')
 (output/geometry_name).write_bytes(painter.m.appearance.pack_glb(doc,binary))
 metadata=load(output/'georeference-and-identities.json');metadata['geometry_asset_sha256']=digest(output/geometry_name)
 metadata['external_images'] += [{'uri':f'observed-apertures-{index}.png','sha256':digest(output/f'observed-apertures-{index}.png'),'dimensions':[mask.shape[1],mask.shape[0]]} for index,mask in enumerate(masks) if index in emission_textures]
 save(output/'georeference-and-identities.json',metadata)
 save(output/'aperture-interpretation.json',{'authorship':'Written by AI on 2026-10-25 by model GPT-6','sourceSha256':views['sourceSha256'],'observationsSha256':digest(observations_path),'daytimeGeometrySha256':digest(handoff/geometry_name),'daytimeArtworkUnchanged':True,'supportedBuildings':sorted(set(projected)),'meaning':observations['meaning'],'status':'Night assembly candidate; actual day/dusk/night opposing city review required'})

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);parser.add_argument('--views',type=Path,required=True);parser.add_argument('--observations',type=Path,required=True);parser.add_argument('--handoff',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--painter-scripts',type=Path,default=Path(__file__).parent);args=parser.parse_args();prepare(args.source,args.views,args.observations,args.handoff,args.output,args.painter_scripts)
