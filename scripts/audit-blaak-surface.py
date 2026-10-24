#!/usr/bin/env python3
"""Exact native BGT triangles against captured NWB vehicle positions; no geometry edits."""
import importlib.util,gzip,json,hashlib,math,csv,io
from pathlib import Path
import numpy as np
from pyproj import Transformer
from shapely.geometry import Polygon,Point,LineString,box
from shapely.ops import unary_union
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'source-data/traffic/blaak-surface'
spec=importlib.util.spec_from_file_location('native',ROOT/'scripts/prepare-building-appearance.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
P=Transformer.from_crs(4979,4978,always_xy=True).transform
lon,lat=4.49,51.915;origin=np.array(P(lon,lat,0));lo,la=np.radians([lon,lat]);basis=np.array([[-np.sin(lo),np.cos(lo),0],[np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)],[np.sin(la)*np.cos(lo),np.sin(la)*np.sin(lo),-np.cos(la)]])
def local(lon,lat):return (np.array(P(lon,lat,0))-origin)@basis.T
raw=gzip.decompress((OUT/'33584-6932.b3dm.gz').read_bytes());features={}
for doc,binary,batch,feature in m.b3dm_parts(raw):
 yz=np.array([[1,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1]]);shift=np.eye(4);shift[:3,3]=feature['RTC_CENTER']
 def visit(i,parent):
  node=doc['nodes'][i];matrix=parent@np.array(node.get('matrix',np.eye(4).T.ravel())).reshape(4,4).T
  if 'mesh' in node:
   for p in doc['meshes'][node['mesh']]['primitives']:
    v=m.accessor(doc,binary,p['attributes']['POSITION']);idx=m.accessor(doc,binary,p['indices'])[:,0].reshape(-1,3);ids=m.accessor(doc,binary,p['attributes']['_BATCHID'])[:,0]
    world=(np.c_[v,np.ones(len(v))]@(shift@yz@matrix).T)[:,:3];points=(world-origin)@basis.T
    for bid in np.unique(ids[idx[:,0]]):
     attrs=batch['attributes'][int(bid)];key=str(attrs.get('DGDT_ID',''))
     triangles=points[idx[ids[idx[:,0]]==bid]]
     triangles=triangles[(triangles[:,:,1]>-30).all(axis=1)]
     polygons=[Polygon(t[:,[0,2]]) for t in triangles if Polygon(t[:,[0,2]]).area>1e-7]
     if polygons:features[key]={'attributes':attrs,'geometry':unary_union(polygons)}
  for child in node.get('children',[]):visit(child,matrix)
 for root in doc['scenes'][doc.get('scene',0)]['nodes']:visit(root,np.eye(4))
captures=json.loads((OUT/'native-capture.json').read_bytes());report=[]
for sample in captures:
 base=sample['verticalSurfaces'][0]['point'];offset=sample['laneOffset'];centre=[base[0]-offset[0],base[2]-offset[1]]
 entry={'vehicleId':sample['vehicleId'],'mode':sample['mode'],'roadId':sample['roadId'],'lanePosition':[base[0],base[2]],'centrelinePosition':centre,'sourcePosition':sample['sourcePosition']}
 for key,pos in [('lane',[base[0],base[2]]),('centreline',centre)]:
  point=Point(pos);entry[key+'Surfaces']=[{'id':id,'function':f['attributes'].get('FUNCTIE'),'boundaryDistanceMetres':round(point.distance(f['geometry'].boundary),3)} for id,f in features.items() if f['geometry'].covers(point)]
 report.append(entry)
nwb=json.loads(gzip.decompress((ROOT/'source-data/traffic/nwb-roads.geojson.gz').read_bytes()));road=next(f for f in nwb['features'] if f['properties']['wvk_id']==185274103)
line=[local(*xy)[[0,2]] for xy in road['geometry']['coordinates'][0]]
img=Image.new('RGB',(1000,900),'#f1f0e6');d=ImageDraw.Draw(img);font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',15)
clip=box(-430,-490,-395,-450)
def screen(p):return 80+(p[0]+430)*19,100+(p[1]+490)*19
for id,f in features.items():
 g=f['geometry'].intersection(clip)
 for poly in g.geoms if hasattr(g,'geoms') else [g]:
  if poly.geom_type!='Polygon' or poly.is_empty:continue
  fn=f['attributes'].get('FUNCTIE','');color='#b78770' if fn=='fietspad' else '#c9cbb9' if fn=='verkeerseiland' else '#a3acaa' if fn=='rijbaan lokale weg' else '#e0d9c8'
  d.polygon([screen(p) for p in poly.exterior.coords],fill=color,outline='#7d847a')
  if id in ['16524553','14702898','14198208']:
   pt=poly.representative_point();d.text(screen([pt.x,pt.y]),id,fill='#26342e',font=font)
d.line([screen(p) for p in line],fill='#366aa0',width=3)
for s in report:
 x,y=screen(s['lanePosition']);cx,cy=screen(s['centrelinePosition']);d.line([(x,y),(cx,cy)],fill='#6a1a40',width=2);d.ellipse((x-5,y-5,x+5,y+5),fill='#6a1a40');d.ellipse((cx-3,cy-3,cx+3,cy+3),fill='#366aa0');d.text((x-56,y-8),str(s['vehicleId']),fill='#6a1a40',font=font)
