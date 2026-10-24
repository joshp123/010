import contextlib,io,runpy,unittest
from pathlib import Path
from shapely.geometry import LineString
ROOT=Path(__file__).resolve().parents[1]
class BlaakSurfaceTest(unittest.TestCase):
 def test_actual_source_and_candidate(self):
  with contextlib.redirect_stdout(io.StringIO()):audit=runpy.run_path(str(ROOT/'scripts/audit-blaak-surface.py'))
  samples={s['vehicleId']:s for s in audit['report']}
  self.assertEqual(samples[2]['laneSurfaces'][0]['id'],'16524553')
  self.assertEqual(samples[2]['centrelineSurfaces'][0]['id'],'14702898')
  self.assertEqual(samples[17]['laneSurfaces'][0]['id'],'14702898')
  self.assertEqual(samples[19]['centrelineSurfaces'][0]['id'],'14198208')
  self.assertEqual(samples[23]['centrelineSurfaces'][0]['id'],'16524553')
  self.assertEqual(audit['access']['AUTO_H'],'J');self.assertEqual(audit['access']['AUTO_T'],'J')
  self.assertLess(LineString(audit['candidate']).difference(audit['carriageway'].buffer(-2.2)).length,1e-5)
  self.assertEqual(audit['candidate'][0],audit['original'][0].tolist())
  affected={x['roadId'] for x in audit['adjacent'] if any(c['shiftMetres']>.1 for c in x['changes'])}
  self.assertEqual(affected,{185274103,185274085,600909887},'shared junction shift must not be activated on only one edge')
if __name__=='__main__':unittest.main()
