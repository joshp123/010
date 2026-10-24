#!/usr/bin/env python3
"""CPU geometry diagnostic using actual retained BGT/crown sources, not WebGL acceptance.
Run with the primary runtime Python; outputs into work/public-space-review.
"""
import importlib.util,gzip,json,subprocess,hashlib
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from pyproj import Transformer
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'work/public-space-review';OUT.mkdir(parents=True,exist_ok=True)
s=importlib.util.spec_from_file_location('source',ROOT/'scripts/prepare-building-appearance.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
raw=gzip.decompress((ROOT/'source-data/transit-ground-evidence/33589-6931.b3dm.gz').read_bytes());d,b,batch,feature=next(m.b3dm_parts(raw))
lon,lat=4.5126138,51.9251404;origin=np.array(Transformer.from_crs(4979,4978,always_xy=True).transform(lon,lat,0));lo,la=np.radians([lon,lat]);basis=np.array([[-np.sin(lo),np.cos(lo),0],[np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)],[np.sin(la)*np.cos(lo),np.sin(la)*np.sin(lo),-np.cos(la)]])
yz=np.array([[1,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1]]);shift=np.eye(4);shift[:3,3]=feature['RTC_CENTER'];meshes=[]
def visit(i,parent):
 n=d['nodes'][i];mat=parent@np.array(n.get('matrix',np.eye(4).T.ravel())).reshape(4,4).T
 if 'mesh'in n:
  for p in d['meshes'][n['mesh']]['primitives']:
   v=m.accessor(d,b,p['attributes']['POSITION']);idx=m.accessor(d,b,p['indices'])[:,0].reshape(-1,3);ids=m.accessor(d,b,p['attributes']['_BATCHID'])[:,0];world=(np.c_[v,np.ones(len(v))]@(shift@yz@mat).T)[:,:3];local=(world-origin)@basis.T
   # Keep complete source triangles. Crop applies only at image presentation.
   meshes.append({'positions':local.astype('float32').ravel().tolist(),'indices':idx.ravel().tolist(),'batch':ids.ravel().tolist()})
 for child in n.get('children',[]):visit(child,mat)
for root in d['scenes'][d.get('scene',0)]['nodes']:visit(root,np.eye(4))
(OUT/'input.json').write_text(json.dumps({'meshes':meshes,'attributes':batch['attributes']}));subprocess.run(['node','scripts/inspect-public-space.mjs',str(OUT/'input.json'),str(OUT/'output.json')],cwd=ROOT,check=True)
out=json.loads((OUT/'output.json').read_text())
def srgb(c):return tuple(np.round(np.where(np.array(c)<=.0031308,np.array(c)*12.92,1.055*np.maximum(c,0)**(1/2.4)-.055).clip(0,1)*255).astype('uint8'))
def render_triangles(tri,col,size,centre,scale,view,lit=False):
 image=Image.new('RGB',size,'#d6dacb');draw=ImageDraw.Draw(image);projected=tri@view.T;depth=projected[:,:,2].mean(axis=1)
 for j in np.argsort(depth):
  t=projected[j];xy=(t[:,:2]-centre)*scale+np.array(size)/2
  if np.max(xy[:,0])<0 or np.min(xy[:,0])>size[0] or np.max(xy[:,1])<0 or np.min(xy[:,1])>size[1]:continue
  color=col[j]
  if lit:
   normal=np.cross(tri[j,1]-tri[j,0],tri[j,2]-tri[j,0]);normal/=max(np.linalg.norm(normal),1e-12);color=color*(.50+.50*max(0,np.dot(normal,np.array([-.4,.8,.45])/1.0)))
  draw.polygon([tuple(p) for p in xy],fill=srgb(color))
 return image
# Source ground only, no fake buildings or props. Top down avoids depth tricks.
view=np.array([[1,0,0],[0,0,1],[0,1,0]]);tri=[];colors=[];seams=[];seamcolors=[]
for item in out['ground']:
 v=np.array(item['positions']).reshape(-1,3);idx=np.array(item['indices']).reshape(-1,3);c=np.array(item['colors']).reshape(-1,3);ids=np.array(item['batch']);allowed=np.array([batch['attributes'][i].get('KLASSE_IMG') in {'Wegdeel','Begroeid terreindeel','Onbegroeid terreindeel','Ondersteunend wegdeel'} for i in ids[idx[:,0]]]);tri.extend(v[idx[allowed]]);colors.extend(c[idx[allowed]].mean(axis=1));seams.extend(np.array(item['boundaries']).reshape(-1,3,3));seamcolors.extend(np.array(item['boundaryColors']).reshape(-1,3,3).mean(axis=1))
tri=np.array(tri);ground_triangle_count=len(tri);colors=np.array(colors);seams=np.array(seams);seamcolors=np.array(seamcolors)
canvas=Image.new('RGB',(1800,960),'#efeee8');draw=ImageDraw.Draw(canvas)
for i,label in enumerate(['Before: flat source classes','Candidate: exact surveyed material boundaries']):
 t=tri if i==0 else np.concatenate([tri,seams+np.array([0,.012,0])]);c=colors if i==0 else np.concatenate([colors,seamcolors]);im=render_triangles(t,c,(890,880),[0,0],8,view);canvas.paste(im,(i*900,70));draw.text((i*900+16,20),label,fill='#27382e')
draw.text((16,940),'Retained BGT 33589/6931 near 51.92514,4.51261; CPU top-down geometry diagnostic. No water in this source tile. Texture/lighting requires WebGL review.',fill='#27382e');canvas.save(OUT/'ground-boundaries.png')
canvas=Image.new('RGB',(1600,1060),'#efeee8');draw=ImageDraw.Draw(canvas);angle=.65;view=np.array([[np.cos(angle),0,-np.sin(angle)],[np.sin(angle)*.55,-.835,np.cos(angle)*.55],[np.sin(angle)*.835,.55,np.cos(angle)*.835]])
for i,item in enumerate(out['trees']):
 tri=np.array(item['positions']).reshape(-1,3,3);color=np.array(item['colors']).reshape(-1,3,3).mean(axis=1);im=render_triangles(tri,color,(790,470),[0,-.33],400,view,True);x=(i%2)*800;y=(i//2)*520;canvas.paste(im,(x,y+40));draw.text((x+15,y+10),f"{item['name']} — {item['label']} ({len(tri):,} triangles)",fill='#27382e')
draw.text((16,1040),'Retained municipal prototype envelopes; fine foliage is bounded illustration, not measured branches. Source instance scale/position untouched.',fill='#27382e');canvas.save(OUT/'crown-before-after.png')
report={'sourceSha256':hashlib.sha256(raw).hexdigest(),'sourceTile':'33589/6931','nativeGroundTriangles':ground_triangle_count,'boundaryTriangles':len(seams),'sourceClasses':{str(k):sum(np.count_nonzero(np.array(i['classes'])==k) for i in out['ground']).item() for k in range(7)},'limits':'CPU geometry diagnostic; material shader, actual city silhouette, night and phone need manager WebGL review.'};(OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
