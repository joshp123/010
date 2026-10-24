#!/usr/bin/env python3
"""Compare illustrative response at one retained native fixture; not a scene render."""
import json,struct,re
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
raw=(ROOT/'public/data/lamps/-3_0.glb').read_bytes();size=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+size]);binary=raw[28+size:]
mesh=next(m for m in doc['meshes'] if m.get('extras',{}).get('objectKind')=='lampHeads');node=next(n for n in doc['nodes'] if n.get('mesh')==doc['meshes'].index(mesh))
def accessor(index):
 a=doc['accessors'][index];v=doc['bufferViews'][a['bufferView']];dt={5123:'<u2',5125:'<u4',5126:'<f4'}[a['componentType']];count={'VEC3':3,'SCALAR':1}[a['type']]
 return np.ndarray((a['count'],count),dtype=dt,buffer=binary,offset=v.get('byteOffset',0)+a.get('byteOffset',0),strides=(v.get('byteStride',np.dtype(dt).itemsize*count),np.dtype(dt).itemsize)).copy()
p=mesh['primitives'][0];vertices=accessor(p['attributes']['POSITION'])*node.get('scale',[1,1,1])+node.get('translation',[0,0,0]);indices=accessor(p['indices']).ravel();ids=mesh['extras']['sourceIds'];chosen=[ids.index(i) for i in ['ovl_20282','ovl_100912']];heads=vertices[indices[chosen]];bases=vertices[indices[chosen]-1]
def smooth(a,b,x):t=np.clip((x-a)/(b-a),0,1);return t*t*(3-2*t)
# Actual candidate exponent comes from its runtime shader source.
code=(ROOT/'public/fixture-surface-lighting.js').read_text();exponent=float(re.search(r'exp\(-([\d.]+) \* normalizedDistance',code)[1])
canvas=Image.new('RGB',(1000,560),'#efeee5');draw=ImageDraw.Draw(canvas)
for column,candidate in enumerate([False,True]):
 # Receiver plane 4m beside the exact fixture pair: x horizontal, y vertical.
 x,y=np.meshgrid(np.linspace(heads[0,0]-20,heads[0,0]+20,470),np.linspace(bases[0,1]+17,bases[0,1],430));xyz=np.stack([x,y,np.full_like(x,heads[0,2]+4)],axis=-1);values=np.zeros_like(x)
 for head in heads:
  vector=head-xyz;distance=np.linalg.norm(vector,axis=-1);n=distance/18;facing=np.maximum(0,-vector[:,:,2]/np.maximum(distance,.1));down=smooth(.25,.75,vector[:,:,1]/np.maximum(distance,.1)) if candidate else smooth(-1,2,vector[:,:,1]);fall=np.exp(-(exponent if candidate else 2)*n*n)*(1-smooth(.75,1,n));values+=fall*facing*down
 rgb=(np.array([15,21,26])[None,None,:]+np.minimum(values,1.2)[:,:,None]*np.array([240,170,90])[None,None,:]).clip(0,255).astype('uint8');canvas.paste(Image.fromarray(rgb),(column*500+15,60));draw.text((column*500+15,20),('Candidate downward response' if candidate else 'Before radial response'),fill='#243b31');draw.text((column*500+15,500),'Receiver 4m beside recorded native heads; 40m wide / 17m tall',fill='#243b31')
draw.text((15,535),'Exact heads ovl_20282 + ovl_100912 retained. Illustrated light distribution, no measured photometry or occlusion.',fill='#243b31');canvas.save(ROOT/'docs/images/night-fixture-response.png')
print(json.dumps({'source':'public/data/lamps/-3_0.glb','ids':[ids[i] for i in chosen],'heads':heads.tolist(),'bases':bases.tolist(),'planSeparationMetres':float(np.linalg.norm((heads[1]-heads[0])[[0,2]]))},indent=2))
