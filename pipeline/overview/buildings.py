"""Written by AI on 2026-10-26 by model GPT-6.
Municipal LOD2 and tanks -> compact untextured whole-gemeente overview.
"""
import sys, json, math, hashlib, datetime, gzip, threading, concurrent.futures, argparse, time
from pathlib import Path
from urllib.parse import urljoin
import numpy as np
import requests
from shapely import union_all, constrained_delaunay_triangles, set_precision
from shapely.geometry import Polygon, shape, mapping
from shapely.errors import GEOSException
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'buildings'))
import build as detailed
from transform import ecef_to_rdnap
ROOT=detailed.ROOT
OUT=ROOT/'scene/overview-v1'
DATASETS={'lod2': detailed.LAYERS['lod2'], 'tanks':'c70023a7-2878-41e9-bb81-a7c454bc310a','bridges':'06595036-c78e-4081-ab25-e8f88b66bc19'}
class Archive:
 def __init__(self,name):
  self.reextract=False;self.name=name;self.root=ROOT/'sources'/('overview-'+name)/'2026-10-26';self.root.mkdir(parents=True,exist_ok=True);self.manifest=self.root/'manifest.json';self.lock=threading.Lock();self.files={};self.base=detailed.BASE+DATASETS[name]+'/'
  if self.manifest.exists():self.files={f['path']:f for f in json.loads(self.manifest.read_text())['files']}
 def fetch(self,url):
  relative=url.removeprefix(self.base);path=self.root/relative
  if not path.exists():
   for attempt in range(4):
    try:
     response=requests.get(url,timeout=120,stream=True);response.raise_for_status();raw=response.raw.read(decode_content=False);break
    except requests.RequestException:
     if attempt==3:raise
     time.sleep(2**attempt)
   path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
   with self.lock:self.files[relative]={'path':relative,'url':url,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'fetched_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'content_encoding':response.headers.get('Content-Encoding')}
  raw=path.read_bytes()
  if relative not in self.files:
   with self.lock:self.files[relative]={'path':relative,'url':url,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'fetched_at':datetime.datetime.fromtimestamp(path.stat().st_mtime,datetime.timezone.utc).isoformat()}
  return gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
 def save(self):
  self.manifest.write_text(json.dumps({'dataset':self.name,'tileset':self.base+'tileset.json','licence':'Public domain','credit':'Gemeente Rotterdam','licence_source':'https://data.overheid.nl/dataset/10230-rotterdam-3d','files':sorted(self.files.values(),key=lambda f:f['path'])},indent=2))

def discover(archive):
 def visit(node,url,parent):
  matrix=parent@np.array(node.get('transform',np.eye(4).flatten(order='F'))).reshape((4,4),order='F')
  if node.get('children'):
   for child in node['children']:yield from visit(child,url,matrix)
  else:
   content=node.get('content',{});uri=content.get('uri',content.get('url'))
   if uri:
    target=urljoin(url,uri)
    if target.endswith('.json'):yield from visit(json.loads(archive.fetch(target))['root'],target,matrix)
    else:yield target,matrix
 url=archive.base+'tileset.json';items=list(visit(json.loads(archive.fetch(url))['root'],url,np.eye(4)));archive.save();return items

def extract(archive,item,transform):
 url,tilematrix=item
 # Shared source decoder, with material interpretation bypassed: overview has no textures.
 cache_path=archive.root/'derived-v2'/((url.removeprefix(archive.base))+'.json.gz')
 if cache_path.exists() and not archive.reextract:
  rows=json.loads(gzip.decompress(cache_path.read_bytes()))
  for row in rows:row['footprint']=shape(row['footprint'])
  return rows
 features=detailed.load_tile(archive,item,transform)
 output=[]
 for identity,feature in features.items():
  points=np.concatenate([part['positions'] for part in feature['parts']]);triangles=points.reshape(-1,3,3)
  projected=triangles[:,:,:2];vectors=projected[:,1]-projected[:,0];others=projected[:,2]-projected[:,0]
  areas=np.abs(vectors[:,0]*others[:,1]-vectors[:,1]*others[:,0]);valid=projected[areas>1e-5]
  if not len(valid):continue
  union_precision=0.
  try:footprint=union_all([Polygon(triangle) for triangle in valid])
  except GEOSException:
   union_precision=.001
   footprint=union_all([Polygon(triangle) for triangle in valid],grid_size=union_precision)
  if not footprint.is_valid:footprint=footprint.buffer(0)
  if footprint.is_empty:continue
  output.append({'union_precision_m':union_precision,'identity':identity,'bag_id':feature['bag_id'],'kind':'storage_tank' if archive.name=='tanks' else feature['kind'],'source':archive.name,'source_id':feature['source_id'],'source_urls':[url],'footprint':footprint,'base_m':float(points[:,2].min()),'roof_m':float(points[:,2].max()),'year':feature['properties'].get('BOUWJAAR'),'use':feature['properties'].get('GEBRUIKSDOEL')})
 cache_path.parent.mkdir(parents=True,exist_ok=True);cache_path.write_bytes(gzip.compress(json.dumps([row|{'footprint':mapping(row['footprint'])} for row in output],separators=(',',':')).encode()))
 return output

def polygons(geometry):
 if geometry.geom_type=='Polygon':yield geometry
 elif hasattr(geometry,'geoms'):
  for child in geometry.geoms:yield from polygons(child)

def write_tile(name,features,tolerance):
 xmin,ymin=map(int,[name.split('_')[0][1:],name.split('_')[1][1:]])
 glb=detailed.GLB();positions=[];identifiers=[];indices=[];sidecar=[];counts={key:0 for key in DATASETS};vertex_lookup={};triangulation_repairs=[]
 def vertex(point,height,feature_index):
  key=(round(point[0]-xmin,3),round(height,3),round(-(point[1]-ymin),3),feature_index)
  if key not in vertex_lookup:
   vertex_lookup[key]=len(positions);positions.append(key[:3]);identifiers.append(feature_index)
  return vertex_lookup[key]
 for feature_index,feature in enumerate(features):
  footprint=feature['footprint'].simplify(tolerance,preserve_topology=True);base=feature['base_m'];roof=feature['roof_m'];height=roof-base
  record={key:feature[key] for key in ['bag_id','kind','source','source_id','year','use']};record.update(height_m=round(height,3),base_m=round(base,3),roof_m=round(roof,3))
  glb.j['extras']['features'].append(record);counts[feature['source']]+=1
  sidecar.append({'type':'Feature','geometry':mapping(footprint),'properties':{'bag_id':feature['bag_id'],'height_m':height,'source':feature['source']}})
  for polygon in polygons(footprint):
   try:roof_triangles=constrained_delaunay_triangles(polygon).geoms
   except GEOSException:
    triangulation_repairs.append(feature['source_id'])
    try:roof_triangles=constrained_delaunay_triangles(set_precision(polygon,.001)).geoms
    except GEOSException as error:raise RuntimeError(f'Roof triangulation {name} {feature["source_id"]}') from error
   for triangle in roof_triangles:
    points=list(triangle.exterior.coords)[:3]
    # RD XY counterclockwise maps to glTF roof +Y.
    if not triangle.exterior.is_ccw:points.reverse()
    indices.extend(vertex(point,roof,feature_index) for point in points)
   for ring in [polygon.exterior,*polygon.interiors]:
    points=list(ring.coords)
    for a,b in zip(points[:-1],points[1:]):
     ia,ib,ic,id_=[vertex(point,z,feature_index) for point,z in [(a,base),(b,base),(b,roof),(a,roof)]]
     indices.extend([ia,ib,ic,ia,ic,id_])
 if positions:
  position_attribute=glb.attribute(np.array(positions),'VEC3',5126);id_attribute=glb.attribute(np.array(identifiers).reshape(-1,1),'SCALAR',5123)
  index_component=5123 if len(positions)<65536 else 5125;index_array=np.array(indices,dtype='<u2' if index_component==5123 else '<u4');view=glb.data(index_array.tobytes(),34963);index_accessor=len(glb.j['accessors']);glb.j['accessors'].append({'bufferView':view,'componentType':index_component,'count':len(indices),'type':'SCALAR'})
  glb.j['materials']=[{'pbrMetallicRoughness':{'baseColorFactor':[.72,.72,.69,1],'metallicFactor':0,'roughnessFactor':1},'doubleSided':True}]
  glb.j['meshes'][0]['primitives']=[{'attributes':{'POSITION':position_attribute,'_FEATURE_ID_0':id_attribute},'indices':index_accessor,'material':0,'mode':4}]
 else:glb.j['nodes']=[{}];glb.j.pop('meshes')
 directory=OUT/'tiles'/name;directory.mkdir(parents=True,exist_ok=True);path=directory/'buildings.glb';glb.write(path)
 return {'buildings':{'by_source':counts,'count':len(features),'triangles':len(indices)//3,'texture_bytes':0,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'simplification_m':tolerance,'triangulation_precision_repairs':triangulation_repairs}},sidecar

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--workers',type=int,default=4);parser.add_argument('--reextract',action='store_true',help='Redo geometry extraction from archived source payloads, bypassing derived caches; raw sources are reused.');args=parser.parse_args()
 index=json.loads((OUT/'tile-index.json').read_text());boundary=shape(index['boundary_rd']);tile_names=set(index['tiles']);transform=ecef_to_rdnap();source_reports={};merged={}
 for name in DATASETS:
  archive=Archive(name);archive.reextract=args.reextract;cache=archive.root/'extracted-v2.json.gz'
  if cache.exists() and not args.reextract:
   rows=json.loads(gzip.decompress(cache.read_bytes()));print(name,'reuse extracted',len(rows),flush=True)
   for row in rows:row['footprint']=shape(row['footprint'])
  else:
   items=discover(archive);print(name,'deepest source tiles',len(items),flush=True);rows=[]
   with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
    futures={executor.submit(extract,archive,item,transform):item for item in items};errors=[]
    for n,future in enumerate(concurrent.futures.as_completed(futures),1):
     try:rows.extend(future.result())
     except Exception as error:
      errors.append((futures[future][0],repr(error)));print('EXTRACTION ERROR',errors[-1],flush=True)
     if n%50==0:archive.save();print(name,n,'/',len(items),'features',len(rows),flush=True)
   archive.save()
   if errors:raise RuntimeError(f'{name} extraction failures: {errors}')
   cache.write_bytes(gzip.compress(json.dumps([row|{'footprint':mapping(row['footprint'])} for row in rows],separators=(',',':')).encode()))
  for row in rows:
   key=(row['source'],row['identity'])
   if key in merged:
    previous=merged[key];previous['footprint']=union_all([previous['footprint'],row['footprint']],grid_size=.001);previous['base_m']=min(previous['base_m'],row['base_m']);previous['roof_m']=max(previous['roof_m'],row['roof_m']);previous['source_urls']=sorted(set(previous['source_urls']+row['source_urls']))
   else:merged[key]=row
  raw=archive.manifest.read_bytes();source_reports[name]={'manifest':str(archive.manifest),'sha256':hashlib.sha256(raw).hexdigest(),'fragment_count':len(rows),'precision_repair_fragments':sum(row.get('union_precision_m',0)>0 for row in rows)}
 tiles={name:[] for name in tile_names};excluded=0
 for feature in merged.values():
  center=feature['footprint'].centroid;x,y=center.x,center.y;tile=f'x{math.floor(x/1000)*1000}_y{math.floor(y/1000)*1000}'
  if tile not in tiles or not boundary.covers(center):excluded+=1;continue
  tiles[tile].append(feature)
 reports={};footprints=[]
 for name,features in sorted(tiles.items()):
  features.sort(key=lambda f:(f['source'],f['identity']));report,sidecar=write_tile(name,features,.5)
  if report['buildings']['bytes']>1500000:report,sidecar=write_tile(name,features,1.)
  reports[name]=report;footprints.extend(sidecar)
 (OUT/'building-footprints.geojson.gz').write_bytes(gzip.compress(json.dumps({'type':'FeatureCollection','features':footprints},separators=(',',':')).encode()))
 report={'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'method':'Every deepest municipal LOD2 building, storage tank and untextured bridge source; source projected triangles unioned (1mm precision fallback for GEOS near-coincident-edge topology errors) and footprint simplified 0.5m (1m when >1.5MB), extruded between source minimum and maximum NAP elevations. Whole-feature ownership by projected footprint centroid within GM0599. No inferred missing buildings.','sources':source_reports,'excluded_outside_boundary':excluded,'tiles':reports,'totals':{'features':len(footprints),'by_source':{source:sum(r['buildings']['by_source'][source] for r in reports.values()) for source in DATASETS},'bytes':sum(r['buildings']['bytes'] for r in reports.values()),'triangles':sum(r['buildings']['triangles'] for r in reports.values())}}
 (OUT/'buildings-report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report['totals']),flush=True)
if __name__=='__main__':main()
