import json,struct,unittest,math
from pathlib import Path
import numpy as np
from pyproj import Transformer
from shapely.geometry import LineString,Point
ROOT=Path(__file__).resolve().parents[1]
class BridgeTest(unittest.TestCase):
 def test_real_reported_crossing_has_deck(self):
  raw=(ROOT/'public/data/supplemental-bridge-surfaces/soetensteeg.glb').read_bytes();length=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+length]);binary=raw[28+length:]
  lon,lat=np.radians([4.49,51.915]);P=Transformer.from_crs(4979,4978,always_xy=True).transform;origin=np.array(P(4.49,51.915,0));east=np.array([-np.sin(lon),np.cos(lon),0]);south=np.array([np.sin(lat)*np.cos(lon),np.sin(lat)*np.sin(lon),-np.cos(lat)]);point=np.array(P(4.483014458,51.919168681,0))-origin;probe=np.array([point@east,point@south]);heights=[]
  for mesh in doc['meshes']:
   for primitive in mesh['primitives']:
    acc=doc['accessors'][primitive['attributes']['POSITION']];view=doc['bufferViews'][acc['bufferView']];vertices=np.frombuffer(binary,dtype='<f4',count=acc['count']*3,offset=view.get('byteOffset',0)).reshape(-1,3)
    for tri in vertices.reshape(-1,3,3):
     plan=tri[:,[0,2]];matrix=(plan[1:]-plan[0]).T
     if abs(np.linalg.det(matrix))<1e-8:continue
     weights=np.linalg.solve(matrix,probe-plan[0])
     if min(weights)>=-1e-6 and weights.sum()<=1+1e-6:heights.append((mesh['name'],float(tri[0,1]+weights@(tri[1:,1]-tri[0,1]))))
  self.assertTrue(any(kind=='road' and 3.5<height<4 for kind,height in heights),heights)
  meta=json.loads((ROOT/'public/data/supplemental-bridge-surfaces/manifest.json').read_bytes());self.assertEqual(len(meta['surfaces']),4)
  self.assertTrue(all(s['rmseMetres']<.05 for s in meta['surfaces']))
 def test_profile_does_not_change_source_plan(self):
  data=json.loads((ROOT/'public/data/traffic/surface-profiles.json').read_bytes());self.assertEqual([p['roadId'] for p in data['roads']],[185274065])
  for road in data['roads']:
   T=Transformer.from_crs(4326,28992,always_xy=True).transform;source=LineString([T(*xy) for xy in road['expectedCoordinates']]);profile=LineString([T(*xy) for xy in road['coordinates']])
   self.assertLess(source.hausdorff_distance(profile),.02)
   self.assertTrue(all(math.dist(T(*a),T(*b))<=2.01 for a,b in zip(road['coordinates'],road['coordinates'][1:])))
if __name__=='__main__':unittest.main()
