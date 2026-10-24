#!/usr/bin/env python3
"""Bounded old/current literal OST identity check from retained source bytes."""
import importlib.util,json,gzip,urllib.request,datetime,sys
from pathlib import Path
from urllib.parse import urljoin
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'source-data/tank-reconciliation';RAW=OUT/'raw';RAW.mkdir(parents=True,exist_ok=True);BASE='https://www.3drotterdam.nl/datasource-data/c70023a7-2878-41e9-bb81-a7c454bc310a/'
s=importlib.util.spec_from_file_location('m',ROOT/'scripts/prepare-building-appearance.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
e=json.loads((ROOT/'source-data/current-tank-evidence/inspection.json').read_text());bounds=e['sourceNode']['boundingVolume']['region'];wanted=set(e['batchTable']['id']);selected=[];evidence=[]
def fetch(url):
 p=RAW/(url.removeprefix(BASE).replace('/','_')+'.gz');meta=p.with_suffix('.json')
 if p.exists():b=gzip.decompress(p.read_bytes());assert m.digest(b)==json.loads(meta.read_text())['sha256']
 else:
  if '--acquire' not in sys.argv:raise RuntimeError('Missing retained '+url)
  with urllib.request.urlopen(url,timeout=90) as r:b=r.read();headers=dict(r.headers.items())
  b=gzip.decompress(b) if b[:2]==b'\x1f\x8b' else b;p.write_bytes(gzip.compress(b,mtime=0));meta.write_text(json.dumps({'url':url,'sha256':m.digest(b),'decodedBytes':len(b),'acquiredAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'responseHeaders':headers},indent=2)+'\n');print(url,len(b),flush=True)
 evidence.append(json.loads(meta.read_text()));return b
def walk(n,base):
 r=n.get('boundingVolume',{}).get('region');assert r,'Expected geographic native hierarchy'
 if not (r[0]<=bounds[2] and r[2]>=bounds[0] and r[1]<=bounds[3] and r[3]>=bounds[1]):return
 uri=n.get('content',{}).get('uri',n.get('content',{}).get('url',''))
 if uri.endswith('.json'):
  url=urljoin(base,uri);walk(json.loads(fetch(url))['root'],url)
 elif uri and not n.get('children'):selected.append((urljoin(base,uri),n))
 for c in n.get('children',[]):walk(c,base)
url=BASE+'tileset.json';walk(json.loads(fetch(url))['root'],url);records=[];found=set()
for url,node in selected:
 for d,b,bt,ft in m.b3dm_parts(fetch(url)):
  ids=bt['id'];matched=sorted(wanted.intersection(ids));found.update(matched);records.append({'url':url,'bounds':node['boundingVolume'],'ids':ids,'matchedCurrentOST':matched,'batchAttributes':bt.get('attributes',[])})
report={'currentSource':e['source'],'currentSourceSha256':e['sourceSha256'],'currentIds':sorted(wanted),'oldSourceRoot':BASE+'tileset.json','oldLeaves':records,'matched':sorted(found),'missing':sorted(wanted-found),'identityPolicy':'Exact literal OST equality only. No BAG conversion or spatial-nearest guesses. Geometry changes are not inferred from identifier equality.','evidence':evidence};(OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'leaves':len(records),'matched':len(found),'missing':sorted(wanted-found)}))
