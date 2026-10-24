#!/usr/bin/env python3
"""Verify texture-only LOD and inherited RTC against native candidate."""
import importlib.util,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('m',ROOT/'scripts/prepare-building-appearance.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
manifest=json.loads((m.OUTPUT/'manifest.json').read_text());tiles=json.loads((m.OUTPUT/'tileset.json').read_text())['root']['children'];totals={};checked=0
for entry,tile in zip(manifest['entries'],tiles):
 native,nb=m.read_glb((m.OUTPUT/entry['output']).read_bytes());levels=entry['textureLevels']
 assert 'transform' in tile
 for i,level in enumerate(levels):
  doc,binary=m.read_glb((m.OUTPUT/level['output']).read_bytes())
  assert doc['meshes']==native['meshes'] and doc['nodes']==native['nodes']
  assert doc['materials']==native['materials'] and doc['accessors']==native['accessors']
  for ai in range(len(native['accessors'])):assert np.array_equal(m.accessor(native,nb,ai),m.accessor(doc,binary,ai))
  if i<len(levels)-1:
   assert tile['content']['uri']==level['output'] and tile['refine']=='REPLACE'
   if i:assert 'transform' not in tile
   assert tile['geometricError']>levels[i+1]['geometricError']
   if i<len(levels)-2:tile=tile['children'][0]
   else:
    assert {c['content']['uri'] for c in tile['children']}=={b['output'] for b in entry['spatialBuildings']}
    assert all(c['geometricError']==0 and 'transform' not in c for c in tile['children'])
  else:assert level['geometricError']==0
  totals[level['maxTextureSize']]=totals.get(level['maxTextureSize'],0)+level['decodedRgbaBytesIncludingMips'];checked+=1
print(json.dumps({'checkedLevels':checked,'decodedRgbaIncludingMipsByMaxDimension':totals},indent=2))
