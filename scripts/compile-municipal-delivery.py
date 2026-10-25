#!/usr/bin/env python3
# Written by AI on 2026-10-25 by model GPT-6 Astra.
"""Compile unchanged source B3DM geometry with screen-resolution photography.
Derived packs and retained originals live outside Git. No upload is performed.
"""
import argparse,concurrent.futures,copy,gzip,hashlib,io,json,math,pathlib,posixpath,struct,time,urllib.request
from PIL import Image
BASE='https://www.3drotterdam.nl/datasource-data/3adbe5af-d05c-475a-b34c-59e69ba8dadc/'
DTYPES={5120:'i1',5121:'u1',5122:'<i2',5123:'<u2',5125:'<u4',5126:'<f4'}
SIZES={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}
def sha(b):return hashlib.sha256(b).hexdigest()
def pad(b,fill=b'\0'):return b+fill*((-len(b))%4)
def get_source(uri,root,acquire):
 p=root/'raw'/uri;p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():wire=p.read_bytes()
 elif acquire:
  with urllib.request.urlopen(BASE+uri,timeout=90) as response:wire=response.read()
  temp=p.with_suffix(p.suffix+'.pending');temp.write_bytes(wire);temp.replace(p)
 else:raise FileNotFoundError(f'{p}: use --acquire for missing source')
 return gzip.decompress(wire) if wire[:2]==b'\x1f\x8b' else wire

