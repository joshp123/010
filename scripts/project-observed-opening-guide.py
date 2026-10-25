#!/usr/bin/env python3
"""Project source-observed opening shapes into a real scene camera.
Written by AI on 2026-10-25 by model GPT-6.
"""
import argparse, importlib.util, json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw

def project_guide(arguments):
 spec=importlib.util.spec_from_file_location('painter',arguments.painter_scripts/'source-view-painter.py');painter=importlib.util.module_from_spec(spec);spec.loader.exec_module(painter)
 source=painter.load_source(arguments.source);plan=json.loads(arguments.views.read_text());target=next(v for v in plan['views'] if v['name']==arguments.view);camera=target['camera'];size=camera['size'];scene_depth=np.load(arguments.views.parent/target['depth']);translation=np.array(json.loads(arguments.translation.read_text())['legacyToAlignedTranslation']);evidence=[]
 for path in arguments.observations:
  observation=json.loads(path.read_text());legacy_plan=json.loads(Path(observation['views']).read_text());old=next(v for v in legacy_plan['views'] if v['name']==observation['view']);old_camera={**old['camera'],'centre':(np.array(old['camera']['centre'])+translation).tolist()};depth=np.load(Path(observation['views']).parent/old['depth']);old_size=old_camera['size'];labels=Image.new('I',(old_size,old_size));draw=ImageDraw.Draw(labels);identities=[''];
  for facade in observation['facades']:
   identities.append(facade['sourceBagId'])
   for opening in facade.get('drawnOpenings',[]):draw.polygon([tuple(p) for p in opening['framePolygon']],fill=len(identities)-1)
  evidence.append((old_camera,old_size,depth,np.asarray(labels),np.array(identities)))
 visible_mask=np.zeros((size,size),bool)
 for face,triangle in enumerate(source.triangles):
  if source.normals[face]@np.array(camera['basis'])[:,2]<=.02:continue
  q,xy=painter.project(triangle['positions'],camera)
  for x0,y0,x1,y1,weights,inside in painter.m.raster_triangle(xy,size,size):
   points=weights@triangle['positions'];zz=weights@q[:,2];visible=inside&(abs(zz-scene_depth[y0:y1+1,x0:x1+1])<.12)
   if not visible.any():continue
   supported=np.zeros_like(visible)
   for old_camera,old_size,old_depth,labels,identities in evidence:
    normal=source.normals[face]@np.array(old_camera['basis'])
    if normal[2]<.6:continue
    projected,old_pixels=painter.project(points,old_camera);pixel=np.floor(old_pixels).astype(int);valid=visible&(pixel[:,:,0]>=0)&(pixel[:,:,0]<old_size)&(pixel[:,:,1]>=0)&(pixel[:,:,1]<old_size);pixel=pixel.clip(0,old_size-1);delta=(pixel+.5-old_pixels)/old_camera['scale'];plane_depth=projected[:,:,2]-(normal[0]*delta[:,:,0]-normal[1]*delta[:,:,1])/normal[2];label=labels[pixel[:,:,1],pixel[:,:,0]];valid&=(label>0)&(identities[label]==triangle['identity'])&(abs(plane_depth-old_depth[pixel[:,:,1],pixel[:,:,0]])<.12);supported|=valid
   visible_mask[y0:y1+1,x0:x1+1]|=supported
 output=np.zeros((size,size,4),np.uint8);output[visible_mask]=[0,90,255,150];arguments.output.mkdir(parents=True,exist_ok=True);guide=Image.fromarray(output);guide.save(arguments.output/'observed-opening-guide.png');im=Image.open(arguments.views.parent/target['source']).convert('RGBA');Image.alpha_composite(im,guide).save(arguments.output/'source-with-observed-openings.png')
 (arguments.output/'registration.json').write_text(json.dumps({'authorship':'Written by AI on 2026-10-25 by model GPT-6','views':str(arguments.views),'view':arguments.view,'observationPaths':[str(p) for p in arguments.observations],'meaning':'Blue marks source-observed frame/glass extents projected through original same-identity geometry and clipped to actual corrected scene depth. Hidden source apertures are retained in observations, not exposed in guide. No inferred openings.'},indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--views',type=Path,required=True);p.add_argument('--view',required=True);p.add_argument('--observations',type=Path,nargs='+',required=True);p.add_argument('--translation',type=Path,required=True);p.add_argument('--painter-scripts',type=Path,required=True);p.add_argument('--output',type=Path,required=True);project_guide(p.parse_args())
