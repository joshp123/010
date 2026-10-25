#!/usr/bin/env python3
"""Written by AI, GPT-6 Astra, 2026-10-25. Reconcile one observed bridge cycle corridor."""
import gzip,json,hashlib
from pathlib import Path
import numpy as np
from pyproj import Transformer
from shapely.geometry import shape,LineString,Point
from shapely.ops import transform,unary_union
ROOT=Path(__file__).resolve().parents[1]
rd=Transformer.from_crs(4326,28992,always_xy=True).transform
geo=Transformer.from_crs(28992,4326,always_xy=True).transform
raw=ROOT/'source-data/traffic/nwb-cycleways.geojson.gz'
feature=next(f for f in json.load(gzip.open(raw,'rt'))['features'] if f['properties']['wvk_id']==600491271)
coordinates=feature['geometry']['coordinates'][0]
line=LineString([rd(*p) for p in coordinates])
# The aerial confirms the inside red lane, separated from the outer grey walk.
# These two corresponding BGT polygons cover the deck and north approach.
ids=['G0599.170ade244fca72d73e050210a7e24429','G0599.170ade24469162d73e050210a7e24429']
bgt=ROOT/'source-data/erasmus-public-space/wegdeel.json'
polygons=unary_union([transform(rd,shape(f['geometry'])) for f in json.load(open(bgt))['features'] if f['properties']['lokaal_id'] in ids])
distances=np.linspace(0,line.length,int(np.ceil(line.length/2))+1)
shifts=[]
for distance in distances:
 p=np.array(line.interpolate(distance).coords[0]);t=np.array(line.interpolate(min(line.length,distance+1)).coords[0])-np.array(line.interpolate(max(0,distance-1)).coords[0]);t/=np.linalg.norm(t);n=np.array([-t[1],t[0]])
 cross=LineString([p-n*8,p+n*8]).intersection(polygons)
 pieces=list(cross.geoms) if hasattr(cross,'geoms') else [cross]
 pieces=[piece for piece in pieces if piece.geom_type=='LineString' and piece.length>.2]
 if pieces:
  piece=min(pieces,key=lambda piece:piece.distance(Point(p)));shifts.append(np.array(piece.interpolate(.5,normalized=True).coords[0])-p)
 else:shifts.append(None)
valid=[i for i,s in enumerate(shifts) if s is not None]
# Continue the matched lane smoothly into unchanged source approach junctions.
for index,shift in enumerate(shifts):
 if shift is not None:continue
 nearest=min(valid,key=lambda j:abs(distances[j]-distances[index]));fade=max(0,1-abs(distances[nearest]-distances[index])/20)
 shifts[index]=shifts[nearest]*fade
result=[]
for distance,shift in zip(distances,shifts):
 p=np.array(line.interpolate(distance).coords[0])+shift;result.append(list(geo(*p)))
result[0]=coordinates[0];result[-1]=coordinates[-1]
p=feature['properties']
out=dict(version=1,mode='bicycle',review='Erasmusbrug east cycle corridor: corresponding BGT deck/approach cycle polygons, confirmed by retained 2026 aerial. Original source identities, access and junctions retained.',sourceSurface=ids,sourceSha256={'wegdeel.json':hashlib.sha256(bgt.read_bytes()).hexdigest(),'nwb-cycleways.geojson.gz':hashlib.sha256(raw.read_bytes()).hexdigest()},patches=[dict(roadId=600491271,start=p['jte_id_beg'],end=p['jte_id_end'],expectedCoordinates=coordinates,coordinates=result)])
(ROOT/'public/data/traffic/cycle-geometry.json').write_text(json.dumps(out,indent=2)+'\n')
print('Maximum observed lane-centre reconciliation:',max(np.linalg.norm(s) for s in shifts),'metres')