def compile_tile(uri,root,acquire,limit):
 started=time.monotonic();raw=get_source(uri,root,acquire);header=list(struct.unpack_from('<4s6I',raw));off=28+sum(header[3:]);glb=raw[off:];js=struct.unpack_from('<I',glb,12)[0];doc=json.loads(glb[20:20+js]);binary=glb[28+js:];original_doc=copy.deepcopy(doc)
 image_views={};dimensions=[];webp_images=set()
 for ii,im in enumerate(doc.get('images',[])):
  vi=im['bufferView'];v=doc['bufferViews'][vi];original=binary[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']];image=Image.open(io.BytesIO(original));image.thumbnail((limit,limit),Image.Resampling.BOX);dimensions.append(image.size)
  encoded=io.BytesIO();image.convert('RGBA').save(encoded,format='WEBP',lossless=True,exact=True,method=4);data=encoded.getvalue()
  # Retain the original exactly when no smaller representation is available.
  if image.size==Image.open(io.BytesIO(original)).size and len(original)<=len(data):data=original
  else:im['mimeType']='image/webp';webp_images.add(ii)
  image_views[vi]=data
 for texture in doc.get('textures',[]):
  if texture.get('source') in webp_images:texture.setdefault('extensions',{})['EXT_texture_webp']={'source':texture.pop('source')}
 if webp_images:
  for key in ['extensionsUsed','extensionsRequired']:doc[key]=list(dict.fromkeys(doc.get(key,[])+['EXT_texture_webp']))
 for material in doc.get('materials',[]):
  ti=material.get('pbrMetallicRoughness',{}).get('baseColorTexture',{}).get('index')
  if ti is not None:material.setdefault('extras',{})['municipalMipDimensions']=list(dimensions[original_doc['textures'][ti]['source']])
 assert all(doc.get(key)==original_doc.get(key) for key in ['accessors','meshes','nodes','scenes','scene'])
 payload=bytearray();geometry_before=hashlib.sha256();geometry_after=hashlib.sha256()
 for vi,v in enumerate(doc['bufferViews']):
  original=binary[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']];data=image_views.get(vi,original)
  payload.extend(b'\0'*((-len(payload))%4));v['byteOffset']=len(payload);v['byteLength']=len(data);payload.extend(data)
  if vi not in image_views:geometry_before.update(original);geometry_after.update(data)
 assert geometry_before.digest()==geometry_after.digest()
 doc['buffers'][0]['byteLength']=len(payload);jb=pad(json.dumps(doc,separators=(',',':')).encode(),b' ');bb=pad(bytes(payload));newglb=struct.pack('<4sII',b'glTF',2,28+len(jb)+len(bb))+struct.pack('<I4s',len(jb),b'JSON')+jb+struct.pack('<I4s',len(bb),b'BIN\0')+bb
 prefix=bytearray(raw[:off]);struct.pack_into('<I',prefix,8,len(prefix)+len(newglb));derived=bytes(prefix)+newglb
 # Feature/batch tables (including RTC and BAG identities) remain byte-exact.
 assert derived[12:off]==raw[12:off]
 compressed=gzip.compress(derived,compresslevel=6,mtime=0);p=root/'tiles'/f'{sha(compressed)}.b3dm.gz';p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(compressed)
 return {'compilerVersion':2,'source':uri,'sourceSha256':sha(raw),'derivedSha256':sha(derived),'gzipSha256':sha(compressed),'file':str(p.relative_to(root)),'length':len(compressed),'sourceBytes':len(raw),'geometrySha256':geometry_before.hexdigest(),'seconds':round(time.monotonic()-started,3)}

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--output',required=True,type=pathlib.Path);ap.add_argument('--bbox',nargs=4,type=float,metavar=('WEST','SOUTH','EAST','NORTH'));ap.add_argument('--acquire',action='store_true');ap.add_argument('--workers',type=int,default=2);ap.add_argument('--limit',type=int,default=256);args=ap.parse_args();root=args.output.resolve();root.mkdir(parents=True,exist_ok=True);bbox=[math.radians(v) for v in args.bbox] if args.bbox else None
 def intersects(node):
  r=node.get('boundingVolume',{}).get('region');return not bbox or not r or (r[0]<=bbox[2] and r[2]>=bbox[0] and r[1]<=bbox[3] and r[3]>=bbox[1])
 selected=[]
 def walk(node,base):
  if not intersects(node):return
  content=node.get('content',{});u=content.get('uri',content.get('url'))
  if u:
   uri=posixpath.normpath(posixpath.join(posixpath.dirname(base),u))
   if uri.endswith('.json'):walk(json.loads(get_source(uri,root,args.acquire))['root'],uri)
   elif uri.startswith('18/'):selected.append(uri)
  for child in node.get('children',[]):walk(child,base)
 walk(json.loads(get_source('tileset.json',root,args.acquire))['root'],'tileset.json');selected=sorted(set(selected));print(f'Selected complete area: {len(selected)} source leaves',flush=True);records=[];checkpoint=root/'compiled-tiles.json';prior={r['source']:r for r in json.loads(checkpoint.read_text()).get('tiles',[])} if checkpoint.exists() else {}
 def job(uri):
  if uri in prior and prior[uri].get('compilerVersion')==2 and (root/prior[uri]['file']).exists():return prior[uri]
  return compile_tile(uri,root,args.acquire,args.limit)
 pool=concurrent.futures.ThreadPoolExecutor(max_workers=args.workers)
 try:
  for record in pool.map(job,selected):
   records.append(record);checkpoint.write_text(json.dumps({'sourceRoot':BASE,'limit':args.limit,'bbox':args.bbox,'tiles':records},indent=2));print(record['source'],record['length'],flush=True)
 finally:pool.shutdown(wait=True,cancel_futures=True)
 packs=[];pack=None;offset=0;pack_index=0
 for record in records:
  data=(root/record['file']).read_bytes()
  if pack is None or offset+len(data)>64*1024*1024:
   if pack:pack.close()
   pack_index+=1;name=f'municipal-{args.limit}-{pack_index:04}.pack';pack=(root/name).open('wb');packs.append(name);offset=0
  pack.write(data);record['pack']=name;record['offset']=offset;offset+=len(data);record.pop('file')
 if pack:pack.close()
 renamed={}
 for name in packs:
  immutable=f'municipal-{args.limit}-{sha((root/name).read_bytes())}.pack';(root/name).replace(root/immutable);renamed[name]=immutable
 packs=[renamed[name] for name in packs]
 for record in records:
  record['pack']=renamed[record['pack']];record.pop('geometricError',None);record.pop('samplingMetersPerTexel',None)
 manifest={'version':1,'sourceRoot':BASE,'attribution':'Gemeente Rotterdam — 3D Rotterdam','license':'CC BY 4.0','licenseUrl':'https://creativecommons.org/licenses/by/4.0/','edition':'3adbe5af-d05c-475a-b34c-59e69ba8dadc','transformation':f'Unchanged source geometry/UV/RTC/BAG; BOX {args.limit}px photography, lossless WebP; original native fallback','limit':args.limit,'bbox':args.bbox,'packs':{p:{'bytes':(root/p).stat().st_size,'sha256':sha((root/p).read_bytes())} for p in packs},'tiles':{r.pop('source'):r for r in records}}
 (root/'manifest.json').write_text(json.dumps(manifest,separators=(',',':')));print('Complete',len(records),'tiles',sum(p['bytes'] for p in manifest['packs'].values()),'packed bytes',flush=True)
if __name__=='__main__':main()
