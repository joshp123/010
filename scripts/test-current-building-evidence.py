#!/usr/bin/env python3
"""Independent exact source-to-isolated triangle/image checks."""
import importlib.util,gzip,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('e',ROOT/'scripts/inspect-current-building-evidence.py');e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
d,b,batch,f=next(e.m.b3dm_parts(gzip.decompress((e.OUT/'raw/18_268621_55475.b3dm.gz').read_bytes())))
o,c,a=e.extract(d,b,batch);bid=batch['id'].index('BAG_'+e.BAG);count=0
for mesh in o['meshes']:
 source=d['meshes'][mesh['extras']['sourceMesh']];wanted=[]
 for p in source['primitives']:
  ix=e.m.accessor(d,b,p['indices'])[:,0].reshape(-1,3);ids=e.m.accessor(d,b,p['attributes']['_BATCHID'])[:,0];ix=ix[ids[ix[:,0]]==bid]
  if len(ix):wanted.append((p,ix))
 assert len(wanted)==len(mesh['primitives'])
 for (p,ix),q in zip(wanted,mesh['primitives']):
  j=e.m.accessor(o,c,q['indices'])[:,0].reshape(-1,3)
  for key,ai in q['attributes'].items():np.testing.assert_array_equal(e.m.accessor(d,b,p['attributes'][key])[ix],e.m.accessor(o,c,ai)[j])
  count+=len(ix)
for n,original in zip(o['nodes'],d['nodes']):assert n.get('matrix')==original.get('matrix')
def image_bytes(doc,buf):
 return {buf[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']] for im in doc['images'] for v in [doc['bufferViews'][im['bufferView']]]}
assert image_bytes(o,c)<=image_bytes(d,b)
for entry in json.loads((e.OUT/'pilot-metadata.json').read_text())['sourceEvidence']:assert e.m.digest(gzip.decompress((ROOT/entry['retained']).read_bytes()))==entry['sha256']
assert (e.OUT/'pilot-original.glb').read_bytes()==e.pack(o,c)
print(json.dumps({'triangles':count,'positionNormalUV':'exact per triangle','imageBytes':'exact source bytes','nodeMatrices':'exact','sourceHashes':'verified'}))
