#!/usr/bin/env python3
"""CPU actual geometry comparison, not a WebGL visual acceptance screenshot."""
import json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
root=Path(__file__).resolve().parents[1]
items=json.loads((root/'work/canopy-review/geometry.json').read_text())
a=.7;basis=np.array([[np.cos(a),0,-np.sin(a)],[np.sin(a)*.55,-.835,np.cos(a)*.55],[np.sin(a)*.835,.55,np.cos(a)*.835]])
canvas=Image.new('RGB',(1000,660),'#edece3');draw=ImageDraw.Draw(canvas)
for k,item in enumerate(items):
 tri=np.array(item['positions']).reshape(-1,3,3);color=np.array(item['colors']).reshape(-1,3,3).mean(axis=1)
 proj=tri@basis.T;normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);normal/=np.maximum(np.linalg.norm(normal,axis=1)[:,None],1e-12)
 light=np.array([-.4,.8,.45]);light/=np.linalg.norm(light)
 colors=color*(.55+.45*np.maximum(0,normal@light))[:,None]
 colors=np.round(np.where(colors<=.0031308,colors*12.92,1.055*np.maximum(colors,0)**(1/2.4)-.055).clip(0,1)*255).astype('uint8')
 image=Image.new('RGB',(470,540),'#d2d5c7');d=ImageDraw.Draw(image)
 for i in np.argsort(proj[:,:,2].mean(axis=1)):
  if (normal@basis[2])[i]<0:continue
  xy=proj[i,:,:2]*430+np.array([235,465]);d.polygon([tuple(p) for p in xy],fill=tuple(colors[i]))
 canvas.paste(image,(k*500+15,50));draw.text((k*500+15,20),item['name']+' | exact proto_8 envelope',fill='#263c2d')
 # Phone-sized silhouette at approximate actual projected crown height.
 small=image.resize((117,135),Image.Resampling.LANCZOS);canvas.paste(small,(k*500+350,500))
draw.text((15,640),'CPU geometry/shading diagnostic. Actual municipal elm prototype; runtime lighting and night still need manager review.',fill='#263c2d')
canvas.save(root/'work/canopy-review/before-after.png')
