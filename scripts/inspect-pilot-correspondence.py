#!/usr/bin/env python3
"""Compare actual older/current photographic observations in one measured plane."""
import gzip,hashlib,importlib.util,io,json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
R=Path(__file__).resolve().parents[1];O=R/'source-data/pilot-correspondence';O.mkdir(exist_ok=True)
s=importlib.util.spec_from_file_location('m',R/'scripts/prepare-building-appearance.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
pilot=json.loads((R/'source-data/mflux-pilot/source.json').read_text());meta=json.loads((R/'source-data/current-whole-row/metadata.json').read_text());z=np.load(R/'source-data/current-whole-row/source-triangles.npz');target=z['positions'][pilot['triangleIds']];normal=np.cross(target[0,1]-target[0,0],target[0,2]-target[0,0]);normal/=np.linalg.norm(normal);matrix=np.load(R/'source-data/mflux-pilot/surface-map.npz')['local_to_image'];current_inv=np.linalg.inv(meta['localToECEFRowMajor']);bag=pilot['bag'];rawpath=R/'source-data/building-appearance/raw/17_134310_27736.cmpt.gz'
assert rawpath.exists(), 'Retained legacy leaf is required; acquire through the building-appearance pipeline'
raw=gzip.decompress(rawpath.read_bytes());triangles=[];atlas=[];records=[];yz=np.array([[1,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1]])
for part,(d,b,bt,ft) in enumerate(m.b3dm_parts(raw)):
 lookup=[str(x.get('gebouwnummer',x.get('GEBOUWNUMMER',''))).removeprefix('ID_').removeprefix('BAG_') for x in bt['attributes']]
 if bag not in lookup:continue
 bid=lookup.index(bag);rtc=np.eye(4);rtc[:3,3]=ft.get('RTC_CENTER',d.get('extensions',{}).get('CESIUM_RTC',{}).get('center'));offset=len(atlas)
 for im in d['images']:
  v=d['bufferViews'][im['bufferView']];atlas.append(np.array(Image.open(io.BytesIO(b[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']])).convert('RGB')))
 def walk(ni,parent):
  node=d['nodes'][ni];mat=parent@np.array(node.get('matrix',np.eye(4).T.ravel())).reshape(4,4).T
  if 'mesh' in node:
   for pi,p in enumerate(d['meshes'][node['mesh']]['primitives']):
    ix=(m.accessor(d,b,p['indices']).ravel() if 'indices' in p else np.arange(d['accessors'][p['attributes']['POSITION']]['count'])).reshape(-1,3);ids=m.accessor(d,b,p['attributes']['_BATCHID']).ravel();P=m.accessor(d,b,p['attributes']['POSITION']);U=m.accessor(d,b,p['attributes']['TEXCOORD_0']) if 'TEXCOORD_0' in p['attributes'] else None
    texture=d['materials'][p['material']].get('extensions',{}).get('KHR_techniques_webgl',{}).get('values',{}).get('u_diffuse_tex')
    if U is None or texture is None:continue
    ii=offset+d['textures'][texture['index']]['source'];converted=(np.c_[P,np.ones(len(P))]@(current_inv@rtc@yz@mat).T)[:,:3]
    for ti,indices in enumerate(ix):
     if ids[indices[0]]!=bid:continue
     pts=converted[indices];distance=np.abs((pts-target[0,0])@normal)
     if distance.max()>.01:continue
     triangles.append((pts,U[indices],ii));records.append({'part':part,'node':ni,'mesh':node['mesh'],'primitive':pi,'triangle':ti,'material':p['material'],'image':ii-offset,'batchId':bid,'maxPlaneDistanceMeters':float(distance.max())})
  for child in node.get('children',[]):walk(child,mat)
 for ni in d['scenes'][d.get('scene',0)]['nodes']:walk(ni,np.eye(4))
rgb=np.full((1024,512,3),235,np.uint8);index=np.full((1024,512),-1,np.int32)
for ti,(P,U,ii) in enumerate(triangles):
 q=np.c_[P,np.ones(3)]@matrix.T;lo=np.maximum(np.floor(q[:,:2].min(0)).astype(int),0);hi=np.minimum(np.ceil(q[:,:2].max(0)).astype(int),[511,1023]);A=np.vstack([q[:,:2].T,np.ones(3)])
 if np.any(hi<lo) or abs(np.linalg.det(A))<1e-9:continue
 x0,y0=lo;x1,y1=hi;yy,xx=np.mgrid[y0:y1+1,x0:x1+1];w=np.stack([xx,yy,np.ones_like(xx)],-1)@np.linalg.inv(A).T;ok=(w>=-1e-7).all(-1);im=atlas[ii];px=np.floor((w@U)*[im.shape[1],im.shape[0]]).astype(int);px[:,:,0]=px[:,:,0].clip(0,im.shape[1]-1);px[:,:,1]=px[:,:,1].clip(0,im.shape[0]-1);rgb[y0:y1+1,x0:x1+1][ok]=im[px[:,:,1][ok],px[:,:,0][ok]];index[y0:y1+1,x0:x1+1][ok]=ti
Image.fromarray(rgb).save(O/'legacy-same-plane.png');current=Image.open(R/'source-data/mflux-pilot/source-panel.png');comparison=Image.new('RGB',(1024,1056),'white');comparison.paste(Image.fromarray(rgb),(0,32));comparison.paste(current,(512,32));draw=ImageDraw.Draw(comparison);draw.text((8,8),'Older municipal edition: same measured plane',fill='black');draw.text((520,8),'Current municipal edition: unchanged model input',fill='black');comparison.save(O/'same-plane-comparison.jpg')
report={'bagId':bag,'currentTriangleIds':pilot['triangleIds'],'currentSourceHash':meta['sourceSha256'],'legacySourceHash':hashlib.sha256(raw).hexdigest(),'legacySourceUrl':'https://www.3drotterdam.nl/datasource-data/a6aee273-9406-41c4-a504-de2a59f7d514/17/134310/27736.cmpt','legacyMatches':records,'currentPanelHash':hashlib.sha256((R/'source-data/mflux-pilot/source-panel.png').read_bytes()).hexdigest(),'localToPanel':matrix.tolist(),'status':'Comparison evidence only: no source correction, model inference or opening-corner ground truth','measuredPlaneWidthMeters':float(np.linalg.norm(target[0,1]-target[0,0])),'measuredPlaneHeightMeters':float(np.linalg.norm(target[0,2]-target[0,1])),'nativeCurrentAtlasDimensions':[1024,1024],'nativeCurrentUVBoundsPixels':[(z['uv'][pilot['triangleIds']].reshape(-1,2).min(0)*1024).tolist(),(z['uv'][pilot['triangleIds']].reshape(-1,2).max(0)*1024).tolist()],'independence':'Different published imagery editions; independent photographic camera/date not established. Multiple CPU views of one atlas are not independent observations.'};(O/'comparison.json').write_text(json.dumps(report,indent=2)+'\n');print('Matching legacy planar triangles',len(records))
