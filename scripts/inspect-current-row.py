#!/usr/bin/env python3
"""Retain the exact current Schiedamseweg22 source, independently of Schans."""
import importlib.util,gzip,json,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('e',ROOT/'scripts/inspect-current-building-evidence.py');e=importlib.util.module_from_spec(s);s.loader.exec_module(e)
e.BAG='0599100000671675';e.OUT=ROOT/'source-data/current-row-evidence';e.OUT.mkdir(exist_ok=True);(e.OUT/'raw').mkdir(exist_ok=True)
uri='18/268620/55473.b3dm';p=e.OUT/'raw/18_268620_55473.b3dm.gz'
if not p.exists():
 old=ROOT/'source-data/current-building-evidence/raw/18_268620_55473.b3dm.gz'
 if old.exists():p.write_bytes(old.read_bytes())
 else:
  import sys
  if '--acquire' not in sys.argv:raise RuntimeError('Missing source; use --acquire')
  b=urllib.request.urlopen(e.BASE+uri,timeout=60).read();b=gzip.decompress(b) if b[:2]==b'\x1f\x8b' else b;p.write_bytes(gzip.compress(b,mtime=0))
b=gzip.decompress(p.read_bytes());meta=e.OUT/'pilot-metadata.json'
if meta.exists():assert e.m.digest(b)==json.loads(meta.read_text())['sourceSha256']
d,buf,batch,feature=next(e.m.b3dm_parts(b));o,c,attrs=e.extract(d,buf,batch);o['extras']['source']=uri;(e.OUT/'pilot-original.glb').write_bytes(e.pack(o,c));e.render(o,c,'pilot-view-a.png',[1,.8,1]);e.render(o,c,'pilot-view-b.png',[-1,.8,-1]);meta.write_text(json.dumps({'bagId':e.BAG,'sourceUrl':e.BASE+uri,'sourceSha256':e.m.digest(b),'sourceAttributes':attrs,'featureTable':feature,'license':'CC BY 4.0','attribution':'Gemeente Rotterdam — 3D Rotterdam','licenseEvidence':'../current-building-evidence/catalog-evidence.json','photographyCaptureDate':'Unknown'},indent=2)+'\n');print(json.dumps({'bytes':len(c),'triangles':sum(len(e.m.accessor(o,c,p['indices']))//3 for m in o['meshes'] for p in m['primitives']),'attributes':attrs}))
