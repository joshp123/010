"""Whole-city BRT classes and sampled AHN terrain.
Written by AI on 2026-10-26 by model GPT-6.1 Sol.
Raw responses and explicit classification remain replaceable independently.
"""
import argparse, concurrent.futures, datetime, gzip, hashlib, io, json, struct, threading, time
from collections import Counter
from pathlib import Path
from urllib.parse import urlencode
import numpy as np
import requests
from PIL import Image, ImageDraw
from shapely import make_valid
from shapely.geometry import shape, box
from shapely.strtree import STRtree

ROOT=Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
SCENE=ROOT/'scene/overview-v1'
DATE='2026-10-26'
CRS='http://www.opengis.net/def/crs/EPSG/0/28992'
LOCK=threading.Lock()
LEGEND=['unknown','carriageway','cycle path','footpath, pavement','parking','tram track bed','grass, planted verge','shrubs, hedges','water','unpaved, sand, bare','paved yard or square','building footprint','bridge deck','quay wall, civil structure','train or metro track bed','traffic island, crossing','rail yard, ballast']
PALETTE=np.array([[190,186,174],[90,93,100],[170,67,55],[211,191,158],[117,120,133],[110,97,89],[115,155,82],[62,113,65],[66,140,175],[180,157,116],[172,158,139],[202,197,187],[167,152,120],[100,85,77],[102,92,113],[203,170,90],[132,124,110]],dtype=np.uint8)


