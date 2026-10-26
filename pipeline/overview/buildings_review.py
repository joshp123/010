"""Written by AI on 2026-10-26 by model GPT-6. Inspect overview roof source coverage."""
import gzip,json
from pathlib import Path
from PIL import Image,ImageDraw
from shapely.geometry import shape,box
ROOT=Path('/Volumes/Josh Extreme Pro USB4 4TB/010');SCENE=ROOT/'scene/overview-v1';DEST=ROOT/'renders/overview';DEST.mkdir(parents=True,exist_ok=True)
REGIONS=[('Maasvlakte terminals',(57000,437000,63000,443000)),('Hoek van Holland',(65000,442000,70000,446000)),('Europoort',(67000,435000,75000,441000))]
features=json.loads(gzip.decompress((SCENE/'building-footprints.geojson.gz').read_bytes()))['features'];shapes=[(shape(f['geometry']),f['properties']) for f in features]
for label,bounds in REGIONS:
 x0,y0,x1,y1=bounds;res=4.;im=Image.new('RGB',(int((x1-x0)/res),int((y1-y0)/res)),(30,30,30));draw=ImageDraw.Draw(im)
 for x in range(x0,x1,1000):
  for y in range(y0,y1,1000):
   path=SCENE/'tiles'/f'x{x}_y{y}'/'ortho.jpg'
   if path.exists():im.paste(Image.open(path).resize((250,250),Image.Resampling.LANCZOS),(int((x-x0)/res),int((y1-y-1000)/res)))
 draw=ImageDraw.Draw(im)
 for geometry,properties in shapes:
  if not geometry.intersects(box(*bounds)):continue
  polygons=[geometry] if geometry.geom_type=='Polygon' else list(geometry.geoms)
  for polygon in polygons:
   if polygon.geom_type!='Polygon':continue
   points=[((x-x0)/res,(y1-y)/res) for x,y in polygon.exterior.coords]
   draw.line(points,fill=(0,255,255) if properties['source']=='lod2' else (255,100,0),width=1)
 draw.rectangle((0,0,400,25),fill=(0,0,0));draw.text((5,5),label+' | cyan buildings, orange tanks/bridges',fill='white')
 im.save(DEST/(label.lower().replace(' ','-')+'-building-coverage.png'))
# Visual observations recorded after looking at these exact 2026-aerial overlays.
review={'written_by':'AI, GPT-6, 2026-10-26','images':[label.lower().replace(' ','-')+'-building-coverage.png' for label,_ in REGIONS],'findings':[{'area':'South-west Maasvlakte warehouse cluster','bounds_rd':[57800,438600,58600,439200],'observation':'Large warehouse roofs visible in the 2026 aerial lack corresponding municipal building footprints. Source age as the cause is unproved.'},{'area':'Peninsula south of Nieuwe Waterweg','bounds_rd':[65900,442700,66400,443100],'observation':'A large white roof visible in the aerial lacks a corresponding municipal building footprint. Source age as the cause is unproved.'}],'other_observations':'Hoek van Holland housing and Europoort storage tanks are broadly present. These overview images do not establish every-building freshness. Containers, ships and cranes visible in imagery are not represented by this building/tank source selection.'}
(DEST/'buildings-coverage-review.json').write_text(json.dumps(review,indent=2)+'\n')
