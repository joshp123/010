import importlib.util,json,unittest
from pathlib import Path
from shapely.geometry import box,shape
from shapely.ops import unary_union
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('collector',ROOT/'scripts/acquire-municipality-turns.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class CollectorTest(unittest.TestCase):
 def test_actual_municipality_coverage(self):
  raw=json.loads(mod.BOUNDARY.read_bytes());boundary=shape(raw['features'][0]['geometry'] if 'features' in raw else raw.get('geometry',raw))
  tiles=mod.make_tiles(boundary);self.assertEqual(len(tiles),17)
  coverage=unary_union([box(t['bbox'][1],t['bbox'][0],t['bbox'][3],t['bbox'][2]) for t in tiles])
  self.assertLess(boundary.difference(coverage).area,1e-12)
 def test_merge_members_boundary_and_conflicts(self):
  nodes=[{'type':'node','id':i,'lon':i,'lat':0} for i in range(1,5)]
  way={'type':'way','id':10,'nodes':[1,2]}
  rel={'type':'relation','id':20,'members':[{'type':'node','ref':1,'role':'via'},{'type':'way','ref':10,'role':'from'},{'type':'way','ref':10,'role':'to'}]}
  outside=dict(rel,id=21,members=[{'type':'node','ref':4,'role':'via'}])
  response={'elements':nodes+[way,rel,outside]}
  result,excluded=mod.merge_responses([response,response],box(0,-1,2,1))
  self.assertEqual(excluded,1);self.assertEqual(len(result['elements']),4)
  with self.assertRaisesRegex(ValueError,'Conflicting source'):
   mod.merge_responses([response,{'elements':[dict(nodes[0],lat=.1)]}],box(0,-1,2,1))
if __name__=='__main__':unittest.main()
