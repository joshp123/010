import json,struct
import numpy as np
from PIL import Image,ImageDraw
from pathlib import Path
p=Path('source-data/vegetation-drawing/municipal-proto8.glb'); b=p.read_bytes(); n=struct.unpack_from('<I',b,12)[0];d=json.loads(b[20:20+n]);bin=b[28+n:]
def a(i):
 x=d['accessors'][i];v=d['bufferViews'][x['bufferView']];typ={5126:'<f4',5123:'<u2',5125:'<u4'}[x['componentType']];k={'VEC3':3,'SCALAR':1}[x['type']];return np.ndarray((x['count'],k),dtype=typ,buffer=bin,offset=v.get('byteOffset',0)+x.get('byteOffset',0),strides=(v.get('byteStride',np.dtype(typ).itemsize*k),np.dtype(typ).itemsize)).copy()
pr=d['meshes'][0]['primitives'][0];pos=a(pr['attributes']['POSITION']);ind=a(pr['indices']).ravel() if 'indices'in pr else np.arange(len(pos));tri=pos[ind].reshape(-1,3,3)
print(pos.min(0),pos.max(0),len(tri)); lo=pos.min(0);hi=pos.max(0);pos=(pos-lo)/(hi-lo)-.5;tri=pos[ind].reshape(-1,3,3)
# +Z,-Z,+X,-X,+Y,-Y; each orthographic source surface in the runtime atlas frame.
bases=[((1,0,0),(0,-1,0),(0,0,1)),((-1,0,0),(0,-1,0),(0,0,-1)),((0,0,-1),(0,-1,0),(1,0,0)),((0,0,1),(0,-1,0),(-1,0,0)),((1,0,0),(0,0,1),(0,1,0)),((1,0,0),(0,0,-1),(0,-1,0))]
canvas=Image.new('RGB',(1536,1024),'#d9ded2')
for k,base in enumerate(bases):
 m=np.array(base);q=tri@m.T;im=Image.new('RGB',(512,512),'#d9ded2');draw=ImageDraw.Draw(im)
 normals=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);normals/=np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-9)
 for j in np.argsort(q[:,:,2].mean(1)):
  if normals[j]@m[2]<0:continue
  lum=.55+.45*max(0,normals[j]@np.array([-.4,.8,.45]));c=tuple(int(x*lum) for x in (119,143,78));draw.polygon([tuple(x)for x in q[j,:,:2]*420+256],fill=c)
 canvas.paste(im,((k%3)*512,(k//3)*512))
canvas.save('work/foliage-drawing/source-six-views.png')
Path('work/foliage-drawing/source-geometry.json').write_text(json.dumps({'positions':pos.tolist(),'indices':ind.tolist()}))
