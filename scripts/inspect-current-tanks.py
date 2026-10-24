#!/usr/bin/env python3
"""One original municipal textured tank leaf; bounded acquisition, no style transform."""
import argparse,datetime,gzip,importlib.util,json,math,struct,urllib.request
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'source-data/current-tank-evidence';RAW=OUT/'raw';BASE='https://www.3drotterdam.nl/datasource-data/25da2fa9-d5b7-4d44-b100-7ab3b3bf51dc/'
spec=importlib.util.spec_from_file_location('centre',ROOT/'scripts/inspect-current-centre.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper);m=helper.m;c=helper.c

def fetch(uri,acquire):
 p=RAW/(uri.replace('/','_')+'.gz');side=p.with_suffix('.json')
 # Bootstrap root was acquired before this helper existed; preserve that original sidecar.
 if not side.exists() and (RAW/(uri.replace('/','_')+'.json')).exists():side=RAW/(uri.replace('/','_')+'.json')
 if p.exists():
  b=gzip.decompress(p.read_bytes());assert m.digest(b)==json.loads(side.read_text())['sha256'];return b
 if not acquire:raise RuntimeError('Missing retained '+str(p)+'; use --acquire')
 with urllib.request.urlopen(BASE+uri,timeout=90) as r:b=r.read();headers=dict(r.headers.items())
 b=gzip.decompress(b) if b[:2]==b'\x1f\x8b' else b;p.write_bytes(gzip.compress(b,mtime=0));side.write_text(json.dumps({'url':BASE+uri,'acquiredAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sha256':m.digest(b),'decodedBytes':len(b),'responseHeaders':headers},indent=2)+'\n');print(uri,len(b),flush=True);return b

def render(doc,binary,name,direction):
 atlas=c.images(doc,binary);triangles=[]
 for mesh in doc['meshes']:
  for p in mesh['primitives']:
   indices=m.accessor(doc,binary,p['indices'])[:,0].reshape(-1,3);P=m.accessor(doc,binary,p['attributes']['POSITION'])[indices];U=m.accessor(doc,binary,p['attributes']['TEXCOORD_0'])[indices];mat=doc['materials'][p['material']]['pbrMetallicRoughness'];ii=doc['textures'][mat['baseColorTexture']['index']]['source'];triangles.extend(zip(P,U,[ii]*len(P)))
 points=np.concatenate([p for p,u,i in triangles]);centre=(points.min(axis=0)+points.max(axis=0))/2;direction=np.array(direction,dtype=float);direction/=np.linalg.norm(direction);right=np.cross([0,1,0],direction);right/=np.linalg.norm(right);up=np.cross(direction,right)
 screen=np.stack([(points-centre)@right,(points-centre)@up],axis=-1);scale=min(620/np.ptp(screen[:,0]),520/np.ptp(screen[:,1]));mid=(screen.min(0)+screen.max(0))/2;rgb=np.full((600,700,3),235,dtype=np.uint8);depth=np.full((600,700),-np.inf)
 for pos,uv,ii in triangles:
  relative=pos-centre;q=np.stack([350+(relative@right-mid[0])*scale,300-(relative@up-mid[1])*scale],axis=-1);z=relative@direction
  x0,y0=np.maximum(np.floor(q.min(axis=0)).astype(int),0);x1,y1=np.minimum(np.ceil(q.max(axis=0)).astype(int),[699,599]);matrix=np.vstack([q.T,np.ones(3)])
  if x1<x0 or y1<y0 or abs(np.linalg.det(matrix))<1e-8:continue
  yy,xx=np.mgrid[y0:y1+1,x0:x1+1];bary=np.stack([xx,yy,np.ones_like(xx)],axis=-1)@np.linalg.inv(matrix).T;zz=bary@z;dep=depth[y0:y1+1,x0:x1+1];ok=(bary>=-1e-7).all(axis=-1)&(zz>dep);image=atlas[ii];coord=bary@uv;xy=np.floor(coord*[image.shape[1],image.shape[0]]).astype(int);xy[:,:,0]=xy[:,:,0].clip(0,image.shape[1]-1);xy[:,:,1]=xy[:,:,1].clip(0,image.shape[0]-1);rgb[y0:y1+1,x0:x1+1][ok]=image[xy[:,:,1][ok],xy[:,:,0][ok]];dep[ok]=zz[ok]
 Image.fromarray(rgb).save(OUT/name)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--acquire',action='store_true');args=ap.parse_args();RAW.mkdir(parents=True,exist_ok=True);c.OUT=OUT
 root=json.loads(fetch('tileset.json',args.acquire));index=json.loads(fetch('10/1048/216.json',args.acquire));leaves=[]
 def walk(node):
  uri=node.get('content',{}).get('uri','')
  if uri and not node.get('children') and not uri.endswith('.json'):leaves.append(node)
  for child in node.get('children',[]):walk(child)
 walk(index['root']);point=np.radians([4.35,51.89])
 def distance(node):
  r=node['boundingVolume']['region'];dx=((r[0]+r[2])/2-point[0])*math.cos(point[1]);dy=(r[1]+r[3])/2-point[1];return dx*dx+dy*dy
 leaf=min(leaves,key=distance);from urllib.parse import urljoin
 uri=urljoin(BASE+'10/1048/216.json',leaf['content']['uri']).removeprefix(BASE);raw=fetch(uri,args.acquire);parts=list(m.b3dm_parts(raw));assert len(parts)==1,'Retain all parts explicitly before multi-part handling'
 doc,binary,batch,feature=parts[0];work=ROOT/'work/current-tank-evidence';work.mkdir(parents=True,exist_ok=True)
 # GLB is copied literally from its B3DM payload, not repacked by a building converter.
 if raw[:4]!=b'b3dm':raise ValueError('Expected single B3DM source')
 header=struct.unpack_from('<4s6I',raw);offset=28+sum(header[3:7]);glb=raw[offset:offset+struct.unpack_from('<I',raw,offset+8)[0]];(work/'original.glb').write_bytes(glb)
 assert glb[:4]==b'glTF';assert struct.unpack_from('<I',glb,8)[0]==len(glb)
 renderdoc,renderbin=helper.render_inputs(doc,binary)
 for suffix,direction in [('a',[1,1,1]),('b',[-1,.7,-1])]:render(renderdoc,renderbin,'source-'+suffix+'.png',direction)
 primitives=[p for mesh in doc['meshes'] for p in mesh['primitives']];ids=batch.get('id',[]);attrs=batch.get('attributes',[])
 report={'source':BASE+uri,'sourceSha256':m.digest(raw),'originalGLBSha256':m.digest(glb),'sourceNode':leaf,'featureTable':feature,'batchTable':batch,'geometry':{'meshes':len(doc['meshes']),'primitives':len(primitives),'triangles':sum((m.accessor(doc,binary,p['indices']).size if 'indices' in p else doc['accessors'][p['attributes']['POSITION']]['count'])//3 for p in primitives),'attributeSemantics':sorted({s for p in primitives for s in p['attributes']})},'images':[list(i.shape[:2][::-1]) for i in c.images(doc,binary)],'materials':doc['materials'],'sourceNodeTransforms':doc['nodes'],'creationDates':sorted({str(x.get('creationDate')) for x in attrs}),'photographyDate':'Not established; model creationDate and HTTP dates are not capture dates.','buildingConverterCompatibility':{'hasBAGIdentifiers':any(str(i).startswith('BAG_') for i in ids),'identityPolicy':'Retain tank feature IDs; no BAG fabrication or cross-layer suppression by building ID.','transportContainer':'Original single B3DM with embedded glTF2 PBR. Direct source tiles can retain all geometry, UVs, materials and RTC placement.','existingRuntime':'scene.js loads older c70023a7 tank endpoint and colorModel replaces source material with generic tank material; featureColor returns #d9d9cb. Merely changing tile URL would still discard tank appearance.','buildingConverter':'Current standard-PBR decode/compaction is reusable, but convert labels every output mesh BAG_ and extras.bagId. OST_* IDs must remain tank IDs in a separate namespace; do not pass through BAG reconciliation.'}}
 (OUT/'inspection.json').write_text(json.dumps(report,indent=2)+'\n');sheet=Image.new('RGB',(1400,630),'#ebebeb');draw=ImageDraw.Draw(sheet)
 for col,suffix in enumerate(['a','b']):sheet.paste(Image.open(OUT/('source-'+suffix+'.png')),(col*700,30));draw.text((col*700+8,8),'Original current tank geometry + source texture — '+suffix,fill='black')
 sheet.save(OUT/'source-views.jpg',quality=94);print(json.dumps({k:report[k] for k in ['source','geometry','images','creationDates','buildingConverterCompatibility']},indent=2))
if __name__=='__main__':main()
