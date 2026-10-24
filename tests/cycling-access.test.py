import gzip,hashlib,json,importlib.util,sys,unittest
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
  self.assertEqual(candidates[1312594]['matches']['to']['continuation']['roadId'],601214656)
  self.assertEqual(candidates[14966194]['matches']['to']['continuation']['roadId'],601044957)
  self.assertNotIn(21622541,candidates,'OSM/NWB motor direction conflict must remain unmatched')
  without_continuation=[f for f in features if f['properties']['wvk_id']!=601214656]
  rejected=mod.match_restrictions(osm,without_continuation)
  self.assertEqual(next(r for r in rejected if r['osmRelation']==1312594)['status'],'unmatched','different names require actual connected continuation evidence')
 def test_municipal_mode_and_complex_semantics(self):
  osm=json.loads(gzip.decompress((ROOT/'source-data/traffic/osm-municipality-turn-restrictions.json.gz').read_bytes()))
  features=json.loads(gzip.decompress((ROOT/'source-data/traffic/nwb-roads.geojson.gz').read_bytes()))['features']
  results={r['osmRelation']:r for r in mod.match_restrictions(osm,features)}
  self.assertEqual(len(results),620)
  self.assertEqual(results[21011676]['reason'],'unsupported motor restriction type','bus/hgv-only restriction is not a motorcar rule')
  for relation in [5486770,11371540,11371541]:self.assertEqual(results[relation]['reason'],'conditional restriction requires temporal evaluation')
  self.assertEqual(results[11605330]['exceptions'],['bicycle'])
  self.assertEqual(results[11605330]['status'],'review-candidate','bicycle exemption does not exempt motorcars')
  relation=next(r for r in osm['elements'] if r.get('id')==11605330 and r['type']=='relation')
  relation['tags']['except']='bicycle; motor_vehicle '
  altered=mod.match_restrictions({'elements':[r for r in osm['elements'] if r['type']!='relation']+[relation]},features)[0]
  self.assertEqual(altered['reason'],'motorcar exempt')
  relation['tags']={'type':'restriction','restriction':'only_straight_on','restriction:motorcar':'no_left_turn'}
  altered=mod.match_restrictions({'elements':[r for r in osm['elements'] if r['type']!='relation']+[relation]},features)[0]
  self.assertEqual(altered['restrictionKey'],'restriction:motorcar');self.assertEqual(altered['restriction'],'no_left_turn')
 def test_empty_supported_inventory_is_error(self):
  feature={'properties':{},'geometry':{'type':'Point','coordinates':[4.49,51.92]}}
  with self.assertRaisesRegex(ValueError,'No usable NWB'):
   mod.match_restrictions({'elements':[]},[feature])
 def test_partial_acquisition_cannot_overwrite_complete_audit(self):
  raw=b'{"elements":[]}'
  meta={'complete':False,'scope':'partial-tile-coverage','outputSha256':hashlib.sha256(raw).hexdigest()}
  with self.assertRaisesRegex(ValueError,'Partial source'):
   mod.validate_acquisition(meta,raw,False,Path('audit.partial.json'))
  with self.assertRaisesRegex(ValueError,'Partial source'):
   mod.validate_acquisition(meta,raw,True,Path('audit.json'))
  mod.validate_acquisition(meta,raw,True,Path('audit.partial.json'))
  with self.assertRaisesRegex(ValueError,'Mismatched'):
   mod.validate_acquisition(meta,b'changed',True,Path('audit.partial.json'))
if __name__=='__main__':unittest.main()
