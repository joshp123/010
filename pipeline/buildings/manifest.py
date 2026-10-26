"""Written by AI on 2026-10-25 by model GPT-6.1 Sol. Narrow scene manifest merge."""
import fcntl, hashlib, json
from pathlib import Path
ROOT=Path('/Volumes/Josh Extreme Pro USB4 4TB/010/scene/v1')
def merge_buildings(report):
 report=dict(report)
 report['tiles']={tile:{**record,'buildings':{key:value for key,value in record['buildings'].items() if key!='features'}} for tile,record in report['tiles'].items()}
 if 'largest_without_photo' in report:report['largest_without_photo']=[{key:value for key,value in feature.items() if key!='bag'} for feature in report['largest_without_photo']]
 ROOT.mkdir(parents=True,exist_ok=True)
 with (ROOT/'.manifest.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  path=ROOT/'manifest.json';j=json.loads(path.read_text()) if path.exists() else {}
  j.setdefault('crs',{'horizontal':'EPSG:28992','vertical':'EPSG:5709','compound':'EPSG:7415'})
  j.setdefault('grid',{'size_m':250,'tile_name':'x{xmin}_y{ymin}','gltf_axes':{'X':'RD east minus tile xmin','Y':'NAP metres','Z':'negative RD north offset from tile ymin'}})
  j.setdefault('area',{})[report['area']]={'bounds_rd':report['bounds']}
  # Preserve whichever common tile-list representation the ground run chose.
  tiles=j.setdefault('tiles',{})
  if isinstance(tiles,list):
   for tile,record in report['tiles'].items():
    existing=next((r for r in tiles if isinstance(r,dict) and r.get('id',r.get('name'))==tile),None)
    if existing is None:tiles.append({'id':tile,**record})
    else:existing.update(record)
  else:
   for tile,record in report['tiles'].items():tiles.setdefault(tile,{}).update(record)
  j.setdefault('sources',{}).update(report['sources'])
  j.setdefault('buildings',{})[report['area']]={k:v for k,v in report.items() if k!='tiles'}
  objects=ROOT/'objects-m1-report.json'
  if not objects.exists():objects=ROOT/'objects-m0-report.json'
  if not objects.exists():objects=ROOT/'objects-core-report.json'
  if objects.exists():j['objects']=json.loads(objects.read_text())
  temp=path.with_suffix('.buildings.tmp');temp.write_text(json.dumps(j,indent=2));temp.replace(path)
