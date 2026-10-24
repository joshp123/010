import gzip,json,importlib.util,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from cycling_access import bicycle_direction,eligible_feature
spec=importlib.util.spec_from_file_location('restrictions',ROOT/'scripts/audit-turn-restrictions.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class AccessTest(unittest.TestCase):
 def test_explicit_directions(self):
  for h,t,result in [('J','J',3),('J','N',1),('N','J',2),('N','N',0),('','J',0),('O','J',0)]:self.assertEqual(bicycle_direction({'FIETS_H':h,'FIETS_T':t}),result)
 def test_motor_direction_is_not_bicycle_direction(self):
  p={'wvk_begdat':'2026-01-01','bst_code':'RB','rijrichtng':'H'}
  self.assertEqual(eligible_feature(p,{'FIETS_H':'N','FIETS_T':'J'},'2026-10-07'),2)
  self.assertEqual(eligible_feature(dict(p,wvk_begdat='2026-10-08'),{'FIETS_H':'J','FIETS_T':'J'},'2026-10-07'),0)
 def test_restriction_match_and_ambiguity(self):
  points=[(4.49,51.92),(4.491,51.92),(4.491,51.921)]
  ways=[{'type':'way','id':1,'nodes':[1,2],'tags':{'name':'A'}},{'type':'way','id':2,'nodes':[2,3],'tags':{'name':'B'}}]
  relation={'type':'relation','id':9,'tags':{'restriction':'no_left_turn'},'members':[{'role':'from','type':'way','ref':1},{'role':'via','type':'node','ref':2},{'role':'to','type':'way','ref':2}]}
  osm={'elements':[{'type':'node','id':i+1,'lon':p[0],'lat':p[1]} for i,p in enumerate(points)]+ways+[relation]}
  features=[{'properties':{'wvk_id':10+i,'jte_id_beg':100+i,'jte_id_end':101+i,'stt_naam':name,'rijrichtng':'H'},'geometry':{'type':'MultiLineString','coordinates':[points[i:i+2]]}} for i,name in enumerate(['A','B'])]
  r=mod.match_restrictions(osm,features)[0];self.assertEqual(r['status'],'review-candidate');self.assertEqual((r['fromNWB'],r['toNWB']),(10,11))
  duplicate=dict(features[1],properties=dict(features[1]['properties'],wvk_id=12))
  self.assertEqual(mod.match_restrictions(osm,features+[duplicate])[0]['status'],'unmatched')
  relation['tags']['except']='bicycle;motorcar';self.assertEqual(mod.match_restrictions(osm,features)[0]['reason'],'motorcar exempt')
 def test_retained_nwb_and_actual_osm_inventory(self):
  features=json.loads(gzip.decompress((ROOT/'source-data/traffic/nwb-roads.geojson.gz').read_bytes()))['features']
  osm=json.loads(gzip.decompress((ROOT/'source-data/traffic/osm-centre-turn-restrictions.json.gz').read_bytes()))
  inventory={};results=mod.match_restrictions(osm,features,inventory)
  self.assertEqual(inventory['multiLineStrings'],len(features))
  self.assertEqual(inventory['usableEndpoints'],len(features)*2)
  self.assertGreater(inventory['junctions'],20000)
  self.assertEqual(len(results),63)
  candidates={r['osmRelation']:r for r in results if r['status']=='review-candidate'}
  self.assertGreaterEqual(len(candidates),10)
  self.assertEqual(candidates[4063857]['fromNWB'],601722926)
  self.assertEqual(candidates[4063857]['toNWB'],601723271)
 def test_empty_supported_inventory_is_error(self):
  feature={'properties':{},'geometry':{'type':'Point','coordinates':[4.49,51.92]}}
  with self.assertRaisesRegex(ValueError,'No usable NWB'):
   mod.match_restrictions({'elements':[]},[feature])
if __name__=='__main__':unittest.main()
