#!/usr/bin/env python3
"""Bounded source-reviewed motor geometry; original NWB/WKD never overwritten."""
import contextlib,io,runpy,json,hashlib,math
from pathlib import Path
import numpy as np
from shapely.geometry import Polygon,LineString,Point,box
from shapely.ops import nearest_points
from pyproj import Transformer
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'source-data/traffic/blaak-surface'
with contextlib.redirect_stdout(io.StringIO()):a=runpy.run_path(str(ROOT/'scripts/audit-blaak-surface.py'))
current=json.loads((OUT/'current-wegdeel.json').read_bytes());id='G0599.170ade244cdb72d73e050210a7e24429'
f=next(f for f in current['features'] if f['properties']['lokaal_id']==id)
rings=[[a['local'](*xy)[[0,2]] for xy in ring] for ring in f['geometry']['coordinates']];polygon=Polygon(rings[0],rings[1:]);corridor=polygon.intersection(a['carriageway']);safe=corridor.buffer(-2.6)
source=LineString(a['original']);candidate=[]
for distance in np.linspace(0,source.length,math.ceil(source.length/.5)+1):
 point=nearest_points(source.interpolate(distance),safe)[1];candidate.append([point.x,point.y])
assert LineString(candidate).difference(corridor.buffer(-2.2)).length<1e-5
geo=Transformer.from_crs(4978,4979,always_xy=True).transform
def coordinates(xz):
 lon,lat,_=geo(*(a['origin']+np.array([xz[0],0,xz[1]])@a['basis']));return [lon,lat]
def polygons(raw):
 for feature in raw['features']:
  if feature['properties']['functie']!='rijbaan lokale weg':continue
  rings=[[a['local'](*xy)[[0,2]] for xy in ring] for ring in feature['geometry']['coordinates']]
  yield Polygon(rings[0],rings[1:])
from shapely.ops import unary_union
current_roads=unary_union(list(polygons(current)));native_roads=unary_union([f['geometry'] for f in a['features'].values() if f['attributes'].get('FUNCTIE')=='rijbaan lokale weg']);drivable=current_roads.intersection(native_roads)

endpoint=coordinates(candidate[-1]);patches=[]
for fid in [185274103,185274085,600909887]:
 original=next(f for f in a['nwb']['features'] if f['properties']['wvk_id']==fid);p=original['properties'];coords=original['geometry']['coordinates'][0];new=[list(xy) for xy in coords]
 if fid==185274103:new=[coordinates(point) for point in candidate]
 else:
  line=LineString([a['local'](*xy)[[0,2]] for xy in coords]);clear=drivable.buffer(-2.6);new=[]
  for distance in np.linspace(0,line.length,math.ceil(line.length/.5)+1):
   pt=line.interpolate(distance);near=distance if p['jte_id_beg']==185274094 else line.length-distance
   corrected=nearest_points(pt,clear)[1];weight=max(0,min(1,(14-near)/4));xy=np.array(pt.coords[0])*(1-weight)+np.array(corrected.coords[0])*weight
   new.append(coordinates(xy))
  new[0 if p['jte_id_beg']==185274094 else -1]=endpoint
  new[-1 if p['jte_id_beg']==185274094 else 0]=coords[-1 if p['jte_id_beg']==185274094 else 0]
 patches.append({'roadId':fid,'start':p['jte_id_beg'],'end':p['jte_id_end'],'expectedCoordinates':[[round(v,7) for v in xy] for xy in coords],'coordinates':new})
# Vehicle footprints use actual runtime lane taper and oriented 4.3m x1.885m
# car boxes. Check the adjusted road and the first/last8m of incident transitions
# against union of all current and native carriageways (not parking/cyclepath).
checks=[]
for patch in patches:
 line=LineString([a['local'](*xy)[[0,2]] for xy in patch['coordinates']])
 for direction in [1,-1]:
  for distance in np.arange(0,line.length+.001,.25):
   if patch['roadId']!=185274103:
    near=distance if patch['start']==185274094 else line.length-distance
    if near>8:continue
   p=np.array(line.interpolate(distance).coords[0]);lo=np.array(line.interpolate(max(0,distance-.1)).coords[0]);hi=np.array(line.interpolate(min(line.length,distance+.1)).coords[0]);t=(hi-lo)/np.linalg.norm(hi-lo);normal=np.array([-t[1],t[0]])
   taper=min(1,distance/8,(line.length-distance)/8);centre=p+normal*1.15*direction*taper
   corners=[centre+t*l+normal*w for l,w in [(-2.15,-.9425),(-2.15,.9425),(2.15,.9425),(2.15,-.9425)]];footprint=Polygon(corners);outside=footprint.difference(drivable).area
   checks.append({'roadId':patch['roadId'],'direction':direction,'distance':round(float(distance),3),'outsideArea':float(outside)})
worst=sorted(checks,key=lambda x:x['outsideArea'],reverse=True)[:8]
output={'version':1,'mode':'motorcar','review':'Blaak current BGT2026-07-09 motor carriageway reconciled with original native visible road; NWB/WKD topology/access unchanged','sourceSurface':id,'sourceRegistered':f['properties']['tijdstip_registratie'],'sourceSha256':{name:hashlib.sha256((OUT/name).read_bytes()).hexdigest() for name in ['current-wegdeel.json','33584-6932.b3dm.gz','ortho2025.jpg','ortho2026.jpg']},'nwbSourceSha256':hashlib.sha256((ROOT/'source-data/traffic/nwb-roads.geojson.gz').read_bytes()).hexdigest(),'wkdSourceSha256':hashlib.sha256((ROOT/'source-data/traffic/wkd-cycling-access.csv.gz').read_bytes()).hexdigest(),'sharedJunction':185274094,'patches':patches}

