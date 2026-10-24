#!/usr/bin/env python3
"""Retained current municipal leaves → adjoining same-view source/model bindings."""
import argparse,gzip,hashlib,importlib.util,json,io
from pathlib import Path
import numpy as np
from PIL import Image
from pyproj import Transformer
R=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('m',R/'scripts/prepare-building-appearance.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
m.BASE='https://www.3drotterdam.nl/datasource-data/3adbe5af-d05c-475a-b34c-59e69ba8dadc/';m.SOURCE=R/'source-data/current-building-appearance'
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bounds',type=float,nargs=4,required=True,metavar=('WEST','SOUTH','EAST','NORTH'));p.add_argument('--output',type=Path,required=True);p.add_argument('--acquire',action='store_true');p.add_argument('--size',type=int,default=1024);p.add_argument('--panel-size',type=int,default=512);p.add_argument('--max-tiles',type=int,default=12);a=p.parse_args();assert a.bounds[0]<a.bounds[2] and a.bounds[1]<a.bounds[3];assert 128<=a.size<=4096;assert 128<=a.panel_size<=a.size
 m.AREAS={'requested':a.bounds};tiles=m.select_tiles(a.acquire);assert 0<len(tiles)<=a.max_tiles,f'{len(tiles)} leaves; narrow bounds or explicitly increase --max-tiles'
 a.output.mkdir(parents=True,exist_ok=True);(a.output/'original').mkdir(exist_ok=True);(a.output/'images').mkdir(exist_ok=True)
 lon,lat=(a.bounds[0]+a.bounds[2])/2,(a.bounds[1]+a.bounds[3])/2;origin=np.array(Transformer.from_crs(4979,4978,always_xy=True).transform(lon,lat,0));la,lo=np.radians([lat,lon]);frame=np.array([[-np.sin(lo),np.cos(lo),0],[np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)],[np.sin(la)*np.cos(lo),np.sin(la)*np.sin(lo),-np.cos(la)]])
 yz=np.array([[1,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1]]);positions=[];uvs=[];image_ids=[];bindings=[];fallback=[];atlases=[];colors=[]
 for tile_index,tile in enumerate(tiles):
  raw=m.fetch(tile['url'],a.acquire);pin=m.source_path(tile['url']).with_suffix('.json');assert not pin.exists() or json.loads(pin.read_text())['sha256']==m.digest(raw),'Retained source changed';name=tile['url'].removeprefix(m.BASE).replace('/','_');print(name,len(raw),flush=True)
  for part,(d,b,bt,ft) in enumerate(m.b3dm_parts(raw)):
   native=f'original/{name}-{part}.glb';(a.output/native).write_bytes(m.pack_glb(d,b));image_lookup=[];image_records=[]
   for ii,im in enumerate(d.get('images',[])):
    v=d['bufferViews'][im['bufferView']];data=b[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']];sha=m.digest(data);ext='.png' if im['mimeType']=='image/png' else '.jpg';uri='images/'+sha+ext;(a.output/uri).write_bytes(data);image_lookup.append(len(atlases));atlases.append(np.asarray(Image.open(io.BytesIO(data)).convert('RGB')));image_records.append({'sourceImage':ii,'globalImage':image_lookup[-1],'uri':uri,'sha256':sha})
   rtc=np.eye(4);rtc[:3,3]=ft['RTC_CENTER'];start=len(bindings)
   def walk(ni,parent):
    node=d['nodes'][ni];assert not any(k in node for k in ['rotation','translation','scale']),'TRS needs explicit composition';mat=parent@np.array(node.get('matrix',np.eye(4).T.ravel())).reshape(4,4).T
    if 'mesh' in node:
     for pi,pr in enumerate(d['meshes'][node['mesh']]['primitives']):
      assert pr.get('mode',4)==4;P=m.accessor(d,b,pr['attributes']['POSITION']);ix=m.accessor(d,b,pr['indices']).ravel().reshape(-1,3);ids=m.accessor(d,b,pr['attributes']['_BATCHID']).ravel();assert np.all(ids[ix]==ids[ix[:,0],None]);world=(np.c_[P,np.ones(len(P))]@(rtc@yz@mat).T)[:,:3];local=(world-origin)@frame.T;U=m.accessor(d,b,pr['attributes']['TEXCOORD_0']) if 'TEXCOORD_0' in pr['attributes'] else np.full((len(P),2),np.nan);mi=pr['material'];material=d['materials'][mi]['pbrMetallicRoughness'];tex=material.get('baseColorTexture');ii=image_lookup[d['textures'][tex['index']]['source']] if tex else -1
      factor=np.array(material.get('baseColorFactor',[1,1,1,1])[:3]);rgb=np.rint(np.where(factor<=.0031308,factor*12.92,1.055*factor**(1/2.4)-.055)*255).astype(np.uint8)
      for ti,indices in enumerate(ix):
       bid=int(ids[indices[0]]);identity=bt['id'][bid];positions.append(local[indices]);uvs.append(U[indices]);image_ids.append(ii);colors.append(rgb);bindings.append({'tile':tile_index,'part':part,'node':ni,'mesh':node['mesh'],'primitive':pi,'sourceTriangle':ti,'sourceIndices':indices.tolist(),'sourceMaterial':mi,'sourceBatchId':bid,'featureId':identity})
    for child in node.get('children',[]):walk(child,mat)
   for ni in d['scenes'][d.get('scene',0)]['nodes']:walk(ni,np.eye(4))
   fallback.append({'tile':tile_index,'part':part,'url':tile['url'],'sourceSha256':m.digest(raw),'rawPath':str(m.source_path(tile['url']).relative_to(R)),'decodedBytes':len(raw),'nativeGLB':native,'nativeGLBSha256':m.digest((a.output/native).read_bytes()),'sourceBoundingVolume':tile['boundingVolume'],'featureTable':ft,'batchTable':bt,'images':image_records,'triangleRange':[start,len(bindings)]})
 P=np.array(positions);U=np.array(uvs);I=np.array(image_ids);C=np.array(colors);np.savez_compressed(a.output/'source-triangles.npz',positions=P,uv=U,image_index=I,untextured_rgb=C)
 points=P.reshape(-1,3);centre=(points.min(0)+points.max(0))/2;frames={}
 for name,vec in [('ne',[1,.8,-1]),('se',[1,.8,1]),('sw',[-1,.8,1]),('nw',[-1,.8,-1]),('roof',[0,1,0])]:
  z=np.array(vec,dtype=float);z/=np.linalg.norm(z);up=[0,0,-1] if name=='roof' else [0,1,0];x=np.cross(up,z);x/=np.linalg.norm(x);y=np.cross(z,x);frames[name]=(x,y,z)
 scale=min(min((a.size-32)/(2*np.max(np.abs((points-centre)@x))),(a.size-32)/(2*np.max(np.abs((points-centre)@y)))) for x,y,z in frames.values());cameras={};panels=[];(a.output/'panels').mkdir(exist_ok=True)
 for name,(x,y,z) in frames.items():
  matrix=np.eye(4);matrix[0,:3]=x*scale;matrix[1,:3]=-y*scale;matrix[2,:3]=z;matrix[:3,3]=[a.size/2-centre@x*scale,a.size/2+centre@y*scale,-centre@z];rgb=np.full((a.size,a.size,3),235,np.uint8);depth=np.full((a.size,a.size),-np.inf);tri=np.full((a.size,a.size),-1,np.int32);uvmap=np.full((a.size,a.size,2),np.nan,np.float32);texelmap=np.full((a.size,a.size,2),-1,np.int32)
  for ti,(pos,uv,ii) in enumerate(zip(P,U,I)):
   q=np.c_[pos,np.ones(3)]@matrix.T;xy=q[:,:2];lo=np.maximum(np.floor(xy.min(0)).astype(int),0);hi=np.minimum(np.ceil(xy.max(0)).astype(int),a.size-1);mat=np.vstack([xy.T,np.ones(3)])
   if np.any(hi<lo) or abs(np.linalg.det(mat))<1e-9:continue
   x0,y0=lo;x1,y1=hi;yy,xx=np.mgrid[y0:y1+1,x0:x1+1];weights=np.stack([xx,yy,np.ones_like(xx)],-1)@np.linalg.inv(mat).T;zz=weights@q[:,2];dep=depth[y0:y1+1,x0:x1+1];ok=(weights>=-1e-7).all(-1)&(zz>dep);mapped=weights@uv
   if ii>=0:
    im=atlases[ii];coords=np.floor(mapped*[im.shape[1],im.shape[0]]).astype(int);coords[:,:,0]=coords[:,:,0].clip(0,im.shape[1]-1);coords[:,:,1]=coords[:,:,1].clip(0,im.shape[0]-1);rgb[y0:y1+1,x0:x1+1][ok]=im[coords[:,:,1][ok],coords[:,:,0][ok]];texelmap[y0:y1+1,x0:x1+1][ok]=coords[ok]
   else:rgb[y0:y1+1,x0:x1+1][ok]=C[ti];texelmap[y0:y1+1,x0:x1+1][ok]=-1
   dep[ok]=zz[ok];tri[y0:y1+1,x0:x1+1][ok]=ti;uvmap[y0:y1+1,x0:x1+1][ok]=mapped[ok]
  Image.fromarray(rgb).save(a.output/f'{name}.png');depth[tri<0]=np.nan;np.savez_compressed(a.output/f'{name}-projection.npz',triangle_index=tri,uv=uvmap,source_texel=texelmap,depth=depth.astype(np.float32));cameras[name]={'imageSize':[a.size,a.size],'localToImageDepth':matrix.tolist(),'imageDepthToLocal':np.linalg.inv(matrix).tolist(),'pixelsPerMeter':scale,'sampleConvention':'integer pixel centres; source top-left UV; depth increases toward camera; uncovered=-1/NaN'}
  # Overlapping spatial panels reuse the full shared-view projection, never
  # refit individual buildings. Neighbor context is preserved across borders.
  stride=a.panel_size*3//4;starts=sorted(set(list(range(0,a.size-a.panel_size+1,stride))+[a.size-a.panel_size]))
  for py in starts:
   for px in starts:
    if not np.any(tri[py:py+a.panel_size,px:px+a.panel_size]>=0):continue
    uri=f'panels/{name}-{px}-{py}.png';Image.fromarray(rgb[py:py+a.panel_size,px:px+a.panel_size]).save(a.output/uri);panel_matrix=matrix.copy();panel_matrix[0,3]-=px;panel_matrix[1,3]-=py;panels.append({'uri':uri,'view':name,'viewCropXYWH':[px,py,a.panel_size,a.panel_size],'localToPanelDepth':panel_matrix.tolist(),'projectionMap':f'{name}-projection.npz','scope':'Model input with overlapping neighbor context; source visibility is not an approved edit mask'})
 metadata={'boundsRequested':a.bounds,'license':'CC BY 4.0; Gemeente Rotterdam','licenseEvidence':'source-data/current-building-evidence/catalog-evidence.json','photographyDate':'Unknown; model creation dates are not photo dates','status':'Original adjoining source evidence, not illustrated or accepted art','commonFrame':{'originECEF':origin.tolist(),'ecefToEastUpSouth':frame.tolist()},'sources':fallback,'triangleBindings':bindings,'cameras':cameras,'modelPanels':panels,'limitations':['Building-only source views omit streets/trees; coordinate with public-space source package','Photographic texture occlusion/projection errors preserved, not repaired','All overlapping native leaves retained; not a whole-municipality coverage claim','No model output is auto-approved or baked; correspondence alone does not establish architectural correctness']}
 (a.output/'binding.json').write_text(json.dumps(metadata,separators=(',',':'))+'\n');print(json.dumps({'tiles':len(tiles),'features':len(set(x['featureId'] for x in bindings)),'triangles':len(P),'rawBytes':sum(x['decodedBytes'] for x in fallback),'output':str(a.output)}))
if __name__=='__main__':main()
