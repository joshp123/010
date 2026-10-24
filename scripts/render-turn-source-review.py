import json,gzip,textwrap,argparse
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from pyproj import Transformer
from shapely.geometry import LineString,box
ROOT=Path(__file__).resolve().parents[1];SOURCE=ROOT/'source-data/traffic';P=Transformer.from_crs(4326,28992,always_xy=True).transform
args=argparse.ArgumentParser();args.add_argument('--municipality',action='store_true');a=args.parse_args()
prefix='osm-municipality' if a.municipality else 'osm-centre'
audit_name='osm-municipality-turn-audit.json' if a.municipality else 'osm-turn-restriction-audit.json'
osm=json.loads(gzip.decompress((SOURCE/(prefix+'-turn-restrictions.json.gz')).read_bytes()));audit=json.loads((SOURCE/audit_name).read_bytes())
nodes={n['id']:P(n['lon'],n['lat']) for n in osm['elements'] if n['type']=='node'};ways={w['id']:w for w in osm['elements'] if w['type']=='way'}
nwb={f['properties']['wvk_id']:f for f in json.loads(gzip.decompress((SOURCE/'nwb-roads.geojson.gz').read_bytes()))['features']}
selected=[r for r in audit['relations'] if r['osmRelation'] in audit['strictCandidateRelations']]
img=Image.new('RGB',(1200,60+330*((len(selected)+3)//4)),'#f1f0e6');d=ImageDraw.Draw(img);font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',13);small=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',11)
d.text((20,12),f'{len(selected)} strict turn matches · north up · blue OSM / orange NWB / green connected name evidence · 70m square',fill='#293c37',font=font)
for i,r in enumerate(selected):
 ox=(i%4)*300;oy=45+(i//4)*330;vx,vy=nodes[r['osmViaNode']];clip=box(vx-35,vy-35,vx+35,vy+35)
 def screen(p):return ox+150+(p[0]-vx)*3.3,oy+180-(p[1]-vy)*3.3
 d.text((ox+10,oy),f"OSM {r['osmRelation']} · {r['restriction']}",font=small,fill='#293c37')
 label=' → '.join(m['osmName']+(f" [NWB {m['nwbName']}]" if m['osmName']!=m['nwbName'] else '') for m in [r['matches'][role] for role in ['from','to']])
 for k,line in enumerate(textwrap.wrap(label,width=37)):d.text((ox+10,oy+17+14*k),line,font=small,fill='#293c37')
 d.rectangle((ox+34,oy+64,ox+266,oy+296),outline='#c7ccbd')
 for typ,color,width in [('osm','#408ab8',5),('nwb','#c36a37',2),('continuation','#39794d',2)]:
  for role in ['from','to']:
   m=r['matches'][role]
   if typ=='osm':parts=[[nodes[n] for n in ways[m['osmWay']]['nodes']]]
   else:
    if typ=='continuation' and not m.get('continuation'):continue
    f=nwb[m['continuation']['roadId'] if typ=='continuation' else m['nwbRoad']];g=f['geometry'];parts=g['coordinates'] if g['type']=='MultiLineString' else [g['coordinates']];parts=[[P(*xy) for xy in part] for part in parts]
   for part in parts:
    g=LineString(part).intersection(clip)
    for line in g.geoms if hasattr(g,'geoms') else [g]:
     if line.geom_type=='LineString':d.line([screen(p) for p in line.coords],fill=color,width=width)
 d.ellipse((ox+146,oy+176,ox+154,oy+184),outline='#133b55',width=2)
 d.text((ox+12,oy+303),f"via offset {r['junctionDistanceMetres']}m · NWB {r['nwbJunction']}",font=small,fill='#293c37')
if a.municipality:
 for page,y in enumerate(range(45,img.height,1650)):
  section=img.crop((0,y,1200,min(y+1650,img.height)))
  sheet=Image.new('RGB',(1200,45+section.height),'#f1f0e6');sheet.paste(img.crop((0,0,1200,45)));sheet.paste(section,(0,45))
  sheet.save(ROOT/f'docs/images/traffic-municipality-matches-{page+1}.png')
else:img.save(ROOT/'docs/images/traffic-restriction-matches.png')
if a.municipality:
 from shapely.geometry import shape
 raw_boundary=json.loads((ROOT/'source-data/transit/municipality.geojson').read_bytes())
 boundary=shape(raw_boundary['features'][0]['geometry'] if 'features' in raw_boundary else raw_boundary.get('geometry',raw_boundary))
 outline=boundary.geoms if hasattr(boundary,'geoms') else [boundary]
 all_points=[P(*xy) for polygon in outline for xy in polygon.exterior.coords]
 xmin,ymin=min(p[0] for p in all_points),min(p[1] for p in all_points)
 xmax,ymax=max(p[0] for p in all_points),max(p[1] for p in all_points)
 scale=min(1100/(xmax-xmin),560/(ymax-ymin))
 def map_point(p):return 50+(p[0]-xmin)*scale,630-(p[1]-ymin)*scale
 overview=Image.new('RGB',(1200,700),'#f1f0e6');draw=ImageDraw.Draw(overview)
 draw.text((20,15),'Municipality source review · north up · green active / orange unresolved target / grey other relations',fill='#293c37',font=font)
 for polygon in outline:draw.line([map_point(P(*xy)) for xy in polygon.exterior.coords],fill='#8d998d',width=2)
 review=json.loads((SOURCE/'osm-municipality-turn-review.json').read_bytes());active=set(review['selectedRelations'])
 relations={r['id']:r for r in osm['elements'] if r['type']=='relation'}
 for r in audit['relations']:
  members=relations[r['osmRelation']]['members'];via=next((m['ref'] for m in members if m['role']=='via' and m['type']=='node'),None)
  if via not in nodes:continue
  x,y=map_point(nodes[via]);color='#39794d' if r['osmRelation'] in active else '#c36a37' if r['osmRelation'] in audit['strictCandidateRelations'] else '#bdc1b5'
  size=4 if r['osmRelation'] in audit['strictCandidateRelations'] else 1
  draw.ellipse((x-size,y-size,x+size,y+size),fill=color)
 draw.text((20,665),'60 active matches; unsupported/ambiguous relations retained. Complete acquisition does not mean complete legal routing.',fill='#293c37',font=font)
 overview.save(ROOT/'docs/images/traffic-municipality-overview.png')
