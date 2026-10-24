#!/usr/bin/env python3
"""Bake a candidate into original atlas coordinates; separate review GLB, never runtime."""
import argparse, copy, hashlib, io, json, struct
from pathlib import Path
import numpy as np
from PIL import Image
R=Path(__file__).resolve().parents[1]
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def raster(xy,width,height):
 a=np.vstack([xy.T,np.ones(3)])
 if abs(np.linalg.det(a))<1e-10:return None
 lo=np.maximum(np.floor(xy.min(0)).astype(int),0);hi=np.minimum(np.ceil(xy.max(0)).astype(int),[width-1,height-1])
 if np.any(hi<lo):return None
 yy,xx=np.mgrid[lo[1]:hi[1]+1,lo[0]:hi[0]+1];w=np.stack([xx,yy,np.ones_like(xx)],-1)@np.linalg.inv(a).T;ok=(w>=-1e-7).all(-1)
 return yy[ok],xx[ok],w[ok]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():p.error('output exists; choose a new directory')
 pilot=R/'source-data/mflux-pilot';src=R/'source-data/current-whole-row';meta=json.loads((pilot/'source.json').read_text());assert sha(src/'row-original.glb')==meta['sourceGeometrySha256'];assert sha(src/'source-triangles.npz')==meta['sourceTrianglesSha256'];assert sha(pilot/'surface-map.npz')==meta['surfaceMapSha256'];assert sha(pilot/'edit-mask.png')==meta['maskSha256']
 art=np.asarray(Image.open(a.candidate).convert('RGB'));mask=np.asarray(Image.open(pilot/'edit-mask.png'))>0
 if art.shape[:2]!=mask.shape:p.error('candidate must match exact source panel 512x1024; no automatic resize')
 z=np.load(src/'source-triangles.npz');P=z['positions'];U=z['uv'];I=z['image_index'];matrix=np.load(pilot/'surface-map.npz')['local_to_image'];selected=set(meta['triangleIds'])
 raw=(src/'row-original.glb').read_bytes();dl=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+dl]);original=raw[28+dl:];buf=bytearray(original);out=copy.deepcopy(doc);atlases=[]
 for im in doc['images']:
  v=doc['bufferViews'][im['bufferView']];atlases.append(np.asarray(Image.open(io.BytesIO(original[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']])).convert('RGB')))
 baked=[im.copy() for im in atlases];report=[]
 for ii in sorted({int(I[t]) for t in selected}):
  im=atlases[ii];h,w=im.shape[:2];allowed=np.zeros((h,w),bool);shared=np.zeros((h,w),bool)
  # Any texel also used by an unselected triangle is protected, including padding-edge overlap.
  for t in np.where(I==ii)[0]:
   if t in selected:continue
   hit=raster(U[t]*[w,h]-.5,w,h)
   if hit is not None:yy,xx,_=hit;shared[yy,xx]=True
  blocked=0
  for t in sorted(selected):
   if I[t]!=ii:continue
   hit=raster(U[t]*[w,h]-.5,w,h)
   if hit is None:continue
   yy,xx,bary=hit;xyz=bary@P[t];q=np.c_[xyz,np.ones(len(xyz))]@matrix.T;px=np.rint(q[:,:2]).astype(int);inside=(px[:,0]>=0)&(px[:,0]<art.shape[1])&(px[:,1]>=0)&(px[:,1]<art.shape[0]);cx=px[:,0].clip(0,art.shape[1]-1);cy=px[:,1].clip(0,art.shape[0]-1);ok=inside&mask[cy,cx];blocked+=int(np.sum(ok&shared[yy,xx]));ok&=~shared[yy,xx];baked[ii][yy[ok],xx[ok]]=art[cy[ok],cx[ok]];allowed[yy[ok],xx[ok]]=True
  assert np.array_equal(baked[ii][~allowed],im[~allowed]);changed=np.any(baked[ii]!=im,axis=-1);assert not np.any(changed&shared)
  stream=io.BytesIO();Image.fromarray(baked[ii]).save(stream,format='PNG');png=stream.getvalue();buf.extend(b'\0'*((-len(buf))%4));out['bufferViews'].append({'buffer':0,'byteOffset':len(buf),'byteLength':len(png)});out['images'][ii]={'bufferView':len(out['bufferViews'])-1,'mimeType':'image/png'};buf.extend(png)
  report.append({'imageIndex':ii,'editableTexels':int(allowed.sum()),'changedTexels':int(changed.sum()),'protectedSharedTexels':blocked})
 assert bytes(buf[:len(original)])==original
 for k in ['meshes','accessors','nodes','materials','textures','samplers']:assert out.get(k)==doc.get(k)
 a.output.mkdir(parents=True);out['buffers']=[{'byteLength':len(buf)}];jb=json.dumps(out,separators=(',',':')).encode();jb+=b' '*((-len(jb))%4);buf.extend(b'\0'*((-len(buf))%4));glb=struct.pack('<4sII',b'glTF',2,28+len(jb)+len(buf))+struct.pack('<I4s',len(jb),b'JSON')+jb+struct.pack('<I4s',len(buf),b'BIN\0')+buf;(a.output/'candidate-row.glb').write_bytes(glb)
 cameras=json.loads((src/'metadata.json').read_text())['cameras']
 for name in ['view-a','view-d']:
  camera=np.array(cameras[name]['localToImageDepthRowMajor']);width,height=cameras[name]['imageSize'];images=[]
  for textures in [atlases,baked]:
   rgb=np.full((height,width,3),235,np.uint8);depth=np.full((height,width),-np.inf)
   for t in range(len(P)):
    q=np.c_[P[t],np.ones(3)]@camera.T;hit=raster(q[:,:2],width,height)
    if hit is None:continue
    yy,xx,bary=hit;zz=bary@q[:,2];ok=zz>depth[yy,xx];yy=yy[ok];xx=xx[ok];bary=bary[ok];depth[yy,xx]=zz[ok]
    if I[t]<0:rgb[yy,xx]=z['untextured_rgb'][t];continue
    im=textures[I[t]];uv=bary@U[t];px=np.floor(uv*[im.shape[1],im.shape[0]]).astype(int);rgb[yy,xx]=im[px[:,1].clip(0,im.shape[0]-1),px[:,0].clip(0,im.shape[1]-1)]
   images.append(rgb)
  Image.fromarray(np.concatenate(images,axis=1)).save(a.output/(name+'-source-candidate.png'))
 record={'status':'unreviewed bake for visual inspection; no runtime publication','candidateSha256':sha(a.candidate),'sourceGeometrySha256':meta['sourceGeometrySha256'],'maskSha256':meta['maskSha256'],'mappingSha256':meta['surfaceMapSha256'],'outputSha256':sha(a.output/'candidate-row.glb'),'geometryBufferPrefixUnchanged':True,'sourceMeshUvNormalMaterialContractsUnchanged':True,'atlasChanges':report,'license':'Original source: Gemeente Rotterdam, CC BY 4.0','views':'Original left, candidate right; view-a and opposing view-d'};(a.output/'bake.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))
if __name__=='__main__':main()
