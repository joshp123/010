#!/usr/bin/env python3
"""Extract unchanged pilot triangles, UV and source pixels from current municipal edition."""
import argparse,copy,gzip,hashlib,importlib.util,io,json,struct,urllib.request
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'source-data/current-building-evidence';BAG='0599100000670808'
spec=importlib.util.spec_from_file_location('appearance',ROOT/'scripts/prepare-building-appearance.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
BASE='https://www.3drotterdam.nl/datasource-data/3adbe5af-d05c-475a-b34c-59e69ba8dadc/'
FILES={'tileset.json':'tileset.json','12_4197_866.json':'12/4197/866.json','18_268621_55475.b3dm':'18/268621/55475.b3dm'}
def pack(doc,binary):
 doc['buffers']=[{'byteLength':len(binary)}];jb=m.pad(m.packed_json(doc),fill=b' ');bb=m.pad(bytes(binary))
 return struct.pack('<4sII',b'glTF',2,28+len(jb)+len(bb))+struct.pack('<I4s',len(jb),b'JSON')+jb+struct.pack('<I4s',len(bb),b'BIN\0')+bb

def extract(doc,binary,batch):
 bid=batch['id'].index('BAG_'+BAG);out=copy.deepcopy(doc);out['meshes']=[];out['accessors']=[];out['bufferViews']=[];out['images']=[];out['textures']=[];out['materials']=[];data=bytearray();meshmap={};materialmap={};imagemap={};texturemap={}
 def view(raw,target=None):
  data.extend(b'\0'*((-len(data))%4));v={'buffer':0,'byteOffset':len(data),'byteLength':len(raw)}
  if target:v['target']=target
  out['bufferViews'].append(v);data.extend(raw);return len(out['bufferViews'])-1
 def attr(values,template,target):
  a={k:v for k,v in template.items() if k not in('bufferView','byteOffset','count','min','max')};a.update(bufferView=view(values.tobytes(),target),count=len(values))
  if 'min'in template:a['min']=values.min(axis=0).tolist()
  if 'max'in template:a['max']=values.max(axis=0).tolist()
  out['accessors'].append(a);return len(out['accessors'])-1
 def material(mi):
  if mi in materialmap:return materialmap[mi]
  mat=copy.deepcopy(doc['materials'][mi]);tex=mat.get('pbrMetallicRoughness',{}).get('baseColorTexture')
  if tex:
   ti=tex['index']
   if ti not in texturemap:
    t=copy.deepcopy(doc['textures'][ti]);ii=t['source']
    if ii not in imagemap:
     im=copy.deepcopy(doc['images'][ii]);v=doc['bufferViews'][im['bufferView']];im['bufferView']=view(binary[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']]);imagemap[ii]=len(out['images']);out['images'].append(im)
    t['source']=imagemap[ii];texturemap[ti]=len(out['textures']);out['textures'].append(t)
   tex['index']=texturemap[ti]
  materialmap[mi]=len(out['materials']);out['materials'].append(mat);return materialmap[mi]
 for mi,mesh in enumerate(doc['meshes']):
  primitives=[]
  for p in mesh['primitives']:
   bids=m.accessor(doc,binary,p['attributes']['_BATCHID'])[:,0];indices=(m.accessor(doc,binary,p['indices'])[:,0] if 'indices'in p else np.arange(len(bids))).reshape(-1,3)
   assert np.all(bids[indices]==bids[indices[:,0],None]);chosen=indices[bids[indices[:,0]]==bid].reshape(-1)
   if not len(chosen):continue
   used,inv=np.unique(chosen,return_inverse=True);q=copy.deepcopy(p);q['attributes']={}
   for key,ai in p['attributes'].items():
    if key=='_BATCHID':continue
    values=np.ascontiguousarray(m.accessor(doc,binary,ai)[used]);q['attributes'][key]=attr(values,doc['accessors'][ai],34962)
   q['indices']=attr(inv.astype('<u2').reshape(-1,1),{'componentType':5123,'type':'SCALAR'},34963);q['material']=material(p['material']);primitives.append(q)
  if primitives:meshmap[mi]=len(out['meshes']);out['meshes'].append({'name':'BAG_'+BAG,'primitives':primitives,'extras':{'bagId':BAG,'sourceMesh':mi}})
 for node in out['nodes']:
  if 'mesh'in node:
   old=node.pop('mesh')
   if old in meshmap:node['mesh']=meshmap[old];node['extras']={'bagId':BAG}
 out['extras']={'bagId':BAG,'attribution':'Gemeente Rotterdam — 3D Rotterdam','license':'CC BY 4.0','source':'18/268621/55475.b3dm','changes':'Only selected original BAG triangles; compacted attributes and unused images/materials removed. Source pixels/UV/positions/normals unchanged.'}
 return out,bytes(data),batch['attributes'][bid]

def images(doc,binary):
 result=[]
 for im in doc['images']:
  v=doc['bufferViews'][im['bufferView']];result.append(np.asarray(Image.open(io.BytesIO(binary[v['byteOffset']:v['byteOffset']+v['byteLength']])).convert('RGB')))
 return result

def render(doc,binary,name,direction):
 atlas=images(doc,binary);triangles=[]
 for mesh in doc['meshes']:
  for p in mesh['primitives']:
   indices=m.accessor(doc,binary,p['indices'])[:,0].reshape(-1,3);P=m.accessor(doc,binary,p['attributes']['POSITION'])[indices];U=m.accessor(doc,binary,p['attributes']['TEXCOORD_0'])[indices];mat=doc['materials'][p['material']]['pbrMetallicRoughness'];ii=doc['textures'][mat['baseColorTexture']['index']]['source'];triangles.extend(zip(P,U,[ii]*len(P)))
 points=np.concatenate([p for p,u,i in triangles]);centre=(points.min(axis=0)+points.max(axis=0))/2;direction=np.array(direction,dtype=float);direction/=np.linalg.norm(direction);right=np.cross([0,1,0],direction);right/=np.linalg.norm(right);up=np.cross(direction,right)
 screen=np.stack([(points-centre)@right,(points-centre)@up],axis=-1);scale=min(620/np.ptp(screen[:,0]),520/np.ptp(screen[:,1]));rgb=np.full((600,700,3),235,dtype=np.uint8);depth=np.full((600,700),-np.inf)
 for pos,uv,ii in triangles:
  relative=pos-centre;q=np.stack([350+relative@right*scale,300-relative@up*scale],axis=-1);z=relative@direction
  x0,y0=np.maximum(np.floor(q.min(axis=0)).astype(int),0);x1,y1=np.minimum(np.ceil(q.max(axis=0)).astype(int),[699,599]);matrix=np.vstack([q.T,np.ones(3)])
  if x1<x0 or y1<y0 or abs(np.linalg.det(matrix))<1e-8:continue
  yy,xx=np.mgrid[y0:y1+1,x0:x1+1];bary=np.stack([xx,yy,np.ones_like(xx)],axis=-1)@np.linalg.inv(matrix).T;zz=bary@z;dep=depth[y0:y1+1,x0:x1+1];ok=(bary>=-1e-7).all(axis=-1)&(zz>dep);image=atlas[ii];coord=bary@uv;xy=np.floor(coord*[image.shape[1],image.shape[0]]).astype(int);xy[:,:,0]=xy[:,:,0].clip(0,image.shape[1]-1);xy[:,:,1]=xy[:,:,1].clip(0,image.shape[0]-1);rgb[y0:y1+1,x0:x1+1][ok]=image[xy[:,:,1][ok],xy[:,:,0][ok]];dep[ok]=zz[ok]
 Image.fromarray(rgb).save(OUT/name)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--acquire',action='store_true');args=ap.parse_args();expected={e['url']:e['sha256'] for e in json.loads((OUT/'pilot-metadata.json').read_text()).get('sourceEvidence',[])} if (OUT/'pilot-metadata.json').exists() else {};OUT.mkdir(exist_ok=True);(OUT/'raw').mkdir(exist_ok=True);evidence=[]
 for filename,uri in FILES.items():
  path=OUT/'raw'/(filename+'.gz')
  if not path.exists():
   if not args.acquire:raise RuntimeError('Missing retained source; use --acquire')
   b=urllib.request.urlopen(BASE+uri,timeout=60).read();b=gzip.decompress(b) if b[:2]==b'\x1f\x8b' else b;path.write_bytes(gzip.compress(b,mtime=0))
  b=gzip.decompress(path.read_bytes());assert BASE+uri not in expected or m.digest(b)==expected[BASE+uri], 'Source changed: '+uri;evidence.append({'url':BASE+uri,'retained':str(path.relative_to(ROOT)),'sha256':m.digest(b),'decodedBytes':len(b)})
 raw=gzip.decompress((OUT/'raw/18_268621_55475.b3dm.gz').read_bytes());doc,binary,batch,feature=next(m.b3dm_parts(raw));isolated,compact,attrs=extract(doc,binary,batch);(OUT/'pilot-original.glb').write_bytes(pack(isolated,compact));(OUT/'pilot-metadata.json').write_text(json.dumps({'bagId':BAG,'sourceAttributes':attrs,'featureTable':feature,'sourceEvidence':evidence,'license':'CC BY 4.0','licenseEvidence':'catalog-evidence.json','photographyCaptureDate':'Not established by model creationDate or file Last-Modified.'},indent=2)+'\n');render(isolated,compact,'pilot-view-a.png',[1,.8,1]);render(isolated,compact,'pilot-view-b.png',[-1,.8,-1]);print('pilot',len(compact),'bytes',sum(len(m.accessor(isolated,compact,p['indices']))//3 for mesh in isolated['meshes'] for p in mesh['primitives']),'triangles')
if __name__=='__main__':main()
