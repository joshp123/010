#!/usr/bin/env python3
"""Source BGT deck/surface polygons + bounded AHN6 height fits. Requires laspy[lazrs]."""
import json,gzip,hashlib,struct,math
from pathlib import Path
import numpy as np,laspy
from shapely.geometry import Polygon,Point,LineString,box
from shapely.ops import triangulate,unary_union
from pyproj import Transformer
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'source-data/traffic/soetensteeg-bridge';OUT=ROOT/'public/data/supplemental-bridge-surfaces';OUT.mkdir(exist_ok=True)
RD=Transformer.from_crs(4326,28992,always_xy=True).transform;GEO=Transformer.from_crs(28992,4326,always_xy=True).transform;ECEF=Transformer.from_crs(4979,4978,always_xy=True).transform
lon,lat=np.radians([4.49,51.915]);east=np.array([-np.sin(lon),np.cos(lon),0]);up=np.array([np.cos(lat)*np.cos(lon),np.cos(lat)*np.sin(lon),np.sin(lat)]);south=np.array([np.sin(lat)*np.cos(lon),np.sin(lat)*np.sin(lon),-np.cos(lat)]);origin=np.array(ECEF(4.49,51.915,0))
def polygon(feature):
 rings=[[RD(*q) for q in ring] for ring in feature['geometry']['coordinates']];return Polygon(rings[0],rings[1:])
deck=next(f for f in json.loads((SRC/'overbruggingsdeel.json').read_bytes())['features'] if f['properties']['type_overbruggingsdeel']=='dek');boundary=polygon(deck)
p=laspy.read(SRC/'ahn6-bridge-subset.laz');xyz=np.c_[p.x,p.y,p.z];classification=np.asarray(p.classification);anchor=np.array(boundary.centroid.coords[0]);surfaces=[];meshes=[]
def design(xy):
 q=xy-anchor;return np.c_[np.ones(len(q)),q[:,0],q[:,1],q[:,0]**2,q[:,0]*q[:,1],q[:,1]**2]
parts=[f for f in json.loads((SRC/'wegdeel.json').read_bytes())['features'] if f['properties']['relatieve_hoogteligging']==1]
remainder=boundary.difference(unary_union([polygon(f) for f in parts]))
parts.append({'properties':{'relatieve_hoogteligging':1,'functie':'unclassified deck edge','lokaal_id':deck['properties']['lokaal_id']},'geometry':deck['geometry']})
for feature in parts:
 props=feature['properties']
 if props['relatieve_hoogteligging']!=1:continue
 edge=props['functie']=='unclassified deck edge'
 area=remainder if edge else polygon(feature).intersection(boundary)
 if area.is_empty:continue
 selected=np.array([(boundary.buffer(-.5) if edge else area.buffer(-.2)).covers(Point(x,y)) for x,y in xyz[:,:2]])&(classification==26)
 points=xyz[selected];matrix=design(points[:,:2]);mask=np.ones(len(points),dtype=bool)
 for iteration in range(5):
  coeff=np.linalg.lstsq(matrix[mask],points[mask,2],rcond=None)[0];residual=points[:,2]-matrix@coeff;mask=np.abs(residual)<.08
 rmse=float(np.sqrt(np.mean(residual[mask]**2)));assert mask.sum()>50 and rmse<.05
 kind='paving' if edge else 'road' if props['functie']=='rijbaan lokale weg' else 'footway';vertices=[]
 xmin,ymin,xmax,ymax=area.bounds
 for x in np.arange(math.floor(xmin),xmax,1):
  for y in np.arange(math.floor(ymin),ymax,1):
   clipped=area.intersection(box(x,y,x+1,y+1))
   for triangle in triangulate(clipped):
    if not clipped.covers(triangle):continue
    coords=list(triangle.exterior.coords)[:3]
    if not triangle.exterior.is_ccw:coords.reverse()
    for xx,yy in coords:
     height=float((design(np.array([[xx,yy]]))@coeff)[0]);lo,la=GEO(xx,yy);local=np.array(ECEF(lo,la,height))-origin;vertices.append([local@east,local@up,local@south])
 surfaces.append({'sourceId':props['lokaal_id'],'kind':kind,'areaSquareMetres':area.area,'selectedAHNPoints':len(points),'inlierPoints':int(mask.sum()),'heightModel':'robust quadratic, independent surface; residual cutoff0.08m','anchorRD':anchor.tolist(),'coefficients':coeff.tolist(),'rmseMetres':rmse,'heightRangeMetres':[float(points[mask,2].min()),float(points[mask,2].max())]});meshes.append((kind,np.asarray(vertices,dtype='<f4')))
assert abs(sum(s['areaSquareMetres'] for s in surfaces)-boundary.area)<.1
# Local ENU glTF, matching existing prepared bridge surfaces.
doc={'asset':{'version':'2.0','generator':'010 BGT-AHN missing bridge reconstruction'},'scene':0,'scenes':[{'nodes':[]}],'nodes':[],'meshes':[],'accessors':[],'bufferViews':[],'buffers':[{'byteLength':0}]};chunks=[];offset=0
for kind,vertices in meshes:
 chunks.append(vertices.tobytes());doc['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':vertices.nbytes,'target':34962});doc['accessors'].append({'bufferView':len(doc['bufferViews'])-1,'componentType':5126,'count':len(vertices),'type':'VEC3','min':vertices.min(axis=0).tolist(),'max':vertices.max(axis=0).tolist()});doc['meshes'].append({'name':kind,'extras':{'surfaceKind':kind,'sourceStage':'current BGT footprint / AHN6 measured deck','bridgeId':deck['properties']['lokaal_id']},'primitives':[{'attributes':{'POSITION':len(doc['accessors'])-1},'mode':4}]});doc['nodes'].append({'mesh':len(doc['meshes'])-1});doc['scenes'][0]['nodes'].append(len(doc['nodes'])-1);offset+=vertices.nbytes
