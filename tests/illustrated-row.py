#!/usr/bin/env python3
"""Independent original municipal triangles, BAG identity and one-RTC bounds proof."""
import gzip,json,struct,hashlib,importlib.util,collections
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'public/data/illustrated-row'
s=importlib.util.spec_from_file_location('m',ROOT/'scripts/prepare-building-appearance.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
raw=(OUT/'row.glb').read_bytes();n=struct.unpack_from('<I',raw,12)[0];d=json.loads(raw[20:20+n]);b=raw[28+n:];manifest=json.loads((OUT/'manifest.json').read_text());meta=json.loads((ROOT/'source-data/illustrated-row/georeference-and-identities.json').read_text());tile=json.loads((OUT/'tileset.json').read_text())['root']['children'][0];source=gzip.decompress((ROOT/'source-data/current-row-evidence/raw/18_268620_55473.b3dm.gz').read_bytes());assert m.digest(source)==meta['source_decoded_sha256'];a,ab,bt,ft=next(m.b3dm_parts(source));wanted={x['batchId']:x['bagId'].removeprefix('BAG_') for x in meta['batch_identity']}
assert d['nodes'][0]['matrix']==a['nodes'][0]['matrix']==meta['root_node_matrix_column_major'];assert 'CESIUM_RTC' not in json.dumps(d);assert tile['transform'][12:15]==ft['RTC_CENTER']==meta['rtc_ecef_m'];assert set(tile['extras']['bagIds'])==set(wanted.values())
def triangles(doc,buf,source=False):
 result=collections.Counter();count=0
 for mesh in doc['meshes']:
  for p in mesh['primitives']:
   ix=m.accessor(doc,buf,p['indices'])[:,0].reshape(-1,3);ids=m.accessor(doc,buf,p['attributes']['_BATCHID'])[:,0]
   for t in ix:
    bid=int(ids[t[0]])
    if source and bid not in wanted:continue
    assert np.all(ids[t]==bid)
    if not source:assert mesh['extras']['bagId']==wanted[bid] and p['extras']['bagId']==wanted[bid]
    content=b''.join(m.accessor(doc,buf,p['attributes'][k])[t].tobytes() for k in ('POSITION','NORMAL','TEXCOORD_0') if k in p['attributes']);result[(bid,hashlib.sha256(content).hexdigest())]+=1;count+=1
 return result,count
assert triangles(d,b)==triangles(a,ab,True);assert triangles(d,b)[1]==678
points=[];yz=np.array([[1,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1]])
def walk(i,parent):
 node=d['nodes'][i];mat=parent@np.array(node.get('matrix',np.eye(4).T.ravel())).reshape(4,4).T
 if 'mesh'in node:
  for p in d['meshes'][node['mesh']]['primitives']:
   v=m.accessor(d,b,p['attributes']['POSITION']);points.extend((np.c_[v,np.ones(len(v))]@(yz@mat).T)[:,:3])
 for c in node.get('children',[]):walk(c,mat)
for i in d['scenes'][d.get('scene',0)]['nodes']:walk(i,np.eye(4))
box=np.array(tile['boundingVolume']['box']);axes=box[3:].reshape(3,3,order='F');assert np.all(abs((points-box[:3])@np.linalg.inv(axes).T)<=1+1e-7)
for image in manifest['textures']:assert m.digest((OUT/image['uri']).read_bytes())==image['sha256']
print(json.dumps({'exactOriginalMunicipalTriangles':678,'bags':len(wanted),'unchangedPaintedPNGs':len(manifest['textures']),'rootMatrix':'exact','RTC':'once in tile transform','nativeBounds':'all positions inside tight source-frame OBB'}))
