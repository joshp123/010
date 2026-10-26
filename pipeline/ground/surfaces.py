"""BGT surface classification, 10 cm rasterisation and rail masks.
Written by AI on 2026-10-25 by model GPT-6.1 Sol.
No appearance is inferred from an aerial photograph. Unknown stays unknown.
"""
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from shapely.geometry import shape, box
from shapely import make_valid
from shapely.strtree import STRtree
from archive import fetch
CRS='http://www.opengis.net/def/crs/EPSG/0/28992'
LEGEND=['unknown','carriageway','cycle path','footpath, pavement','parking','tram track bed','grass, planted verge','shrubs, hedges','water','unpaved, sand, bare','paved yard or square','building footprint','bridge deck','quay wall, civil structure','train or metro track bed','traffic island, crossing','rail yard, ballast']
COLLECTIONS=['wegdeel','ondersteunendwegdeel','begroeidterreindeel','onbegroeidterreindeel','waterdeel','ondersteunendwaterdeel','pand','overbruggingsdeel','kunstwerkdeel_vlak','scheiding_vlak','scheiding_lijn','spoor','overigbouwwerk','ongeclassificeerdobject','vegetatieobject_vlak','weginrichtingselement_vlak']
# Explicit field-value contract, shared in the scene manifest.
FUNCTION_CLASSES={
 'rijbaan autosnelweg':1,'rijbaan autoweg':1,'rijbaan regionale weg':1,'rijbaan lokale weg':1,
 'rijbaan':1,'fietspad':2,'voetpad':3,'voetpad op trap':3,'ruiterpad':9,
 'parkeervlak':4,'OV-baan':5,'ov-baan':5,'spoorbaan':14,'baan voor vliegverkeer':1,
 'transitie':15,'verkeerseiland':15,'berm':6}
APPEARANCE_CLASSES={'grasland agrarisch':6,'grasland overig':6,'groenvoorziening':6,
 'bouwland':6,'akkerbouw':6,'heide':6,'loofbos':7,'naaldbos':7,'gemengd bos':7,
 'struiken':7,'struikrozen':7,'heesters':7,'houtwal':7,'haag':7,'rietland':6,
 'onverhard':9,'zand':9,'open verharding':10,'gesloten verharding':10,
 'half verhard':9,'erf':10,'spoorbaan':14,'ballast':16}
PLUS_APPEARANCE_CLASSES={'heesters':7,'bosplantsoen':7,'struikrozen':7,'haag':7,'gras- en kruidachtigen':6,'planten':6}
DEFAULT_CLASSES={'waterdeel':8,'ondersteunendwaterdeel':9,'pand':11,'overbruggingsdeel':12,
 'kunstwerkdeel_vlak':13,'scheiding_vlak':13,'overigbouwwerk':13,
 'vegetatieobject_vlak':7,'weginrichtingselement_vlak':15}
PALETTE=np.array([[220,40,180],[90,93,100],[170,67,55],[211,191,158],[117,120,133],[110,97,89],[115,155,82],[62,113,65],[66,140,175],[180,157,116],[172,158,139],[202,197,187],[167,152,120],[100,85,77],[102,92,113],[203,170,90],[132,124,110]],dtype=np.uint8)

def classify(collection,properties):
 function=str(properties.get('functie') or properties.get('FUNCTIE') or '').strip()
 physical=str(properties.get('fysiek_voorkomen') or properties.get('FYSIEKVK') or '').strip()
 if function=='spoorbaan' or physical=='spoorbaan':return 14
 if physical=='ballast':return 16
 if collection in DEFAULT_CLASSES:return DEFAULT_CLASSES[collection]
 if collection=='begroeidterreindeel' and properties.get('plus_fysiek_voorkomen') in PLUS_APPEARANCE_CLASSES:return PLUS_APPEARANCE_CLASSES[properties['plus_fysiek_voorkomen']]
 if collection=='ondersteunendwegdeel' and function=='berm' and physical in ('open verharding','gesloten verharding'):return 10
 if collection in ('wegdeel','ondersteunendwegdeel') and function in FUNCTION_CLASSES:return FUNCTION_CLASSES[function]
 if physical in APPEARANCE_CLASSES:return APPEARANCE_CLASSES[physical]
 return 0