binary=b''.join(chunks);doc['buffers'][0]['byteLength']=len(binary);meta=json.dumps(doc,separators=(',',':')).encode();meta+=b' '*(-len(meta)%4);glb=struct.pack('<4sII',b'glTF',2,28+len(meta)+len(binary))+struct.pack('<I4s',len(meta),b'JSON')+meta+struct.pack('<I4s',len(binary),b'BIN\0')+binary;(OUT/'soetensteeg.glb').write_bytes(glb)
allpoints=np.concatenate([v for _,v in meshes]);low=allpoints.min(axis=0);high=allpoints.max(axis=0);centre=(low+high)/2;half=(high-low)/2;bounds=[float(centre[0]),float(-centre[2]),float(centre[1]),float(half[0]),0,0,0,float(half[2]),0,0,0,float(half[1])];matrix=np.eye(4);matrix[:3,0]=east;matrix[:3,1]=-south;matrix[:3,2]=up;matrix[:3,3]=origin
tiles={'asset':{'version':'1.1'},'geometricError':0,'root':{'transform':matrix.T.ravel().tolist(),'boundingVolume':{'box':bounds},'geometricError':0,'content':{'uri':'soetensteeg.glb'}}};(OUT/'tileset.json').write_text(json.dumps(tiles,separators=(',',':'))+'\n')
# Linear densification preserves every source vertex and plan line; it adds
# samples so road elevation can follow the measured deck between bank endpoints.
roads=json.loads(gzip.decompress((ROOT/'source-data/traffic/nwb-roads.geojson.gz').read_bytes()))['features'];profiles=[]
for feature in roads:
 coords=feature['geometry']['coordinates'][0];line=LineString([RD(*q) for q in coords])
 if not line.intersects(boundary):continue
 dense=[coords[0]]
 for first,last in zip(coords,coords[1:]):
  length=math.dist(RD(*first),RD(*last));count=max(1,math.ceil(length/2))
  dense.extend([[first[j]+(last[j]-first[j])*i/count for j in range(2)] for i in range(1,count+1)])
 profiles.append({'roadId':feature['properties']['wvk_id'],'expectedCoordinates':[[round(v,7) for v in xy] for xy in coords],'coordinates':dense})
(ROOT/'public/data/traffic/surface-profiles.json').write_text(json.dumps({'version':1,'source':'BGT Soetensteeg deck + AHN6 surface; original NWB plan unchanged','roads':profiles},indent=2)+'\n')
manifest={'deckSource':deck['properties'],'surfaces':surfaces,'sourceHashes':{n:hashlib.sha256((SRC/n).read_bytes()).hexdigest() for n in ['overbruggingsdeel.json','wegdeel.json','ahn6-bridge-subset.laz','tileset.json.gz','textured-bridge-2099-433.json.gz']},'triangles':sum(len(v)//3 for _,v in meshes),'bytes':len(glb),'profileRoads':[p['roadId'] for p in profiles],'limitations':'Measured top surfaces only; no invented arches, rails or underside. AHN height is NAP numerical height in existing project Earth convention. Original source network plan/access unchanged.'};(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');(SRC/'build-review.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps({'surfaces':surfaces,'profiles':manifest['profileRoads'],'triangles':manifest['triangles']}))
# Review image: original dated aerial with labelled shadow-only gamma, and
# source geometry/height map. This is evidence, not a browser acceptance image.
meta=json.loads((SRC/'ortho2026.source.json').read_bytes());xmin,ymin,xmax,ymax=meta['boundsRD']
def screen(x,y):return (x-xmin)/(xmax-xmin)*600,(ymax-y)/(ymax-ymin)*600
photo=Image.open(SRC/'ortho2026.jpg').convert('RGB').point([round(255*(v/255)**.45) for v in range(256)]*3);review=Image.new('RGB',(1200,650),'#f1f0e6');review.paste(photo,(0,50));paint=ImageDraw.Draw(review);font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',14)
paint.text((10,15),'2026 OrthoHR · gamma0.45 for shadow inspection',font=font,fill='#293c37');paint.text((610,15),'BGT deck / road / footways + measured AHN6 top surface',font=font,fill='#293c37')
for surface,feature in zip(surfaces,parts):
 area=remainder if feature['properties']['functie']=='unclassified deck edge' else polygon(feature).intersection(boundary);col={'road':'#8d9694','footway':'#c9c4b2','paving':'#b5b5a7'}[surface['kind']]
 for poly in area.geoms if hasattr(area,'geoms') else [area]:
  if poly.geom_type=='Polygon' and not poly.is_empty:paint.polygon([(600+screen(x,y)[0],50+screen(x,y)[1]) for x,y in poly.exterior.coords],fill=col,outline='#525e57')
for profile in profiles:
 line=[screen(*RD(*q)) for q in profile['coordinates']];paint.line([(x+600,y+50) for x,y in line],fill='#276ca0',width=3)
x,y=screen(*RD(4.483014458,51.919168681));paint.ellipse((x+595,y+45,x+605,y+55),fill='#b42463');paint.text((x+612,y+50),'reported bicycle45',font=font,fill='#293c37')
review.save(ROOT/'docs/images/traffic-soetensteeg-source.png')
