#!/usr/bin/env python3
"""Place the supplied illustrated row unchanged; add exact per-draw BAG identities."""
import argparse,copy,hashlib,importlib.util,json,shutil,struct,tempfile,zipfile
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'public/data/illustrated-row';RETAINED=ROOT/'source-data/illustrated-row';SOURCE_ARCHIVE='010-current-row-runtime-candidate.zip'
s=importlib.util.spec_from_file_location('m',ROOT/'scripts/prepare-building-appearance.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def read(raw):
 size=struct.unpack_from('<I',raw,12)[0];return json.loads(raw[20:20+size]),raw[28+size:]
def main():
 ap=argparse.ArgumentParser();ap.add_argument('input',nargs='?',default=str(ROOT/'work/illustrated-row-review'));args=ap.parse_args();source=Path(args.input);archive_hash=None
 with tempfile.TemporaryDirectory() as tmp:
  if source.is_file():
   archive_hash=m.digest(source.read_bytes())
   with zipfile.ZipFile(source) as z:
    for name in z.namelist():
     target=Path(tmp)/name
     if not target.resolve().is_relative_to(Path(tmp).resolve()):raise ValueError('Unsafe archive path')
    z.extractall(tmp)
   source=next(Path(tmp).rglob('georeference-and-identities.json')).parent
  meta=json.loads((source/'georeference-and-identities.json').read_text());raw=(source/'row-review.glb').read_bytes();a,b=read(raw);assert a['nodes'][0]['matrix']==meta['root_node_matrix_column_major'];assert a.get('extensions',{}).get('CESIUM_RTC',{}).get('center')==meta['rtc_ecef_m']
  mapping={x['batchId']:x['bagId'].removeprefix('BAG_') for x in meta['batch_identity']};d=copy.deepcopy(a);d['meshes']=[];d['accessors']=[];d['bufferViews']=[];payload=bytearray();meshmap={};triangle_count=0
  def view(data,target):
   payload.extend(b'\0'*((-len(payload))%4));v={'buffer':0,'byteOffset':len(payload),'byteLength':len(data),'target':target};d['bufferViews'].append(v);payload.extend(data);return len(d['bufferViews'])-1
  def attr(values,template,target):
   ac={k:v for k,v in template.items() if k not in ('bufferView','byteOffset','count','min','max')};ac.update(bufferView=view(values.tobytes(),target),count=len(values))
   if 'min'in template:ac['min']=values.min(0).tolist()
   if 'max'in template:ac['max']=values.max(0).tolist()
   d['accessors'].append(ac);return len(d['accessors'])-1
  for mi,mesh in enumerate(a['meshes']):
   meshmap[mi]=[]
   for pi,p in enumerate(mesh['primitives']):
    assert p.get('mode',4)==4;ids=m.accessor(a,b,p['attributes']['_BATCHID'])[:,0];ix=(m.accessor(a,b,p['indices'])[:,0] if 'indices'in p else np.arange(len(ids))).reshape(-1,3);assert np.all(ids[ix]==ids[ix[:,0],None])
    for bid in sorted(set(ids[ix[:,0]].astype(int))):
     assert bid in mapping;chosen=ix[ids[ix[:,0]]==bid];used,remapped=np.unique(chosen.ravel(),return_inverse=True);q=copy.deepcopy(p);q['attributes']={}
     for semantic,ai in p['attributes'].items():
      values=np.ascontiguousarray(m.accessor(a,b,ai)[used]);q['attributes'][semantic]=attr(values,a['accessors'][ai],34962);np.testing.assert_array_equal(values[remapped.reshape(-1,3)],m.accessor(a,b,ai)[chosen])
     q['indices']=attr(remapped.astype('<u2').reshape(-1,1),{'componentType':5123,'type':'SCALAR'},34963);q.setdefault('extras',{})['bagId']=mapping[bid];meshmap[mi].append(len(d['meshes']));d['meshes'].append({'name':'BAG_'+mapping[bid],'primitives':[q],'extras':{'bagId':mapping[bid],'sourceMesh':mi,'sourcePrimitive':pi,'sourceBatchId':int(bid)}});triangle_count+=len(chosen)
  for node in list(d['nodes']):
   if 'mesh'not in node:continue
   mi=node.pop('mesh');children=node.setdefault('children',[])
   for newmesh in meshmap[mi]:children.append(len(d['nodes']));d['nodes'].append({'mesh':newmesh,'extras':{'bagId':d['meshes'][newmesh]['extras']['bagId']}})
  d.get('extensions',{}).pop('CESIUM_RTC',None)
  if not d.get('extensions'):d.pop('extensions',None)
  for key in ['extensionsUsed','extensionsRequired']:
   if key in d:d[key]=[x for x in d[key] if x!='CESIUM_RTC']
   if key in d and not d[key]:d.pop(key)
  d.setdefault('extras',{}).update(bagIds=list(mapping.values()),sourceArtifactArchive=SOURCE_ARCHIVE,appearanceStatus='Illustrated row review candidate; not accepted production art')
  points=[];yz=np.array([[1,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1]])
  def walk(i,parent):
   node=d['nodes'][i];mat=parent@np.array(node.get('matrix',np.eye(4).T.ravel())).reshape(4,4).T
   if 'mesh'in node:
    for p in d['meshes'][node['mesh']]['primitives']:
     pos=m.accessor(d,payload,p['attributes']['POSITION']);points.extend((np.c_[pos,np.ones(len(pos))]@(yz@mat).T)[:,:3])
   for child in node.get('children',[]):walk(child,mat)
  for node in d['scenes'][d.get('scene',0)]['nodes']:walk(node,np.eye(4))
  points=np.array(points);frame=(yz@np.array(a['nodes'][0]['matrix']).reshape(4,4).T)[:3,:3];assert np.allclose(frame.T@frame,np.eye(3),atol=1e-10);aligned=points@frame;lo,hi=aligned.min(0),aligned.max(0);centre=((lo+hi)/2)@frame.T;half=(hi-lo)/2+.001;box=[*centre,*(frame*half).flatten(order='F')];rtc=meta['rtc_ecef_m'];world=points+rtc;wc=(world.min(0)+world.max(0))/2;radius=float(np.max(np.linalg.norm(world-wc,axis=1)))+.001
  OUT.mkdir(parents=True,exist_ok=True);RETAINED.mkdir(parents=True,exist_ok=True);(OUT/'row.glb').write_bytes(m.pack_glb(d,payload));textures=[]
  for item in meta['textures']:
   data=(source/item['uri']).read_bytes();assert m.digest(data)==item['sha256'];target=OUT/item['uri'];target.parent.mkdir(exist_ok=True);target.write_bytes(data);textures.append(item)
  transform=[1,0,0,0,0,1,0,0,0,0,1,0,*rtc,1];tiles={'asset':{'version':'1.0','gltfUpAxis':'Y'},'geometricError':0,'root':{'boundingVolume':{'sphere':[*wc,radius]},'geometricError':0,'refine':'REPLACE','children':[{'boundingVolume':{'box':box},'transform':transform,'geometricError':0,'content':{'uri':'row.glb'},'extras':{'bagIds':list(mapping.values())}}]}};(OUT/'tileset.json').write_bytes(m.packed_json(tiles)+b'\n')
  from pyproj import Transformer
  lon,lat,h=Transformer.from_crs(4978,4979,always_xy=True).transform(*world.T)
  manifest={'status':'review only, no art acceptance','sourceArchive':SOURCE_ARCHIVE,'inputArchiveSha256':archive_hash,'inputGLBSha256':m.digest(raw),'sourceMunicipalSha256':meta['source_decoded_sha256'],'outputGLBSha256':m.digest((OUT/'row.glb').read_bytes()),'bagIds':list(mapping.values()),'triangles':triangle_count,'textures':textures,'rootMatrixRetained':True,'rtcApplied':'Once in child 3D Tiles transform; removed CESIUM_RTC extension','boundsLonLatHeight':[np.array([lon,lat,h]).min(1).tolist(),np.array([lon,lat,h]).max(1).tolist()],'changes':'Split source draw indices by exact original _BATCHID; compacted unchanged attribute values; unchanged external painted PNGs and materials; no art filtering'};(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');(RETAINED/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');shutil.copyfile(source/'georeference-and-identities.json',RETAINED/'georeference-and-identities.json');shutil.copyfile(source/'README.md',RETAINED/'artifact-README.md');assert triangle_count==678;print(json.dumps({'triangles':triangle_count,'bags':len(mapping),'meshes':len(d['meshes']),'glbBytes':(OUT/'row.glb').stat().st_size,'bounds':manifest['boundsLonLatHeight']}))
if __name__=='__main__':main()
