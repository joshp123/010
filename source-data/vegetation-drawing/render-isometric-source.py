"""AI-written2026-10-25,GPT-6Astra: source-registered nine-view crown reference."""
import json,math,struct
import numpy as np
from PIL import Image,ImageDraw
from pathlib import Path
p=Path('source-data/vegetation-drawing/municipal-proto8.glb'); b=p.read_bytes(); n=struct.unpack_from('<I',b,12)[0];d=json.loads(b[20:20+n]);bin=b[28+n:]
def a(i):
 x=d['accessors'][i];v=d['bufferViews'][x['bufferView']];typ={5126:'<f4',5123:'<u2',5125:'<u4'}[x['componentType']];k={'VEC3':3,'SCALAR':1}[x['type']];return np.ndarray((x['count'],k),dtype=typ,buffer=bin,offset=v.get('byteOffset',0)+x.get('byteOffset',0),strides=(v.get('byteStride',np.dtype(typ).itemsize*k),np.dtype(typ).itemsize)).copy()
pr=d['meshes'][0]['primitives'][0];pos=a(pr['attributes']['POSITION']);ind=a(pr['indices']).ravel() if 'indices'in pr else np.arange(len(pos));tri=pos[ind].reshape(-1,3,3)
print(pos.min(0),pos.max(0),len(tri)); lo=pos.min(0);hi=pos.max(0);pos=(pos-lo)/(hi-lo)-.5;tri=pos[ind].reshape(-1,3,3)
canvas=Image.new('RGB',(1536,1536),'#d9ded2');views=[]
for k in range(9):
 az=math.radians(k*45);el=math.atan(1/math.sqrt(2)) if k<8 else math.pi/2
 right=np.array([math.cos(az),0,-math.sin(az)]);up=np.array([-math.sin(az)*math.sin(el),math.cos(el),-math.cos(az)*math.sin(el)]);direction=np.array([math.sin(az)*math.cos(el),math.sin(el),math.cos(az)*math.cos(el)]);basis=np.array([right,-up,direction]);q=tri@basis.T
 image=Image.new('RGB',(512,512),'#d9ded2');draw=ImageDraw.Draw(image)
 normals=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-9)
 for j in np.argsort(q[:,:,2].mean(1)):
  if normals[j]@direction<0:continue
  lum=.5+.5*max(0,normals[j]@np.array([-.4,.8,.45]));draw.polygon([tuple(x)for x in q[j,:,:2]*320+256],fill=tuple(int(x*lum)for x in(119,143,78)))
 canvas.paste(image,((k%3)*512,(k//3)*512));views.append({'right':right.tolist(),'up':up.tolist(),'direction':direction.tolist(),'scale':320,'centre':[256,256]})
canvas.save('source-data/vegetation-drawing/source-isometric-views.png');Path('source-data/vegetation-drawing/isometric-registration.json').write_text(json.dumps(views,indent=2)+'\n')
