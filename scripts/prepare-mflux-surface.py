#!/usr/bin/env python3
"""Rectify one observed street facade; retain exact pixel→triangle→atlas mapping."""
import hashlib, importlib.util, json, struct
from pathlib import Path
import numpy as np
from PIL import Image
R=Path(__file__).resolve().parents[1]; O=R/'source-data/mflux-pilot'; O.mkdir(exist_ok=True)
S=R/'source-data/current-whole-row'; z=np.load(S/'source-triangles.npz'); P=z['positions']; U=z['uv']; I=z['image_index']; B=z['source_batch_id']
n=np.cross(P[:,1]-P[:,0],P[:,2]-P[:,0]); n/=np.maximum(np.linalg.norm(n,axis=1)[:,None],1e-12)
ids=np.array([624,625]); target=n[624].astype(float); target/=np.linalg.norm(target)
assert len(ids)>0
raw=(S/'row-original.glb').read_bytes(); dl=struct.unpack_from('<I',raw,12)[0]; d=json.loads(raw[20:20+dl]); b=raw[28+dl:]
spec=importlib.util.spec_from_file_location('e',R/'scripts/inspect-current-building-evidence.py'); e=importlib.util.module_from_spec(spec); spec.loader.exec_module(e); atlas=e.images(d,b)
v=P[ids].reshape(-1,3); centre=(v.min(0)+v.max(0))/2; x=np.cross([0,1,0],target); y=np.array([0,1,0]); width,height=512,1024; scale=min((width-32)/np.ptp(v@x),(height-32)/np.ptp(v@y)); matrix=np.eye(4);matrix[0,:3]=x*scale;matrix[1,:3]=-y*scale;matrix[2,:3]=target;matrix[:3,3]=[width/2-centre@x*scale,height/2+centre@y*scale,-centre@target]
rgb=np.full((height,width,3),235,np.uint8); ti=np.full((height,width),-1,np.int32); uvmap=np.full((height,width,2),np.nan,np.float32); imap=np.full((height,width),-1,np.int16)
for t in ids:
 q=np.c_[P[t],np.ones(3)]@matrix.T; xy=q[:,:2]; a=np.vstack([xy.T,np.ones(3)])
 if abs(np.linalg.det(a))<1e-8:continue
 lo=np.maximum(np.floor(xy.min(0)).astype(int),0);hi=np.minimum(np.ceil(xy.max(0)).astype(int),[width-1,height-1]);x0,y0=lo;x1,y1=hi; yy,xx=np.mgrid[y0:y1+1,x0:x1+1];w=np.stack([xx,yy,np.ones_like(xx)],-1)@np.linalg.inv(a).T;ok=(w>=-1e-7).all(-1);uv=w@U[t];im=atlas[I[t]];px=np.floor(uv*[im.shape[1],im.shape[0]]).astype(int);px[:,:,0]=px[:,:,0].clip(0,im.shape[1]-1);px[:,:,1]=px[:,:,1].clip(0,im.shape[0]-1)
 rgb[y0:y1+1,x0:x1+1][ok]=im[px[:,:,1][ok],px[:,:,0][ok]];ti[y0:y1+1,x0:x1+1][ok]=t;uvmap[y0:y1+1,x0:x1+1][ok]=uv[ok];imap[y0:y1+1,x0:x1+1][ok]=I[t]
Image.fromarray(rgb).save(O/'source-panel.png');np.savez_compressed(O/'surface-map.npz',triangle_index=ti,uv=uvmap,image_index=imap,local_to_image=matrix)
# Scope deliberately limited to two upper storeys: no generated shop lettering or occluded interior.
mask=(ti>=0)&(np.indices(ti.shape)[0]<int(height*.61));Image.fromarray((mask*255).astype('uint8')).save(O/'edit-mask.png')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
meta={'status':'Source pilot only; no style image or generated result approved','bag':'0599100000671699','sourceBatchId':16,'sourceMetadata':'source-data/current-whole-row/metadata.json','license':'CC BY 4.0; Gemeente Rotterdam — 3D Rotterdam','triangleIds':ids.tolist(),'sourceGeometrySha256':sha(S/'row-original.glb'),'sourceTrianglesSha256':sha(S/'source-triangles.npz'),'sourcePanelSha256':sha(O/'source-panel.png'),'surfaceMapSha256':sha(O/'surface-map.npz'),'maskSha256':sha(O/'edit-mask.png'),'pixelsPerMeter':scale,'pixelConvention':'integer pixel centres, top-left UV; exact affine rectification of original planar triangles','interpretation':'Observed street facade, two windows per upper storey, pale frames and horizontal bands, red-brown masonry. Excludes known invalid party-wall planes 0/1/3/4/11. Storefront lettering and lower facade excluded from edit mask. No inferred windows or new geometry. Source camera blur/photometric shadows remain evidence limitations.','outputContract':'512x1024 exact image alignment. Review opening edges and material boundaries against source before bake. Only edit-mask pixels may transfer through surface-map UVs; preserve all other atlas pixels and all geometry. Mask is an illustrative scope, not semantic certainty.'}
(O/'source.json').write_text(json.dumps(meta,indent=2)+'\n');print(meta['triangleIds'])