def fetch(dataset,name,url):
 folder=ROOT/'sources'/dataset/DATE; path=folder/name
 if path.exists():return path.read_bytes()
 for attempt in range(5):
  try:
   r=requests.get(url,timeout=150);r.raise_for_status();data=r.content;break
  except requests.RequestException:
   if attempt==4:raise
   time.sleep(2**attempt)
 path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
 with LOCK:
  mp=folder/'manifest.json'
  manifest=json.loads(mp.read_text()) if mp.exists() else {'dataset':dataset,'license':'CC-BY-4.0' if dataset=='overview-brt' else 'CC0-1.0','credit':'Kadaster / PDOK — BRT TOP10NL' if dataset=='overview-brt' else 'Actueel Hoogtebestand Nederland / PDOK','files':{}}
  manifest['files'][name]={'url':url,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'fetched_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
  temp=mp.with_suffix('.tmp');temp.write_text(json.dumps(manifest,indent=2));temp.replace(mp)
 return data


def read_collection(collection,bounds):
 params={'bbox':','.join(map(str,bounds)),'bbox-crs':CRS,'crs':CRS,'limit':1000,'f':'json'}
 url=f'https://api.pdok.nl/kadaster/brt-top10nl/ogc/v1/collections/{collection}/items?'+urlencode(params)
 records=[];page=0
 while url:
  j=json.loads(fetch('overview-brt',f'{collection}/page{page:04}.json',url))
  if 'features' not in j:raise ValueError(j)
  for f in j['features']:
   if not f.get('geometry'):continue
   p=f['properties'];g=make_valid(shape(f['geometry']))
   if g.is_empty:continue
   records.append((collection,p,g))
  print(collection,len(records),flush=True)
  url=next((v['href'] for v in j.get('links',[]) if v['rel']=='next'),None);page+=1
 return records


def transport_exclusion(properties):
 if 'veerverbinding' in str(properties.get('typeweg') or '').split('|'):return 'ferry route has no physical ground surface'
 physical_tags=set(str(properties.get('fysiekvoorkomen') or '').split('|'))
 if physical_tags & {'in tunnel','overkluisd'}:return 'tunnel or covered transport is not an exposed surface'
 if (properties.get('hoogteniveau') or 0)<0:return 'underground relative level'
 if properties.get('status') not in (None,'in gebruik'):return 'not in use'
 return None


def classify(collection,p):
 if collection=='building_footprint':return 12 if p.get('source')=='bridges' else (13 if p.get('source')=='tanks' else 11)
 if collection=='waterdeel_vlak':return 8
 if collection=='terrein_vlak':
  land=p.get('typelandgebruik','')
  if land in ('grasland','bouwland','boomgaard','fruitkwekerij','boomkwekerij','heide','akkerland'):return 6
  if land in ('bos: loofbos','bos: naaldbos','bos: gemengd bos','populieren','griend'):return 7
  if 'bos' in land:return 7
  if land in ('zand','duin','strand','onverhard'):return 9
  if land=='spoorbaanlichaam':return 16
  if land in ('basaltblokken, steenglooiing','aanlegsteiger'):return 13
  if land in ('dodenakker','fruitteelt'):return 6
  return 0
 if collection in ('wegdeel_vlak','wegdeel_lijn'):
  if transport_exclusion(p):return 0
  use=p.get('hoofdverkeersgebruik','')
  if 'fietsers' in use:return 2
  if 'voetgangers' in use:return 3
  if 'parkeer' in p.get('typeweg',''):return 4
  if p.get('verhardingstype')=='onverhard':return 9
  return 1
 return 0


def draw_geometry(image,g,x,y,value):
 d=ImageDraw.Draw(image)
 def points(coords):return [(a-x-.5,y+1000-b-.5) for a,b,*_ in coords]
 if g.geom_type=='Polygon':
  if not g.interiors:d.polygon(points(g.exterior.coords),fill=value)
  else:
   mask=Image.new('1',image.size);md=ImageDraw.Draw(mask);md.polygon(points(g.exterior.coords),fill=1)
   for ring in g.interiors:md.polygon(points(ring.coords),fill=0)
   image.paste(value,(0,0),mask)
 elif hasattr(g,'geoms'):
  for part in g.geoms:draw_geometry(image,part,x,y,value)


def write_ground(path,x,y,classes,municipal_mask):
 # A 25 m lattice samples actual AHN DTM cells; no nearest-neighbour filling of water/nodata.
 # WCS coordinates describe pixel edges. +/-12.5 makes lattice nodes fall at tile edges.
 p={'SERVICE':'WCS','VERSION':'1.0.0','REQUEST':'GetCoverage','COVERAGE':'dtm_05m','CRS':'EPSG:28992','BBOX':f'{x-12.5},{y-12.5},{x+1012.5},{y+1012.5}','WIDTH':41,'HEIGHT':41,'FORMAT':'image/tiff'}
 url='https://service.pdok.nl/rws/ahn/wcs/v1_0?'+urlencode(p)
 raw=fetch('overview-ahn',f'x{x}_y{y}.tif',url)
 heights=np.array(Image.open(io.BytesIO(raw)),dtype=float)
 if heights.shape!=(41,41):raise ValueError(heights.shape)
 valid=np.isfinite(heights)&(np.abs(heights)<1e6)
 rows,cols=np.indices((41,41));vertices=np.column_stack([cols.ravel()*25,heights.ravel(),-(1000-rows.ravel()*25)])
 a=np.arange(41*41).reshape(41,41)[:-1,:-1].ravel();tris=np.concatenate([np.column_stack([a,a+1,a+41]),np.column_stack([a+1,a+42,a+41])])
 keep=valid.ravel()[tris].all(1);tris=tris[keep]
 # Winding must face upwards in glTF's east/up/south coordinates.
 tris=tris[:,[0,2,1]]
 positions=vertices[tris].reshape(-1,3).astype('<f4')
 centre=vertices[tris].mean(1)
 cc=np.clip(centre[:,0].astype(int),0,999);rr=np.clip((1000+centre[:,2]).astype(int),0,999)
 surface_classes=np.repeat(classes[rr,cc],3).astype('u1')
 binary=b'';views=[]
 for data in [positions.tobytes(),surface_classes.tobytes()]:
  views.append({'buffer':0,'byteOffset':len(binary),'byteLength':len(data),'target':34962});binary+=data+b'\0'*((-len(data))%4)
 stat={'triangles':len(tris),'valid_height_nodes':int(valid.sum()),'height_nodes':1681,'missing_height_nodes':int((~valid).sum()),'omitted_triangles':3200-len(tris),'sample_spacing_m':25,'nap_range_m':[float(heights[valid].min()),float(heights[valid].max())] if valid.any() else None}
 doc={'asset':{'version':'2.0','generator':'010 overview AHN terrain'},'scene':0,'scenes':[{'nodes':[0]}],'nodes':[{'mesh':0}], 'meshes':[{'primitives':[{'attributes':{'POSITION':0,'_CLASS':1},'mode':4,'material':0}]}], 'materials':[{'doubleSided':True,'pbrMetallicRoughness':{'metallicFactor':0,'roughnessFactor':1}}], 'buffers':[{'byteLength':len(binary)}],'bufferViews':views, 'accessors':[{'bufferView':0,'componentType':5126,'count':len(positions),'type':'VEC3',**({'min':positions.min(0).tolist(),'max':positions.max(0).tolist()} if len(positions) else {})},{'bufferView':1,'componentType':5121,'count':len(surface_classes),'type':'SCALAR'}], 'extras':{'source':'PDOK AHN dtm_05m; 25 m point sampling','vertical_datum':'NAP','nodata_policy':'Omit triangles touching any nodata node. Water is classed in raster but AHN water holes remain unmodelled; no invented elevation.',**stat}}
 if not len(positions):
  doc['nodes']=[{}]
  for key in ['meshes','materials','buffers','bufferViews','accessors']:doc.pop(key,None)
 coverage=Image.new('1',(1000,1000));drawing=ImageDraw.Draw(coverage)
 for triangle in vertices[tris]:drawing.polygon([(v[0],1000+v[2]) for v in triangle],fill=1)
 covered=np.array(coverage,dtype=bool)
 for kind,mask in [('municipal',municipal_mask),('water',municipal_mask&(classes==8)),('known_land',municipal_mask&~np.isin(classes,[0,8])),('unknown_surface',municipal_mask&(classes==0))]:
  stat[kind+'_area_m2']=int(mask.sum());stat[kind+'_ground_uncovered_m2']=int((mask&~covered).sum())
 doc['extras'].update(stat)
 jb=json.dumps(doc,separators=(',',':')).encode();jb+=b' '*((-len(jb))%4)
 path.write_bytes(struct.pack('<4sII',b'glTF',2,28+len(jb)+len(binary))+struct.pack('<I4s',len(jb),b'JSON')+jb+struct.pack('<I4s',len(binary),b'BIN\0')+binary)
 return stat


def main():
 parser=argparse.ArgumentParser();parser.add_argument('--classes-only',action='store_true');args=parser.parse_args()
 index=json.loads((SCENE/'tile-index.json').read_text());tiles=index['tiles']
 fetch('overview-ahn','capabilities.xml','https://service.pdok.nl/rws/ahn/wcs/v1_0?service=WCS&request=GetCapabilities')
 bounds=[min(v['bounds_rd'][0] for v in tiles.values()),min(v['bounds_rd'][1] for v in tiles.values()),max(v['bounds_rd'][2] for v in tiles.values()),max(v['bounds_rd'][3] for v in tiles.values())]
 collections=['terrein_vlak','waterdeel_vlak','wegdeel_vlak','wegdeel_lijn','spoorbaandeel_lijn']
 with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:records=[r for result in pool.map(lambda c:read_collection(c,bounds),collections) for r in result]
 footprints=SCENE/'building-footprints.geojson.gz'
 if footprints.exists():
  for feature in json.loads(gzip.decompress(footprints.read_bytes()))['features']:
   geometry=make_valid(shape(feature['geometry']))
   if not geometry.is_empty:records.append(('building_footprint',feature['properties'],geometry))
 municipality=shape(index['boundary_rd'])
 tree=STRtree([r[2] for r in records]);attrs=Counter((c,p.get('typelandgebruik'),classify(c,p)) for c,p,g in records)
 report={'source_strategy':'BRT TOP10NL full source polygons for whole municipality overview, rather than detailed BGT historical features/3D payloads. No geometry simplification before 1 m rasterisation. Coarse BRT classes do not distinguish every BGT semantic (e.g. grass verges/paved urban yards).','bounds_rd':bounds,'class_legend':dict(enumerate(LEGEND)),'source_counts':dict(Counter(r[0] for r in records)),'transport_exclusions':dict(Counter(c+': '+transport_exclusion(p) for c,p,g in records if c in ('wegdeel_vlak','wegdeel_lijn','spoorbaandeel_lijn') and transport_exclusion(p))),'attribute_mapping_counts':[[list(k),v] for k,v in attrs.items()],'building_footprints':{'file':str(footprints),'sha256':hashlib.sha256(footprints.read_bytes()).hexdigest()} if footprints.exists() else None,'classification_limit':'BRT overig and bebouwd gebied remain class0 because no physical paving can be established; no fabricated generic land cover.', 'rail_method':'BRT source centreline rasterised at one-pixel width. G bit 1 tram, bit 2 train/metro/sneltram; centreline coverage at 1 m, not rail-head gauge. Ferry links never become ground. Physical `in tunnel`/`overkluisd`, underground and out-of-use transport excluded.','terrain_method':'PDOK AHN dtm_05m WCS sampled every 25 m at exact shared tile-edge lattice. Triangle touching nodata omitted, no height filling. Land and water nodata separately counted.','tiles':{}}
 report['path_width_method']='Road polygons retain supplied geometry. Source road/path centrelines use illustrative 2 m/1 m half-width buffers for visibility at overview resolution; these are not surveyed paving widths.'
 def build(item):
  name,entry=item;x,y=entry['bounds_rd'][:2];directory=SCENE/'tiles'/name;directory.mkdir(parents=True,exist_ok=True)
  selected=[records[i] for i in tree.query(box(x-10,y-10,x+1010,y+1010))]
  image=Image.new('L',(1000,1000));bits=Image.new('L',(1000,1000));rail_counts=Counter()
  priorities={'terrein_vlak':0,'waterdeel_vlak':1,'wegdeel_vlak':2,'wegdeel_lijn':3,'spoorbaandeel_lijn':4,'building_footprint':5}
  for c,p,g in sorted(selected,key=lambda r:(priorities[r[0]],r[1].get('hoogteniveau') or 0)):
   if c=='spoorbaandeel_lijn':continue
   if c.startswith('wegdeel') and transport_exclusion(p):continue
   cls=classify(c,p)
   if c=='wegdeel_lijn':g=g.buffer(1 if cls in (2,3) else 2)
   if cls:draw_geometry(image,g,x,y,cls)
  bitarray=np.zeros((1000,1000),dtype='u1')
  for c,p,g in selected:
   if c!='spoorbaandeel_lijn' or transport_exclusion(p):continue
   rail=p.get('typespoorbaan');bit=1 if rail=='tram' else 2
   mask=Image.new('L',(1000,1000));draw_geometry(mask,g.buffer(.65,cap_style='flat'),x,y,1);bitarray[np.array(mask)>0]|=bit;rail_counts[str(rail)]+=1
  classes=np.array(image);rgba=np.zeros((1000,1000,4),dtype='u1');rgba[:,:,0]=classes;rgba[:,:,1]=bitarray;rgba[:,:,3]=255;Image.fromarray(rgba).save(directory/'classes.png')
  maskimage=Image.new('L',(1000,1000));draw_geometry(maskimage,municipality,x,y,1);municipal_mask=np.array(maskimage,dtype=bool)
  stat={'municipal_area_m2':int(municipal_mask.sum()),'municipal_class_pixels':{str(i):int(n) for i,n in enumerate(np.bincount(classes[municipal_mask],minlength=17))},'class_pixels':{str(i):int(n) for i,n in enumerate(np.bincount(classes.ravel(),minlength=17))},'rail_features':dict(rail_counts),'rail_pixels':int((bitarray>0).sum())}
  if not args.classes_only:stat['ground']=write_ground(directory/'ground.glb',x,y,classes,municipal_mask)
  stat['files']={f:{'bytes':(directory/f).stat().st_size,'sha256':hashlib.sha256((directory/f).read_bytes()).hexdigest()} for f in ['classes.png','ground.glb'] if (directory/f).exists()}
  print(name,stat.get('ground',{}).get('triangles'),flush=True)
  return name,stat
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
  for name,stat in pool.map(build,tiles.items()):report['tiles'][name]=stat
 report['municipal_class_pixels']={str(i):sum(record['municipal_class_pixels'][str(i)] for record in report['tiles'].values()) for i in range(17)}
 report['municipal_area_m2']=sum(report['municipal_class_pixels'].values())
 report['municipal_unknown_fraction']=report['municipal_class_pixels']['0']/report['municipal_area_m2']
 if not args.classes_only:
  report['terrain_coverage_totals']={key:sum(record['ground'][key] for record in report['tiles'].values()) for key in ['municipal_area_m2','municipal_ground_uncovered_m2','water_area_m2','water_ground_uncovered_m2','known_land_area_m2','known_land_ground_uncovered_m2','unknown_surface_area_m2','unknown_surface_ground_uncovered_m2']}
 for dataset in ['overview-brt','overview-ahn']:
  p=ROOT/'sources'/dataset/DATE/'manifest.json'
  if p.exists():report.setdefault('sources',{})[dataset]={'manifest':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
 (SCENE/'surfaces-report.json').write_text(json.dumps(report,indent=2))
 print('COMPLETE',len(report['tiles']),flush=True)

if __name__=='__main__':main()
