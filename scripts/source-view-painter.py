#!/usr/bin/env python3
"""Compose model-drawn source views onto retained geometry and original UVs.
Written by AI on 2026-10-24 by model GPT-6.
"""
import argparse,importlib.util,json,math
from pathlib import Path
import numpy as np
from PIL import Image
spec=importlib.util.spec_from_file_location('bound',Path(__file__).with_name('source-bound-painter.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class SourceCollection:
 """Observe adjoining sources together; export their original geometry separately."""
 def __init__(self,folder):
  self.path=folder;self.sources=[m.Source(p) for p in sorted(folder.glob('*.b3dm'))];assert self.sources,'No retained municipal sources'
  anchor=self.sources[0];anchor_rotation=np.array(anchor.doc['nodes'][0]['matrix']).reshape(4,4,order='F')[:3,:3];anchor_centre=np.array(anchor.feature['RTC_CENTER'])
  self.images=[];self.triangles=[];self.source_image_ranges=[]
  for source in self.sources:
   image_start=len(self.images);self.images.extend(source.images);self.source_image_ranges.append((image_start,len(self.images)))
   rotation=np.array(source.doc['nodes'][0]['matrix']).reshape(4,4,order='F')[:3,:3];relative_rotation=anchor_rotation.T@rotation;relative_centre=anchor_rotation.T@(np.array(source.feature['RTC_CENTER'])-anchor_centre)
   for triangle in source.triangles:
    original_identity=str(source.batch['id'][triangle['batch']])
    if not original_identity.startswith('BAG_'):continue
    self.triangles.append({**triangle,'positions':triangle['positions']@relative_rotation.T+relative_centre,'image':triangle['image']+image_start})
  self.positions=np.array([t['positions'] for t in self.triangles]);self.normals=np.cross(self.positions[:,1]-self.positions[:,0],self.positions[:,2]-self.positions[:,0]);self.areas=np.linalg.norm(self.normals,axis=1)/2;self.normals/=np.maximum(self.areas[:,None]*2,1e-12)
  self.raw='\n'.join(m.digest(s.raw) for s in self.sources).encode();self.anchor_rotation=anchor_rotation;self.anchor_centre=anchor_centre

 def export_handoff(self,images,identities,folder):
  folder.mkdir(parents=True,exist_ok=True);tiles=[]
  for source,(first,last) in zip(self.sources,self.source_image_ranges):
   selected={str(i).removeprefix('BAG_') for i in source.batch['id'] if str(i).startswith('BAG_')} & identities
   if not selected:continue
   tile_folder=folder/source.path.stem;source.export_handoff(images[first:last],selected,tile_folder);tiles.append({'directory':source.path.stem,'sourceDecodedSha256':m.digest(source.raw),'bagIds':sorted(selected)})
  m.save_json(folder/'collection.json',{'authorship':'Written by AI on 2026-10-25 by model GPT-6','status':'Shared neighbourhood drawing candidate, requires actual source/opposing city review','observationFingerprint':m.digest(self.raw),'tiles':tiles})

def load_source(path):
 return SourceCollection(path) if path.is_dir() else m.Source(path)

def camera(source,angle,elevation,size=1600):
 points=source.positions.reshape(-1,3);centre=(points.min(0)+points.max(0))/2;yaw=np.radians(angle);elev=np.radians(elevation);toward=np.array([np.sin(yaw)*np.cos(elev),np.sin(elev),np.cos(yaw)*np.cos(elev)]);right=np.array([np.cos(yaw),0,-np.sin(yaw)]);up=np.cross(toward,right);basis=np.stack([right,up,toward],axis=1);projected=(points-centre)@basis;scale=(size-48)/max(np.ptp(projected[:,:2],axis=0));mid=(projected[:,:2].max(0)+projected[:,:2].min(0))/2
 return {'centre':centre.tolist(),'basis':basis.tolist(),'scale':float(scale),'mid':mid.tolist(),'size':size,'angle':angle,'elevation':elevation}

def project(points,c):
 q=(points-np.array(c['centre']))@np.array(c['basis']);return q,(q[...,:2]-c['mid'])*[c['scale'],-c['scale']]+c['size']/2

def render(source,c):
 size=c['size'];rgb=np.full((size,size,3),[232,234,229],np.uint8);depth=np.full((size,size),-np.inf)
 for t in source.triangles:
  q,xy=project(t['positions'],c)
  for x0,y0,x1,y1,w,inside in m.raster_triangle(xy,size,size):
   zz=w@q[:,2];valid=inside&(zz>depth[y0:y1+1,x0:x1+1]);im=source.images[t['image']];uv=w@t['uv'];px=np.floor(uv*[im.shape[1],im.shape[0]]).astype(int);px[:,:,0]=px[:,:,0].clip(0,im.shape[1]-1);px[:,:,1]=px[:,:,1].clip(0,im.shape[0]-1);rgb[y0:y1+1,x0:x1+1][valid]=im[px[:,:,1][valid],px[:,:,0][valid]];depth[y0:y1+1,x0:x1+1][valid]=zz[valid]
 return rgb,depth

def prepare(source,out):
 out.mkdir(parents=True,exist_ok=True);views=[];previous=json.loads((out/'views.json').read_text()) if (out/'views.json').exists() else {}
 if previous:assert previous['sourceSha256']==m.digest(source.raw)
 accepted_views={v['name']:v for v in previous.get('views',[])}
 for angle,elevation in [(0,0),(90,0),(180,0),(270,0),(0,90),(120,28),(300,28),(0,45),(180,45)]:
  name=f'view-{angle}-{elevation}';c=camera(source,angle,elevation);rgb,depth=render(source,c);Image.fromarray(rgb).save(out/(name+'-source.png'));np.save(out/(name+'-depth.npy'),depth);views.append({'name':name,'camera':c,'source':name+'-source.png','paint':name+'-paint.png','depth':name+'-depth.npy',**accepted_views.get(name,{})})
 m.save_json(out/'views.json',{'authorship':'Written by AI on 2026-10-24 by model GPT-6','status':'Model drawing fields require actual source architecture review before acceptance',**previous,'sourceSha256':m.digest(source.raw),'sourcePath':str(source.path.resolve()),'views':views})

def bake(source,out):
 plan=json.loads((out/'views.json').read_text());assert plan['sourceSha256']==m.digest(source.raw);images=[a.copy() for a in source.images];scores=[np.full(a.shape[:2],-np.inf) for a in images]
 for view in plan['views']:
  path=out/view['paint']
  if not path.exists():continue
  c=view['camera'];size=c['size'];drawing=Image.open(path).convert('RGB');pixel_size=plan.get('drawingPixelSize')
  if plan.get('drawingPixelsPerMetre'):pixel_size=round(size*plan['drawingPixelsPerMetre']/c['scale'])
  if pixel_size:drawing=drawing.resize((pixel_size,pixel_size),Image.Resampling.BOX)
  paint=np.asarray(drawing.resize((size,size),Image.Resampling.NEAREST));depth=np.load(out/view['depth']);toward=np.array(c['basis'])[:,2]
  for index,t in enumerate(source.triangles):
   facing=float(source.normals[index]@toward)
   if facing<.4:continue
   score=facing*view.get('drawingConfidence',1)
   tex=images[t['image']];h,w=tex.shape[:2]
   for x0,y0,x1,y1,weights,inside in m.raster_triangle(t['uv']*[w,h],w,h):
    q,xy=project(weights@t['positions'],c);px=np.floor(xy).astype(int);valid=inside&(px[:,:,0]>=0)&(px[:,:,0]<size)&(px[:,:,1]>=0)&(px[:,:,1]<size);px[:,:,0]=px[:,:,0].clip(0,size-1);px[:,:,1]=px[:,:,1].clip(0,size-1)
    view_normal=source.normals[index]@np.array(c['basis']);sample_delta=(px+.5-xy)/c['scale'];sample_plane_depth=q[:,:,2]-(view_normal[0]*sample_delta[:,:,0]-view_normal[1]*sample_delta[:,:,1])/view_normal[2]
    valid&=abs(sample_plane_depth-depth[px[:,:,1],px[:,:,0]])<.12;valid&=score>scores[t['image']][y0:y1+1,x0:x1+1];tex[y0:y1+1,x0:x1+1][valid]=paint[px[:,:,1][valid],px[:,:,0][valid]];scores[t['image']][y0:y1+1,x0:x1+1][valid]=score
 if not isinstance(source,SourceCollection):source.export(images,out/'model-drawn-block.glb')
 source.export_handoff(images,{t['identity'] for t in source.triangles},out/plan.get('handoffDirectory','bound-model-drawn-block'));np.savez_compressed(out/'painted-atlases.npz',**{f'image_{i}':a for i,a in enumerate(images)})
 m.save_json(out/'baked.json',{'sourceSha256':m.digest(source.raw),'paintedViews':[v['paint'] for v in plan['views'] if (out/v['paint']).exists()],'identities':sorted({t['identity'] for t in source.triangles}),'status':'Whole model drawing field candidate; source aperture and opposing view inspection required, no fidelity acceptance inferred from geometry'})

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('operation',choices=['prepare','bake']);p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args();s=load_source(a.source)
 if a.operation=='prepare':prepare(s,a.output)
 else:bake(s,a.output)