def load_collection(collection,bounds):
 params={'bbox':','.join(map(str,bounds)),'bbox-crs':CRS,'crs':CRS,'limit':1000,'f':'json','filter':'eind_registratie IS NULL','filter-lang':'cql2-text'}
 url=f'https://api.pdok.nl/lv/bgt/ogc/v1/collections/{collection}/items?'+urlencode(params)
 records=[];page=0
 archive_prefix='m0-buffer' if tuple(bounds)==(89745,435245,92005,436755) else 'bbox_'+'_'.join(map(str,bounds))
 while url:
  j=json.loads(fetch('bgt',f'{collection}/{archive_prefix}-page{page:03}.json',url))
  for feature in j['features']:
   p=feature['properties']
   # The OGC API exposes history by default. Do not draw retired versions or tunnels.
   if p.get('eind_registratie') or p.get('termination_date') or (p.get('relatieve_hoogteligging') or 0)<0:continue
   if p.get('status') not in (None,'bestaand'):continue
   if not feature.get('geometry'):continue
   g=make_valid(shape(feature['geometry']))
   records.append((collection,p,g))
  url=next((l['href'] for l in j.get('links',[]) if l['rel']=='next'),None);page+=1
 print(collection,len(records),'current surface records',flush=True)
 return records

class SurfaceData:
 def __init__(self,bounds):
  with ThreadPoolExecutor(max_workers=5) as pool:
   self.records=[r for result in pool.map(lambda c:load_collection(c,bounds),COLLECTIONS) for r in result]
  self.tree=STRtree([r[2] for r in self.records])
  self.attribute_counts=Counter((c,p.get('functie'),p.get('fysiek_voorkomen'),classify(c,p)) for c,p,g in self.records)
 def select(self,bounds):return [self.records[i] for i in self.tree.query(box(*bounds))]

def draw_geometry(image,geometry,x,y,value):
 draw=ImageDraw.Draw(image)
 def coords(points):return [((a-x)*10-.5,(y+250-b)*10-.5) for a,b,*_ in points]
 if geometry.geom_type=='Polygon':
  # Draw into local bounding mask so holes reveal underlying surfaces, never erase them.
  exterior=coords(geometry.exterior.coords)
  if not geometry.interiors:draw.polygon(exterior,fill=value)
  else:
   mask=Image.new('1',image.size);d=ImageDraw.Draw(mask);d.polygon(exterior,fill=1)
   for ring in geometry.interiors:d.polygon(coords(ring.coords),fill=0)
   image.paste(value,(0,0),mask)
 elif hasattr(geometry,'geoms'):
  for part in geometry.geoms:draw_geometry(image,part,x,y,value)

def rasterize(data,x,y):
 records=data.select((x-2,y-2,x+252,y+252))
 image=Image.new('L',(2500,2500))
 # Level order resolves bridges over water/roads. Same-level base cover precedes detailed overlays.
 priorities={'onbegroeidterreindeel':0,'begroeidterreindeel':0,'ondersteunendwaterdeel':0,'waterdeel':1,'wegdeel':2,'ondersteunendwegdeel':2,'pand':3,'kunstwerkdeel_vlak':4,'overigbouwwerk':4,'scheiding_vlak':4,'vegetatieobject_vlak':4,'weginrichtingselement_vlak':4,'overbruggingsdeel':5}
 ordered=sorted(records,key=lambda r:((r[1].get('relatieve_hoogteligging') or 0),priorities.get(r[0],0)))
 for c,p,g in ordered:
  if c in ('spoor','scheiding_lijn'):continue
  cls=classify(c,p)
  if cls:draw_geometry(image,g,x,y,cls)
 classes=np.asarray(image).copy()
 line_bits=np.zeros_like(classes)
 # BGT spoor represents one track centreline. Pair of rail heads at standard gauge.
 # Offset 0.7175 m is a nominal centre separation; rail-head width 7 cm sampled at 10 cm.
 # Underground sneltram features have already been excluded.
 rail_info=Counter()
 for c,p,g in records:
  if c!='spoor':continue
  function=p.get('functie')
  # Harbour-crane rails are not standard-gauge passenger tracks. No contract bit represents them.
  if function not in ('tram','trein','sneltram','metro'):
   rail_info['omitted:'+str(function)+':'+str(p.get('plus_functie'))]+=1
   continue
  bit=1 if function=='tram' else 2
  rail_info[str(function)]+=1
  lines=list(g.geoms) if hasattr(g,'geoms') else [g]
  for line in lines:
   if line.geom_type!='LineString':continue
   rail_image=Image.new('L',image.size)
   for offset in (-.7175,.7175):
    rail=line.offset_curve(offset,quad_segs=8,join_style='round')
    draw_geometry(rail_image,rail.buffer(.05,cap_style='flat'),x,y,1)
   line_bits[np.asarray(rail_image)>0]|=bit
 # A kerb only exists where pavement meets road/cycleway. 1 pixel on each side of the boundary.
 pavement=classes==3; road=np.isin(classes,[1,2]); structure=ndimage.generate_binary_structure(2,1)
 kerb=(road&ndimage.binary_dilation(pavement,structure=structure))|(pavement&ndimage.binary_dilation(road,structure=structure))
 line_bits[kerb]|=8
 return classes,line_bits,dict(rail_info)
