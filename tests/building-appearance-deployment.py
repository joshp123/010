#!/usr/bin/env python3
"""Actual generated output asset limit + standard external texture references."""
from pathlib import Path
import json,struct,hashlib
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'public/data/current-building-appearance';limit=25*1024*1024;files=[p for p in OUT.rglob('*') if p.is_file() and p.suffix in ('.glb','.png','.jpg','.json')]
for p in files:assert p.stat().st_size<=limit,(p,p.stat().st_size)
refs=0
for p in OUT.glob('*.glb'):
 raw=p.read_bytes();n=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+n])
 for im in doc.get('images',[]):
  if 'uri' not in im:continue
  assert 'bufferView' not in im;target=OUT/im['uri'];assert target.is_file() and target.stat().st_size<=limit;assert target.name=='texture-'+hashlib.sha256(target.read_bytes()).hexdigest()+'.png';refs+=1
manifest=json.loads((OUT/'manifest.json').read_text());assert manifest['assetLimitBytes']==limit
for t in manifest['externalTextures']:assert (OUT/t['uri']).stat().st_size==t['bytes'] and hashlib.sha256((OUT/t['uri']).read_bytes()).hexdigest()==t['sha256']
print(json.dumps({'assets':len(files),'externalTextureReferences':refs,'largestAssetBytes':max(p.stat().st_size for p in files),'limitBytes':limit}))
