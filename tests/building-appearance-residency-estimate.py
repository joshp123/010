#!/usr/bin/env python3
"""Conservative orthographic box visibility estimate, not browser memory telemetry.
Delfshaven51.9098,4.448,span200,bearing35; replicates scene camera elevation.
"""
import json,numpy as np,itertools,math
from pathlib import Path
root=Path(__file__).resolve().parents[1]/'public/data/building-appearance';m=json.loads((root/'manifest.json').read_text());ts=json.loads((root/'tileset.json').read_text())
lat,lon=np.radians([51.9098,4.448]);N=6378137/math.sqrt(1-.00669437999014*math.sin(lat)**2);target=np.array([N*math.cos(lat)*math.cos(lon),N*math.cos(lat)*math.sin(lon),N*(1-.00669437999014)*math.sin(lat)])
frame=np.array([[-math.sin(lon),math.cos(lon),0],[math.cos(lat)*math.cos(lon),math.cos(lat)*math.sin(lon),math.sin(lat)],[math.sin(lat)*math.cos(lon),math.sin(lat)*math.sin(lon),-math.cos(lat)]])
b=np.radians(35);right=np.array([math.cos(b),0,-math.sin(b)]);direction=np.array([math.sin(b),1/math.sqrt(2),math.cos(b)]);direction/=np.linalg.norm(direction);up=np.cross(direction,right)
for width,height in [(390,844),(1440,900)]:
 count=total=old=0
 for entry,tile in zip(m['entries'],ts['root']['children']):
  rtc=np.array(tile['transform'][12:15]);hit=False
  for leaf in entry['spatialBuildings']:
   box=np.array(leaf['boundingVolume']['box']);corners=np.array([box[:3]+box[3:].reshape(3,3,order='F')@s for s in itertools.product([-1,1],repeat=3)])+rtc;local=(corners-target)@frame.T;x=local@right;y=local@up
   visible=x.min()<=100*width/height and x.max()>=-100*width/height and y.min()<=100 and y.max()>=-100
   if visible:count+=1;total+=leaf['decodedRgbaBytesIncludingMips'];hit=True
  if hit:old+=entry['textureLevels'][-1]['decodedRgbaBytesIncludingMips']
 print(width,height,count,'packedMiB',total/1048576,'oldIntersectingTilesMiB',old/1048576)
