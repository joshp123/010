"""Written by AI on 2026-10-25 by model GPT-6.1 Sol. Merge owned metadata."""
import fcntl,hashlib,json
from pathlib import Path
REPO=Path(__file__).resolve().parents[2]
DATA=REPO.parent
SCENE=DATA/'scene/v1'
DEBUG=DATA/'renders/debug-buildings'

def main():
 with (SCENE/'.manifest.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  path=SCENE/'manifest.json';j=json.loads(path.read_text())
  for area in ['core','m0']:
   report=json.loads((SCENE/f'buildings-{area}-report.json').read_text())
   j.setdefault('buildings',{})[area]={k:v for k,v in report.items() if k!='tiles'}
   for tile,record in report['tiles'].items():j['tiles'].setdefault(tile,{}).update(record)
  j['objects']={}
  for area in ['core','m0']:
   report=json.loads((SCENE/f'objects-{area}-report.json').read_text());j['objects'][area]=report
   for dataset,record in report['datasets'].items():
    if area=='m0':j['sources'][dataset]={'manifest':record['source_manifest'],'sha256':record['source_manifest_sha256']}
   for tile,counts in report['tiles'].items():
    output=SCENE/'tiles'/tile/'objects.json';j['tiles'][tile]['objects']={'counts':counts,'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}
  for dataset in ['coordinate-grids','debug-buildings-ortho']:
   source=DATA/'sources'/dataset/'2026-10-25/manifest.json'
   if source.exists():j['sources'][dataset]={'manifest':str(source),'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
  j['buildings']['coordinates']={'horizontal':'ETRS89 interpretation of municipal ECEF; real NSGI RDNAPTRANS2018 grid','vertical':'Municipal exporter encoded NAP as geodetic height. Preserve decoded height; do not subtract geoid again.','reference_check':json.loads((Path(__file__).parent/'transform-check.json').read_text()),'building_height_check':json.loads((Path(__file__).parent/'transform-check-building-heights.json').read_text())}
  measurement=DEBUG/'alignment-measurement.json'
  if measurement.exists():j['buildings']['alignment']={'measurement':json.loads(measurement.read_text()),'limitation':'Low-roof sample is within 0.3 m. Tall northern roof differs by about 1.08 m in the aerial. Roof lean and source age are plausible causes, not established causes. No global offset applied. Uniform 0.3 m source-to-aerial agreement is not established.'}
  j['buildings']['debug_images']={p.name:{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(DEBUG.glob('*.png')) if p.name.startswith(('overlay-','oblique-','alignment-'))}
  j['buildings']['code_files']={str(p.relative_to(REPO)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((REPO/'pipeline/buildings').glob('*')) if p.suffix in ['.py','.mjs','.md']}
  j['buildings']['rebuild']='devenv shell -- python pipeline/buildings/rebuild.py'
  temp=path.with_suffix('.buildings-final.tmp');temp.write_text(json.dumps(j,indent=2));temp.replace(path)
 print('Merged building, object, transform and debug metadata into',path)
if __name__=='__main__':main()