report={'currentSource':f['properties'],'currentVsNativeHausdorffMetresInReviewBox':polygon.intersection(box(-420,-480,-400,-455)).hausdorff_distance(a['carriageway'].intersection(box(-420,-480,-400,-455))),'samplesChecked':len(checks),'maximumFootprintOutsideAreaSquareMetres':worst[0]['outsideArea'],'worst':worst}
(OUT/'current-corridor-review.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
# Source-native overhead overlay plus current dated vector boundary and candidate.
from PIL import Image,ImageDraw
image=Image.open(ROOT/'docs/images/traffic-blaak-surface.png').convert('RGB')
paint=ImageDraw.Draw(image)
for part in polygon.intersection(a['clip']).geoms if hasattr(polygon.intersection(a['clip']),'geoms') else [polygon.intersection(a['clip'])]:
 if part.geom_type=='Polygon':paint.line([a['screen'](p) for p in part.exterior.coords],fill='#168ec1',width=2)
paint.line([a['screen'](p) for p in candidate],fill='#087a43',width=4)
paint.text((25,42),'Blue border: current July2026 BGT / green: reconciled motor route',fill='#087a43',font=a['font'])
image.save(ROOT/'docs/images/traffic-blaak-current-corridor.png')
# Replay the renderer's bounded yaw rate through all admissible movements at
# the corrected node, including reverse directions. No body can cut the island.
turns=[]
for incoming in patches:
 for outgoing in patches:
  if incoming is outgoing:continue
  i=LineString([a['local'](*xy)[[0,2]] for xy in incoming['coordinates']]);o=LineString([a['local'](*xy)[[0,2]] for xy in outgoing['coordinates']])
  idir=1 if incoming['end']==185274094 else -1;odir=1 if outgoing['start']==185274094 else -1
  def pose(line,d,direction):
   p=np.array(line.interpolate(d).coords[0]);t=np.array(line.interpolate(min(line.length,d+.1)).coords[0])-np.array(line.interpolate(max(0,d-.1)).coords[0]);t/=np.linalg.norm(t)
   p+=np.array([-t[1],t[0]])*1.15*direction*min(1,d/8,(line.length-d)/8)
   return p,math.atan2(t[0]*direction,t[1]*direction)
  _,start_heading=pose(i,i.length if idir==1 else 0,idir);_,end_heading=pose(o,0 if odir==1 else o.length,odir)
  if math.cos(start_heading-end_heading)<-.5:continue
  heading=None;maximum=0
  for travel in np.arange(-6,6.001,.175):
   line,d,direction=(i,i.length+travel if idir==1 else -travel,idir) if travel<0 else (o,travel if odir==1 else o.length-travel,odir)
   centre,wanted=pose(line,d,direction)
   if heading is None:heading=wanted
   else:heading+=max(-.07,min(.07,math.atan2(math.sin(wanted-heading),math.cos(wanted-heading))))
   t=np.array([math.sin(heading),math.cos(heading)]);n=np.array([-t[1],t[0]])
   body=Polygon([centre+t*l+n*w for l,w in [(-2.15,-.9425),(-2.15,.9425),(2.15,.9425),(2.15,-.9425)]])
   maximum=max(maximum,body.difference(drivable).area)
  turns.append({'from':incoming['roadId'],'fromDirection':idir,'to':outgoing['roadId'],'toDirection':odir,'maximumFootprintOutsideAreaSquareMetres':maximum})
report['turnClearance']=turns
(OUT/'current-corridor-review.json').write_text(json.dumps(report,indent=2)+'\n')
if max([c['outsideArea'] for c in checks]+[t['maximumFootprintOutsideAreaSquareMetres'] for t in turns])>1e-5:raise ValueError('Vehicle footprint leaves supported carriageway')
(ROOT/'public/data/traffic/road-geometry.json').write_text(json.dumps(output,indent=2)+'\n')
# Dated image comparison. Gamma is inspection-only; original JPEGs stay intact.
from PIL import Image,ImageFont
font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',13);sheet=Image.new('RGB',(1200,640),'#f1f0e6');rd=Transformer.from_crs(4326,28992,always_xy=True).transform
for index,year in enumerate([2025,2026]):
 meta=json.loads((OUT/f'ortho{year}.json').read_bytes());photo=Image.open(OUT/f'ortho{year}.jpg').convert('RGB')
 if year==2026:photo=photo.point([round(255*(v/255)**.45) for v in range(256)]*3)
 paint=ImageDraw.Draw(photo);xmin,ymin,xmax,ymax=meta['boundsRD']
 def pixel(lon,lat):
  x,y=rd(lon,lat);return (x-xmin)/(xmax-xmin)*600,(ymax-y)/(ymax-ymin)*600
 paint.line([pixel(*xy) for xy in patches[0]['expectedCoordinates']],fill='#2879ff',width=2)
 paint.line([pixel(*xy) for xy in patches[0]['coordinates']],fill='#15e080',width=3)
 sheet.paste(photo,(index*600,40));ImageDraw.Draw(sheet).text((index*600+10,10),f'{year} '+('gamma0.45 for shadow inspection; ' if year==2026 else '')+'blue original / green derived motor route',fill='#293c37',font=font)
sheet.save(ROOT/'docs/images/traffic-blaak-dated-corridor.png')
