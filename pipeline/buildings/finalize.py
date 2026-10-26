"""Written by AI on 2026-10-25 by model GPT-6.1 Sol. Merge owned metadata."""
import fcntl,hashlib,json
from collections import Counter
from pathlib import Path
REPO=Path(__file__).resolve().parents[2]
DATA=REPO.parent
SCENE=DATA/'scene/v1'
DEBUG=DATA/'renders/debug-buildings'

def refresh_area_reports():
 """Refresh overlapping area metadata from the latest full conversion."""
 latest_path=SCENE/'buildings-m1-report.json'
 if not latest_path.exists():return
 latest=json.loads(latest_path.read_text())
 bag_manifest=DATA/'sources/bag/2026-10-26/manifest.json'
 if bag_manifest.exists():
  raw=bag_manifest.read_bytes();digest=hashlib.sha256(raw).hexdigest();snapshot=bag_manifest.parent/'manifests'/f'{digest}.json';snapshot.parent.mkdir(exist_ok=True);snapshot.write_bytes(raw)
  latest['sources']['bag']={'manifest':str(snapshot),'sha256':digest}
 # Feature detail lives in GLB extras; reports retain aggregate coverage only.
 from build import unpack_glb
 for tile,record in latest['tiles'].items():
  raw=(SCENE/'tiles'/tile/'buildings.glb').read_bytes()
  record['buildings']['sha256']=hashlib.sha256(raw).hexdigest()
  record['buildings']['features']=unpack_glb(raw)[0]['extras']['features']
  for feature in record['buildings']['features']:feature['tile']=tile
 for area in ['core','m0','m1']:
  path=SCENE/f'buildings-{area}-report.json'
  if not path.exists():continue
  report=latest.copy() if area=='m1' else json.loads(path.read_text())
  x0,y0,x1,y1=report['bounds']
  records={tile:record for tile,record in latest['tiles'].items() if x0<=int(tile.split('_')[0][1:])<x1 and y0<=int(tile.split('_')[1][1:])<y1}
  report['tiles']=records;report['sources']=latest['sources'];report['code_sha256']=latest['code_sha256']
  if area!='m1':report['reconciled_from_area']='m1'
  features=[f for r in records.values() for f in r['buildings']['features'] if f['kind']=='building']
  report['bag_coverage']={'buildings':len(features),'matched':sum(f.get('bag',{}).get('bag_coverage')=='complete' for f in features),'year':sum(f.get('year') is not None for f in features),'status':sum(f.get('status') is not None for f in features),'use_resolved':sum(f.get('bag',{}).get('bag_coverage')=='complete' for f in features),'with_use':sum(bool(f.get('use')) for f in features),'storeys_stated':0}
  report['bag_coverage']['status_counts']=dict(Counter(f.get('status') or 'unavailable' for f in features))
  report['bag_coverage']['zero_vbo']=sum(f.get('bag',{}).get('vbo_count')==0 for f in features)
  report['bag_coverage']['unavailable_ids']=[f['bag_id'] for f in features if f.get('bag',{}).get('bag_coverage')!='complete']
  report['largest_without_photo']=sorted((f for f in features if f['photo_facade_area_m2']==0),key=lambda f:f['facade_area_m2'],reverse=True)[:20]
  report['totals']={key:sum(r['buildings'][key] for r in records.values()) for key in ['triangles','texture_bytes','facade_area_m2','photo_facade_area_m2','image_bound_facade_area_m2','degenerate_uv_facade_area_m2']}
  report['totals']['photo_facade_fraction']=report['totals']['photo_facade_area_m2']/report['totals']['facade_area_m2']
  report['totals']['counts']={source:sum(r['buildings']['by_source'][source] for r in records.values()) for source in ['textured2018','lod2','bridges']}
  # Do not duplicate per-VBO provenance for every feature in the shared manifest.
  compact=json.loads(json.dumps(report))
  for record in compact['tiles'].values():record['buildings'].pop('features',None)
  for feature in compact['largest_without_photo']:feature.pop('bag',None)
  path.write_text(json.dumps(compact,indent=2))

def main():
 refresh_area_reports()
 with (SCENE/'.manifest.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  path=SCENE/'manifest.json';j=json.loads(path.read_text())
  for area in ['core','m0','m1']:
   if not (SCENE/f'buildings-{area}-report.json').exists():continue
   report=json.loads((SCENE/f'buildings-{area}-report.json').read_text())
   j.setdefault('buildings',{})[area]={k:v for k,v in report.items() if k!='tiles'}
   for tile,record in report['tiles'].items():j['tiles'].setdefault(tile,{}).update(record)
  j['objects']={}
  for area in ['core','m0','m1']:
   if not (SCENE/f'objects-{area}-report.json').exists():continue
   report=json.loads((SCENE/f'objects-{area}-report.json').read_text());j['objects'][area]=report
   for dataset,record in report['datasets'].items():
    if area in ['m0','m1']:j['sources'][dataset]={'manifest':record['source_manifest'],'sha256':record['source_manifest_sha256']}
   for tile,counts in report['tiles'].items():
    output=SCENE/'tiles'/tile/'objects.json';j['tiles'][tile]['objects']={'counts':counts,'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}
  for dataset in ['coordinate-grids','debug-buildings-ortho']:
   source=DATA/'sources'/dataset/'2026-10-25/manifest.json'
   if source.exists():j['sources'][dataset]={'manifest':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
  j['buildings']['coordinates']={'horizontal':'ETRS89 interpretation of municipal ECEF; real NSGI RDNAPTRANS2018 grid','vertical':'Municipal exporter encoded NAP as geodetic height. Preserve decoded height; do not subtract geoid again.','reference_check':json.loads((Path(__file__).parent/'transform-check.json').read_text()),'building_height_check':json.loads((Path(__file__).parent/'transform-check-building-heights.json').read_text())}
  measurement=DEBUG/'alignment-measurement.json'
  if measurement.exists():j['buildings']['alignment']={'measurement':json.loads(measurement.read_text()),'limitation':'Low-roof sample is within 0.3 m. Tall northern roof differs by about 1.08 m in the aerial. Roof lean and source age are plausible causes, not established causes. No global offset applied. Uniform 0.3 m source-to-aerial agreement is not established.'}
  j['buildings']['debug_images']={p.name:{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(DEBUG.glob('*.png')) if p.name.startswith(('overlay-','oblique-','alignment-'))}
  j['buildings']['landmark_checks']={p.name:{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(DEBUG.glob('landmark-*.json'))}
  audit=DATA/'sources/bag/2026-10-26/scene-m1-facts-audit.json'
  if audit.exists():j['buildings']['m1']['bag_audit']={'path':str(audit),'sha256':hashlib.sha256(audit.read_bytes()).hexdigest()}
  validation=SCENE/'buildings-m1-validation.json'
  if validation.exists():j['buildings']['m1']['validation']={'path':str(validation),'sha256':hashlib.sha256(validation.read_bytes()).hexdigest()}
  j['buildings']['code_files']={str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((REPO/'pipeline/buildings').glob('*')) if p.suffix in ['.py','.mjs','.md']}
  j['buildings']['rebuild']='devenv shell -- python pipeline/buildings/rebuild.py --area m1 --workers 8'
  temp=path.with_suffix('.buildings-final.tmp');temp.write_text(json.dumps(j,indent=2));temp.replace(path)
 print('Merged building, object, transform and debug metadata into',path)
if __name__=='__main__':main()