d.text((25,15),'Blaak · exact native BGT polygons / blue NWB centreline / magenta captured lane points',fill='#293c37',font=font)
d.text((760,100),'north up',fill='#293c37',font=font)
img.save(ROOT/'docs/images/traffic-blaak-surface.png')
access=next(row for row in csv.DictReader(io.StringIO(gzip.decompress((ROOT/'source-data/traffic/wkd-cycling-access.csv.gz').read_bytes()).decode()),delimiter=';') if row['WVK_ID']=='185274103')
(OUT/'audit.json').write_text(json.dumps({'wkdAccess':access,'sourceSha256':hashlib.sha256(raw).hexdigest(),'sourceRoad':road,'samples':report},indent=2)+'\n')
print(json.dumps(report,indent=2))
# Independent dated imagery: project original source coordinates directly to the
# retained WMS grid. Lane offsets use the local ECEF frame, converted back to RD.
if (OUT/'ortho2025.jpg').exists():
 meta=json.loads((OUT/'ortho2025.json').read_bytes());rd=Transformer.from_crs(4326,28992,always_xy=True).transform;geo=Transformer.from_crs(4978,4979,always_xy=True).transform
 photo=Image.open(OUT/'ortho2025.jpg').convert('RGB');draw=ImageDraw.Draw(photo);xmin,ymin,xmax,ymax=meta['boundsRD']
 def pixel(lon,lat):
  x,y=rd(lon,lat);return (x-xmin)/(xmax-xmin)*photo.width,(ymax-y)/(ymax-ymin)*photo.height
 draw.line([pixel(*xy) for xy in road['geometry']['coordinates'][0]],fill='#2879ff',width=2)
 for sample in captures:
  point=sample['verticalSurfaces'][0]['point'];world=origin+np.asarray(point)@basis;lon,lat,_=geo(*world);x,y=pixel(lon,lat)
  draw.ellipse((x-4,y-4,x+4,y+4),fill='#f00080');draw.text((x+6,y),str(sample['vehicleId']),fill='#f00080',font=font)
 photo.save(ROOT/'docs/images/traffic-blaak-ortho2025.png')
# A bounded derived candidate, deliberately NOT runtime input. Preserve source
# coordinates separately. Both directions need 1.15m lane separation plus .95m
# half-car width inside the surveyed carriageway. This is a geometric clearance
# interpretation, not a new surveyed centreline or confirmation of current BGT.
from shapely.ops import nearest_points
carriageway=features['14702898']['geometry'];safe=carriageway.buffer(-2.35)
if safe.is_empty:raise ValueError('No surveyed carriageway room for two car lanes')
original=np.array(line);candidate=[]
source_line=LineString(original)
for distance in np.linspace(0,source_line.length,math.ceil(source_line.length/.5)+1):
 point=source_line.interpolate(distance);target=nearest_points(point,safe)[1];candidate.append([target.x,target.y])
if LineString(candidate).difference(carriageway.buffer(-2.2)).length>1e-5:raise ValueError('Candidate interpolation leaves carriageway clearance; no candidate generated')
node_corrections={road['properties']['jte_id_beg']:candidate[0],road['properties']['jte_id_end']:candidate[-1]}
adjacent=[]
for f in nwb['features']:
 p=f['properties'];changes=[]
 for field,start in [('jte_id_beg',True),('jte_id_end',False)]:
  if p[field] in node_corrections:
   xy=f['geometry']['coordinates'][0 if start else -1][0 if start else -1];before=local(*xy)[[0,2]];after=node_corrections[p[field]]
   changes.append({'endpoint':'start' if start else 'end','junction':p[field],'before':before.tolist(),'candidate':after,'shiftMetres':float(np.linalg.norm(np.asarray(after)-before))})
 if changes:adjacent.append({'roadId':p['wvk_id'],'changes':changes})
(OUT/'corridor-candidate.json').write_text(json.dumps({'status':'review only; NOT loaded by runtime','method':'Sample NWB every <=0.5m, nearest points on native BGT carriageway eroded 2.35m; whole interpolated candidate must remain inside 2.2m erosion; original NWB vertices retained separately','sourceRoad':185274103,'surfaceId':'14702898','originalLocalXZ':original.tolist(),'candidateLocalXZ':candidate,'affectedIncidentMotorEdges':adjacent,'requiredBeforeActivation':['Verify current BGT carriageway boundaries against 2025 image and construction','Reconcile all affected incident edge geometry using the same corrected junction position','Check entire vehicle footprints along interpolated turns and both lane directions','Keep bicycle geometry independent; no motor adjustment copied to cyclists']},indent=2)+'\n')
d.line([screen(p) for p in candidate],fill='#087a43',width=4);d.text((25,42),'Green = derived corridor candidate only; junction/turn reconciliation required before use',fill='#087a43',font=font)
img.save(ROOT/'docs/images/traffic-blaak-corridor-candidate.png')
