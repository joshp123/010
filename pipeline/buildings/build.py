"""Written by AI on 2026-10-25 by model GPT-6.1 Sol.

Rebuild building meshes from archived municipal 3D Tiles. No inferred geometry.
"""
import argparse, concurrent.futures, datetime, gzip, hashlib, io, json, math, os, re, struct, subprocess, threading
from pathlib import Path
from urllib.parse import urljoin
import numpy as np
import requests
from PIL import Image
from shapely import union_all, set_precision
from shapely.geometry import Polygon
from pyproj import Transformer

ROOT=Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
BASE='https://www.3drotterdam.nl/datasource-data/'
LAYERS={'textured2018':'a6aee273-9406-41c4-a504-de2a59f7d514','lod2':'8b5d0ded-a222-4e44-bc70-2992bc2192fc','bridges':'69926a30-444d-46bb-995e-bb14b151d3ab'}
DATE='2026-10-25'
CORE=(89750,435750,90750,436750)
M0=(89750,435250,92000,436750)
M1=(89750,434750,96500,438000)
DTYPES={5120:'i1',5121:'u1',5122:'<i2',5123:'<u2',5125:'<u4',5126:'<f4'}
SIZES={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}

class Archive:
 def __init__(self,name):
  self.name=name;self.root=ROOT/'sources'/name/DATE;self.root.mkdir(parents=True,exist_ok=True);self.lock=threading.Lock()
  self.manifest=self.root/'manifest.json';self.files={}
  if self.manifest.exists():self.files={r['path']:r for r in json.loads(self.manifest.read_text())['files']}
 def fetch(self,url):
  relative=url.split(LAYERS[self.name]+'/')[1];p=self.root/relative
  if not p.exists():
   r=requests.get(url,timeout=90,stream=True);r.raise_for_status();raw=r.raw.read(decode_content=False)
   p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
   record={'path':relative,'url':url,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'fetched_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'content_encoding':r.headers.get('Content-Encoding')}
   with self.lock:self.files[relative]=record
  raw=p.read_bytes()
  # Earlier format probes stored decoded response entities. Register these too.
  if relative not in self.files:
   self.files[relative]={'path':relative,'url':url,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'fetched_at':datetime.datetime.fromtimestamp(p.stat().st_mtime,datetime.timezone.utc).isoformat(),'content_encoding':'identity','note':'initial format-probe download; response entity retained'}
  return gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
 def save(self):
  self.manifest.write_text(json.dumps({'dataset':self.name,'tileset':BASE+LAYERS[self.name]+'/tileset.json','licence':'Public domain','credit':'Gemeente Rotterdam','licence_source':'https://data.overheid.nl/dataset/10230-rotterdam-3d','files':sorted(self.files.values(),key=lambda x:x['path'])},indent=2))

def discover(archive,bounds):
 # Bounds culling only: approximate lon/lat is sufficient with 100m padding.
 from pyproj import network
 network.set_network_enabled(False)
 tr=Transformer.from_crs(28992,4258,always_xy=True)
 x0,y0,x1,y1=bounds
 corners=[tr.transform(x,y) for x in (x0-100,x1+100) for y in (y0-100,y1+100)]
 roi=np.radians([min(c[0] for c in corners),min(c[1] for c in corners),max(c[0] for c in corners),max(c[1] for c in corners)])
 def intersect(t):
  r=t.get('boundingVolume',{}).get('region')
  return r is None or not(r[2]<roi[0] or r[0]>roi[2] or r[3]<roi[1] or r[1]>roi[3])
 def visit(t,url,parent):
  if not intersect(t):return []
  matrix=parent@np.array(t.get('transform',np.eye(4).flatten(order='F'))).reshape((4,4),order='F')
  children=t.get('children',[]);out=[]
  # REPLACE hierarchy: only deepest descendant content, never coarse ancestors.
  if children:
   for child in children:out.extend(visit(child,url,matrix))
  else:
   content=t.get('content',{});uri=content.get('uri',content.get('url'))
   if uri:
    target=urljoin(url,uri)
    if target.endswith('.json'):
     j=json.loads(archive.fetch(target));out.extend(visit(j['root'],target,matrix))
    else:out.append((target,matrix))
  return out
 url=BASE+LAYERS[archive.name]+'/tileset.json'
 result=visit(json.loads(archive.fetch(url))['root'],url,np.eye(4));archive.save()
 return result

def unpack_glb(data):
 if data[:4]!=b'glTF':raise ValueError('Expected embedded GLB')
 offset=12;binary=b'';j=None
 while offset+8<=struct.unpack_from('<I',data,8)[0]:
  length,kind=struct.unpack_from('<II',data,offset);chunk=data[offset+8:offset+8+length];offset+=length+8
  if kind==0x4e4f534a:j=json.loads(chunk)
  elif kind==0x004e4942:binary=chunk
 return j,binary

def b3dms(data):
 if data[:4]==b'cmpt':
  p=16
  for _ in range(struct.unpack_from('<I',data,12)[0]):
   n=struct.unpack_from('<I',data,p+8)[0];yield from b3dms(data[p:p+n]);p+=n
 elif data[:4]==b'b3dm':
  fj,fb,bj,bb=struct.unpack_from('<4I',data,12);p=28
  ft=json.loads(data[p:p+fj]) if fj else {};p+=fj+fb
  batch=json.loads(data[p:p+bj]) if bj else {};p+=bj+bb
  yield ft,batch,*unpack_glb(data[p:])
 elif data[:4]==b'vctr':return # duplicate vector footprints, not building triangles
 else:raise ValueError(f'Unsupported payload {data[:4]}')

def accessor(j,binary,index):
 a=j['accessors'][index];v=j['bufferViews'][a['bufferView']];dtype=np.dtype(DTYPES[a['componentType']]);n=SIZES[a['type']]
 offset=v.get('byteOffset',0)+a.get('byteOffset',0);stride=v.get('byteStride',dtype.itemsize*n)
 result=np.ndarray((a['count'],n),dtype=dtype,buffer=binary,offset=offset,strides=(stride,dtype.itemsize)).copy()
 if a.get('normalized') and a['componentType']!=5126:
  limits=np.iinfo(dtype);result=result.astype(float)/limits.max
  if limits.min<0:result=np.maximum(-1,result)
 return result

def node_matrix(node):
 if 'matrix' in node:return np.array(node['matrix']).reshape(4,4,order='F')
 from scipy.spatial.transform import Rotation
 m=np.eye(4);m[:3,:3]=Rotation.from_quat(node.get('rotation',[0,0,0,1])).as_matrix()@np.diag(node.get('scale',[1,1,1]));m[:3,3]=node.get('translation',[0,0,0]);return m

def mesh_instances(j):
 def walk(index,parent):
  node=j['nodes'][index];m=parent@node_matrix(node)
  if 'mesh'in node:
   for primitive in j['meshes'][node['mesh']]['primitives']:
    if primitive.get('mode',4)==4:yield primitive,m
  for child in node.get('children',[]):yield from walk(child,m)
 for index in j['scenes'][j.get('scene',0)]['nodes']:yield from walk(index,np.eye(4))

def material(j,binary,index,key):
 m=j.get('materials',[{}])[index];old=m.get('extensions',{}).get('KHR_techniques_webgl',{}).get('values',{})
 pbr=m.get('pbrMetallicRoughness',{});texture=pbr.get('baseColorTexture',old.get('u_diffuse_tex'))
 color=pbr.get('baseColorFactor',old.get('u_diffuse_mat',[.8,.8,.8,1]));image=None;sampler={}
 if texture is not None:
  texture=j['textures'][texture['index']];im=j['images'][texture['source']]
  if 'bufferView' not in im:raise ValueError('External source image unsupported')
  v=j['bufferViews'][im['bufferView']];raw=binary[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']]
  source=Image.open(io.BytesIO(raw)).convert('RGB');source.thumbnail((2048,2048),Image.Resampling.LANCZOS);stream=io.BytesIO();source.save(stream,format='JPEG',quality=90);image=stream.getvalue()
  sampler=j.get('samplers',[{}])[texture.get('sampler',0)]
 return {'key':key,'color':color,'image':image,'sampler':sampler,'doubleSided':m.get('doubleSided',False)}

def load_tile(archive,item,transform):
 url,tilematrix=item;data=archive.fetch(url);features={};materials={}
 y_up_to_ecef=np.array([[1,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1]],float)
 for part,(ft,batch,j,binary) in enumerate(b3dms(data)):
  rtc=np.array(ft.get('RTC_CENTER',j.get('extensions',{}).get('CESIUM_RTC',{}).get('center',[0,0,0])))
  for primitive,matrix in mesh_instances(j):
   attributes=primitive['attributes'];positions=accessor(j,binary,attributes['POSITION']).astype(float)
   ecef=(np.c_[positions,np.ones(len(positions))]@(y_up_to_ecef@matrix).T)[:,:3]+rtc
   ecef=(np.c_[ecef,np.ones(len(ecef))]@tilematrix.T)[:,:3]
   rd=np.array(transform.transform(*ecef.T)).T
   indices=accessor(j,binary,primitive['indices']).ravel().astype(int) if 'indices'in primitive else np.arange(len(rd))
   if len(indices)%3:raise ValueError('Triangle primitive has non-triangle index count')
   triangles=indices.reshape(-1,3)
   batch_index=attributes.get('_BATCHID',attributes.get('_BATCH_ID'))
   ids=accessor(j,binary,batch_index).ravel().astype(int) if batch_index is not None else np.zeros(len(rd),int)
   if not np.all(ids[triangles]==ids[triangles[:,0]][:,None]):raise ValueError('Triangle crosses source features')
   uv=accessor(j,binary,attributes['TEXCOORD_0']) if 'TEXCOORD_0'in attributes else np.zeros((len(rd),2))
   material_index=primitive.get('material',0);key=f'{url}#{part}/{material_index}'
   if key not in materials:materials[key]=material(j,binary,material_index,key)
   for feature_id in np.unique(ids[triangles[:,0]]):
    properties={k:v[feature_id] for k,v in batch.items() if isinstance(v,list) and len(v)>feature_id}
    rawid=str(properties.get('id',properties.get('gebouwnummer',properties.get('GEBOUWNUMMER',feature_id))))
    bag_match=re.search(r'(\d{16})',rawid);identity=bag_match.group(1) if bag_match else rawid
    kind='bridge' if archive.name=='bridges' else 'building'
    feature=features.setdefault(identity,{'bag_id':identity if bag_match else None,'source_id':rawid,'kind':kind,'source':'textured2018' if archive.name=='bridges' else archive.name,'properties':properties,'parts':[],'source_url':url})
    selection=triangles[ids[triangles[:,0]]==feature_id].ravel()
    feature['parts'].append({'positions':rd[selection],'uv':uv[selection],'material':materials[key]})
 return features

def describe_feature(f):
 points=np.concatenate([p['positions'] for p in f['parts']]);f['bounds']=np.r_[points.min(axis=0),points.max(axis=0)]
 # Union projected triangle surfaces gives the actual whole-building footprint,
 # including concavities; vertical walls contribute zero projected area.
 polygons=[]
 for part in f['parts']:
  triangles=part['positions'].reshape(-1,3,3)
  for t in triangles:
   cross=np.cross(t[1]-t[0],t[2]-t[0])
   if abs(cross[2])>1e-5:polygons.append(Polygon(t[:,:2]))
 footprint=union_all(set_precision(polygons,grid_size=0.0001))
 if footprint.is_empty:
  f['centroid']=points[:,:2].mean(axis=0)
 else:f['centroid']=np.array([footprint.centroid.x,footprint.centroid.y])
 f['height_m']=float(points[:,2].max()-points[:,2].min())

def finish_feature(f):
 seen=set();unique=[]
 for p in f['parts']:
  tris=p['positions'].reshape(-1,3,3);uv=p['uv'].reshape(-1,3,2);keep=[]
  for n,t in enumerate(tris):
   key=tuple(sorted(tuple(v) for v in np.round(t,4)))
   if key not in seen:seen.add(key);keep.append(n)
  if keep:unique.append({'positions':tris[keep].reshape(-1,3),'uv':uv[keep].reshape(-1,2),'material':p['material']})
 f['parts']=unique;describe_feature(f);return f

def combine_features(items,workers=8):
 result={}
 for features in items:
  for identity,f in features.items():
   if identity in result:
    # Split source content parts with one BAG are one feature. Exact duplicate
    # fragments can occur at tile borders; retain each triangle once.
    result[identity]['parts'].extend(f['parts'])
   else:result[identity]=f
 # Send material keys rather than repeated image bytes through worker pipes.
 materials={p['material']['key']:p['material'] for f in result.values() for p in f['parts']}
 for f in result.values():
  for p in f['parts']:p['material']=p['material']['key']
 with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
  finished=list(executor.map(finish_feature,result.values(),chunksize=16))
 for f in finished:
  for p in f['parts']:p['material']=materials[p['material']]
 result={identity:f for identity,f in zip(result,finished)}
 return result

class GLB:
 def __init__(self):
  self.j={'asset':{'version':'2.0','generator':'010 municipal building conversion'},'scene':0,'scenes':[{'nodes':[0]}],'nodes':[{'mesh':0}],'meshes':[{'primitives':[]}],'accessors':[],'bufferViews':[],'buffers':[{}],'materials':[],'textures':[],'images':[],'samplers':[],'extras':{'features':[]}};self.binary=bytearray()
 def data(self,data,target=None):
  while len(self.binary)%4:self.binary.append(0)
  index=len(self.j['bufferViews']);v={'buffer':0,'byteOffset':len(self.binary),'byteLength':len(data)}
  if target:v['target']=target
  self.j['bufferViews'].append(v);self.binary.extend(data);return index
 def attribute(self,array,typ,component):
  array=np.ascontiguousarray(array,dtype=DTYPES[component]);v=self.data(array.tobytes(),34962)
  a={'bufferView':v,'componentType':component,'count':len(array),'type':typ}
  if typ=='VEC3':a.update(min=array.min(axis=0).tolist(),max=array.max(axis=0).tolist())
  index=len(self.j['accessors']);self.j['accessors'].append(a);return index
 def write(self,path):
  self.j['buffers'][0]['byteLength']=len(self.binary)
  for key in ['accessors','bufferViews','materials','textures','images','samplers']:
   if not self.j[key]:self.j.pop(key)
  if not self.binary:self.j.pop('buffers')
  while len(self.binary)%4:self.binary.append(0)
  encoded=json.dumps(self.j,separators=(',',':')).encode();encoded+=b' ' *((-len(encoded))%4)
  binary_chunk=struct.pack('<II',len(self.binary),0x004e4942)+self.binary if self.binary else b''
  path.write_bytes(struct.pack('<III',0x46546c67,2,20+len(encoded)+len(binary_chunk))+struct.pack('<II',len(encoded),0x4e4f534a)+encoded+binary_chunk)

def write_tile(tile,features):
 x0,y0=tile;name=f'x{x0}_y{y0}';directory=ROOT/'scene/v1/tiles'/name;directory.mkdir(parents=True,exist_ok=True);glb=GLB();groups={};counts={'textured2018':0,'lod2':0,'bridges':0};wall=photo=bound_photo=degenerate_photo=0.;triangles=0;texturebytes=0
 for index,f in enumerate(features):
  facts=f.get('bag_facts',{})
  feature_record={k:f[k] for k in ('bag_id','kind','source','height_m')}|{'year':facts.get('year'),'use':facts.get('use'),'status':facts.get('status'),'source_id':f['source_id'],'source_url':f['source_url'],'facade_area_m2':0.,'photo_facade_area_m2':0.}
  if f['kind']=='building':feature_record['bag']=facts
  glb.j['extras']['features'].append(feature_record)
  counts['bridges' if f['kind']=='bridge' else f['source']]+=1
  for p in f['parts']:
   material=p['material'];group=groups.setdefault(material['key'],{'material':material,'positions':[],'uv':[],'ids':[],'normals':[]})
   rd=p['positions'];local=np.column_stack((rd[:,0]-x0,rd[:,2],-(rd[:,1]-y0)))
   t=local.reshape(-1,3,3);normal=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);length=np.linalg.norm(normal,axis=1);norm=normal/np.maximum(length[:,None],1e-30)
   if f['kind']=='building':
    iswall=np.abs(norm[:,1])<0.2;area=float((length[iswall]*.5).sum());wall+=area;feature_record['facade_area_m2']+=area
    if material['image'] is not None:
     bound_photo+=area
     uv=p['uv'].reshape(-1,3,2);first=uv[:,1]-uv[:,0];second=uv[:,2]-uv[:,0]
     uv_area=np.abs(first[:,0]*second[:,1]-first[:,1]*second[:,0])*.5
     photo_area=float((length[iswall & (uv_area>1e-10)]*.5).sum());photo+=photo_area;feature_record['photo_facade_area_m2']+=photo_area
     degenerate_photo+=float((length[iswall & (uv_area<=1e-10)]*.5).sum())
   group['positions'].append(local);group['uv'].append(p['uv']);group['ids'].append(np.full(len(local),index));group['normals'].append(np.repeat(norm,3,axis=0));triangles+=len(t)
 for group in groups.values():
  m=group['material'];pbr={'baseColorFactor':m['color'],'metallicFactor':0,'roughnessFactor':1}
  if m['image'] is not None:
   v=glb.data(m['image']);imindex=len(glb.j['images']);glb.j['images'].append({'bufferView':v,'mimeType':'image/jpeg'});si=len(glb.j['samplers']);glb.j['samplers'].append(m['sampler']);ti=len(glb.j['textures']);glb.j['textures'].append({'source':imindex,'sampler':si});pbr['baseColorTexture']={'index':ti};texturebytes+=len(m['image'])
  mi=len(glb.j['materials']);glb.j['materials'].append({'name':m['key'],'pbrMetallicRoughness':pbr,'doubleSided':m['doubleSided']})
  attrs={}
  for semantic,field,typ,component in [('POSITION','positions','VEC3',5126),('NORMAL','normals','VEC3',5126),('TEXCOORD_0','uv','VEC2',5126),('_FEATURE_ID_0','ids','SCALAR',5126)]:attrs[semantic]=glb.attribute(np.concatenate(group[field]),typ,component)
  glb.j['meshes'][0]['primitives'].append({'attributes':attrs,'material':mi,'mode':4})
 if not groups:glb.j['nodes']=[{}];glb.j.pop('meshes')
 glb.write(directory/'buildings.glb')
 return {'buildings':{'by_source':counts,'triangles':triangles,'texture_bytes':texturebytes,'facade_area_m2':wall,'photo_facade_area_m2':photo,'image_bound_facade_area_m2':bound_photo,'degenerate_uv_facade_area_m2':degenerate_photo,'photo_facade_fraction':photo/wall if wall else None,'sha256':hashlib.sha256((directory/'buildings.glb').read_bytes()).hexdigest(),'features':glb.j['extras']['features']}}

def write_tile_job(item):
 tile,features=item
 return f'x{tile[0]}_y{tile[1]}',write_tile(tile,sorted(features,key=lambda f:f['source_id']))

def source_snapshot(archive):
 raw=archive.manifest.read_bytes();digest=hashlib.sha256(raw).hexdigest()
 path=archive.root/'manifests'/f'{digest}.json';path.parent.mkdir(exist_ok=True);path.write_bytes(raw)
 return {'manifest':str(path),'sha256':digest}

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--area',choices=['core','m0','m1'],default='core');parser.add_argument('--workers',type=int,default=8);args=parser.parse_args();bounds={'core':CORE,'m0':M0,'m1':M1}[args.area]
 from transform import ecef_to_rdnap
 transform=ecef_to_rdnap();layers={};archives=[]
 for name in LAYERS:
  archive=Archive(name);archives.append(archive);items=discover(archive,bounds);print(name,'deepest source tiles',len(items),flush=True)
  def load(item):return load_tile(archive,item,transform)
  with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:parts=list(executor.map(load,items))
  archive.save();layers[name]=combine_features(parts,args.workers);print(name,'features',len(layers[name]),flush=True)
 selected=[];decisions={'matched_within_1m':0,'changed':0,'old_has_no_photos':0,'no_old_match':0,'old_without_current':sum(bool(bounds[0]<=f['centroid'][0]<bounds[2] and bounds[1]<=f['centroid'][1]<bounds[3]) for identity,f in layers['textured2018'].items() if identity not in layers['lod2'])}
 for identity,new in layers['lod2'].items():
  if not(bounds[0]<=new['centroid'][0]<bounds[2] and bounds[1]<=new['centroid'][1]<bounds[3]):continue
  old=layers['textured2018'].get(identity)
  # Horizontal footprint bounding boxes. Geometry and UVs are kept together.
  old_has_photo=old is not None and any(p['material']['image'] is not None for p in old['parts'])
  if old_has_photo and np.max(np.abs(old['bounds'][[0,1,3,4]]-new['bounds'][[0,1,3,4]]))<=1.0:
   chosen=old;decisions['matched_within_1m']+=1
  else:chosen=new;decisions[('changed' if old_has_photo else 'old_has_no_photos') if old else 'no_old_match']+=1
  # Use current footprint centroid for stable tile ownership across versions.
  chosen['centroid']=new['centroid'];selected.append(chosen)
 selected+=list(layers['bridges'].values())
 tiles={}
 for x in range(bounds[0],bounds[2],250):
  for y in range(bounds[1],bounds[3],250):tiles[(x,y)]=[]
 for f in selected:
  x,y=f['centroid'];tile=(math.floor(x/250)*250,math.floor(y/250)*250)
  if tile in tiles:tiles[tile].append(f)
 from bag import load_facts
 facts=load_facts(bounds,building_ids=[f['bag_id'] for features in tiles.values() for f in features if f['kind']=='building' and f['bag_id']])
 for features in tiles.values():
  for f in features:
   if f['kind']=='building':f['bag_facts']=facts.get(f['bag_id'],{'year':None,'status':None,'bag_coverage':'not_found'})
 with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as executor:
  tile_results=list(executor.map(write_tile_job,tiles.items(),chunksize=1))
 records={name:record for name,record in tile_results}
 output=ROOT/'scene/v1';output.mkdir(parents=True,exist_ok=True)
 report={'area':args.area,'bounds':bounds,'selection':decisions,'tiles':records,'sources':{a.name:source_snapshot(a) for a in archives},'facade_definition':'Building triangles with |unit normal dot vertical| < 0.2; 3D triangle area weighted. Bridges excluded. A photo texture means a bound source image and original UVs with UV triangle area >1e-10; degenerate UV triangles are excluded. This does not certify image content or freshness.','code_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
 report['totals']={key:sum(r['buildings'][key] for r in records.values()) for key in ['triangles','texture_bytes','facade_area_m2','photo_facade_area_m2','image_bound_facade_area_m2','degenerate_uv_facade_area_m2']};report['totals']['photo_facade_fraction']=report['totals']['photo_facade_area_m2']/report['totals']['facade_area_m2'];report['totals']['counts']={s:sum(r['buildings']['by_source'][s] for r in records.values()) for s in ['textured2018','lod2','bridges']}
 building_features=[f for r in records.values() for f in r['buildings']['features'] if f['kind']=='building']
 report['bag_coverage']={key:sum(bool(f.get('bag',{}).get(key)) for f in building_features) for key in ['year','status']}
 report['bag_coverage'].update(buildings=len(building_features),matched=sum(f['bag']['bag_coverage']=='complete' for f in building_features),use_resolved=sum(f['bag']['bag_coverage']=='complete' for f in building_features),with_use=sum(bool(f['use']) for f in building_features),storeys_stated=0)
 report['largest_without_photo']=sorted((f for f in building_features if f['photo_facade_area_m2']==0),key=lambda f:f['facade_area_m2'],reverse=True)[:20]
 bag_manifest=ROOT/'sources/bag/2026-10-26/manifest.json'
 if bag_manifest.exists():report['sources']['bag']={'manifest':str(bag_manifest),'sha256':hashlib.sha256(bag_manifest.read_bytes()).hexdigest()}
 (output/f'buildings-{args.area}-report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report['totals'],indent=2),flush=True)
 # Manifest merge is separate and lock-protected, to coexist with ground writer.
 from manifest import merge_buildings
 merge_buildings(report)
if __name__=='__main__':main()
