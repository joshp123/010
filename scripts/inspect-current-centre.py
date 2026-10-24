#!/usr/bin/env python3
"""Bounded centre-source acquisition and original-geometry comparison; no runtime changes."""
import argparse,copy,datetime,gzip,hashlib,importlib.util,io,json,math,struct,urllib.request
from pathlib import Path
from urllib.parse import urljoin
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'source-data/current-centre-evidence';RAW=OUT/'raw';BAG='0599100000753300';POINT=[math.radians(x) for x in [4.4875135,51.905083]]
spec=importlib.util.spec_from_file_location('current',ROOT/'scripts/inspect-current-building-evidence.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c);m=c.m
BASE=c.BASE

def fetch(url,acquire):
 name=url.removeprefix(BASE).replace('/','_');p=RAW/(name+'.gz');meta=RAW/(name+'.json')
 if p.exists():
  b=gzip.decompress(p.read_bytes());assert m.digest(b)==json.loads(meta.read_text())['sha256'];return b
 if not acquire:raise RuntimeError(f'Missing {p}; run --acquire')
 cached=ROOT/'source-data/current-building-evidence/raw'/(name+'.gz')
 if cached.exists():b=gzip.decompress(cached.read_bytes());headers={};origin='Retained current municipal source copy'
 else:
  with urllib.request.urlopen(url,timeout=90) as r:b=r.read();headers=dict(r.headers.items())
  b=gzip.decompress(b) if b[:2]==b'\x1f\x8b' else b;origin='Public download'
 p.write_bytes(gzip.compress(b,mtime=0));meta.write_text(json.dumps({'url':url,'sha256':m.digest(b),'decodedBytes':len(b),'acquiredAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'responseHeaders':headers,'origin':origin,'license':'CC BY4.0','attribution':'Gemeente Rotterdam —3D Rotterdam','licenseEvidence':'../current-building-evidence/catalog-evidence.json'},indent=2)+'\n');print(name,len(b),flush=True);return b

def select(acquire):
 result=[]
 def walk(node,url):
  region=node['boundingVolume'].get('region');x,y=POINT
  if region and not(region[0]<=x<=region[2] and region[1]<=y<=region[3]):return
  assert not node.get('transform'),'Source index transform requires explicit composition'
  uri=node.get('content',{}).get('uri','')
  if uri.endswith('.json'):
   u=urljoin(url,uri);walk(json.loads(fetch(u,acquire))['root'],u)
  elif uri and not node.get('children'):result.append({'url':urljoin(url,uri),'node':node})
  for child in node.get('children',[]):walk(child,url)
 url=BASE+'tileset.json';walk(json.loads(fetch(url,acquire))['root'],url);return result

def subset_legacy(doc):
 keep={i for i,mesh in enumerate(doc['meshes']) if mesh.get('extras',{}).get('bagId')==BAG};mapping={old:new for new,old in enumerate(sorted(keep))};doc=copy.deepcopy(doc);doc['meshes']=[mesh for i,mesh in enumerate(doc['meshes']) if i in keep]
 for node in doc['nodes']:
  if 'mesh' in node:
   index=node.pop('mesh')
   if index in mapping:node['mesh']=mapping[index]
 return doc

def verify_extraction(source,binary,batch,isolated,compact):
 bid=batch['id'].index('BAG_'+BAG);triangles=0
 for mesh in isolated['meshes']:
  originals=source['meshes'][mesh['extras']['sourceMesh']]['primitives'];selected=[]
  for p in originals:
   ids=m.accessor(source,binary,p['attributes']['_BATCHID'])[:,0];index=(m.accessor(source,binary,p['indices'])[:,0] if 'indices' in p else np.arange(len(ids))).reshape(-1,3);chosen=index[ids[index[:,0]]==bid].ravel()
   if len(chosen):selected.append((p,chosen))
  assert len(selected)==len(mesh['primitives'])
  for (p,chosen),q in zip(selected,mesh['primitives']):
   index=m.accessor(isolated,compact,q['indices'])[:,0];assert len(chosen)==len(index);triangles+=len(index)//3
   for key,ai in p['attributes'].items():
    if key=='_BATCHID':continue
    old=m.accessor(source,binary,ai)[chosen];new=m.accessor(isolated,compact,q['attributes'][key])[index];assert old.dtype==new.dtype and np.array_equal(old,new)
 for old,new in zip(source['nodes'],isolated['nodes']):assert {k:v for k,v in old.items() if k not in ('mesh','extras')}=={k:v for k,v in new.items() if k not in ('mesh','extras')}
 def image_hashes(d,b):
  result=[]
  for im in d.get('images',[]):
   v=d['bufferViews'][im['bufferView']];start=v.get('byteOffset',0);result.append(m.digest(b[start:start+v['byteLength']]))
  return result
 assert set(image_hashes(isolated,compact))<=set(image_hashes(source,binary))
 return {'expandedTrianglesExact':triangles,'allOriginalAttributesExact':True,'sourceNodeTransformsExact':True,'embeddedImageBytesExact':True}

def render_inputs(doc,binary):
 """Render-only constant-colour texels for original untextured primitives."""
 d=copy.deepcopy(doc);data=bytearray(binary)
 def view(raw):
  data.extend(b'\0'*((-len(data))%4));d['bufferViews'].append({'buffer':0,'byteOffset':len(data),'byteLength':len(raw)});data.extend(raw);return len(d['bufferViews'])-1
 for mesh in d['meshes']:
  for p in mesh['primitives']:
   mat=d['materials'][p['material']]['pbrMetallicRoughness']
   if 'TEXCOORD_0' not in p['attributes']:
    n=d['accessors'][p['attributes']['POSITION']]['count'];v=view(np.zeros((n,2),dtype='<f4').tobytes());d['accessors'].append({'bufferView':v,'componentType':5126,'count':n,'type':'VEC2'});p['attributes']['TEXCOORD_0']=len(d['accessors'])-1
   if 'baseColorTexture' not in mat:
    rgb=tuple(round(x*255) for x in mat.get('baseColorFactor',[.65,.65,.62])[:3]);buf=io.BytesIO();Image.new('RGB',(1,1),rgb).save(buf,format='PNG');d.setdefault('images',[]).append({'bufferView':view(buf.getvalue()),'mimeType':'image/png'});d.setdefault('textures',[]).append({'source':len(d['images'])-1});mat['baseColorTexture']={'index':len(d['textures'])-1}
 return d,bytes(data)

def world_geometry(doc,binary,rtc):
 yz=np.array([[1,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1]]);shift=np.eye(4);shift[:3,3]=rtc;triangles=[]
 def visit(i,parent):
  n=doc['nodes'][i];mat=parent@np.array(n.get('matrix',np.eye(4).T.ravel())).reshape(4,4).T
  if 'mesh' in n:
   for p in doc['meshes'][n['mesh']]['primitives']:
    v=m.accessor(doc,binary,p['attributes']['POSITION']);idx=m.accessor(doc,binary,p['indices'])[:,0].reshape(-1,3);xyz=(np.c_[v,np.ones(len(v))]@(shift@yz@mat).T)[:,:3];triangles.extend(xyz[idx])
  for child in n.get('children',[]):visit(child,mat)
 for root in doc['scenes'][doc.get('scene',0)]['nodes']:visit(root,np.eye(4))
 return np.asarray(triangles)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--acquire',action='store_true');args=ap.parse_args();RAW.mkdir(parents=True,exist_ok=True);c.OUT=OUT;c.BAG=BAG
 leaves=select(args.acquire);found=None
 for entry in leaves:
  raw=fetch(entry['url'],args.acquire)
  for doc,binary,batch,feature in m.b3dm_parts(raw):
   if 'BAG_'+BAG in batch.get('id',[]):found=(entry,raw,doc,binary,batch,feature);break
  if found:break
 if not found:raise ValueError('Requested BAG absent from selected source leaf; inspect bounded neighbouring leaves')
 entry,raw,doc,binary,batch,feature=found
 isolated,compact,attrs=c.extract(doc,binary,batch);isolated['extras']['source']=entry['url'];work=ROOT/'work/current-centre-evidence';work.mkdir(parents=True,exist_ok=True);(work/'current-original.glb').write_bytes(c.pack(isolated,compact))
 original=gzip.decompress((ROOT/'source-data/building-appearance/raw/17_134339_27739.cmpt.gz').read_bytes());m.STYLE='source'
 for ld,lb,lbt,lf in m.b3dm_parts(original):
  if any(str(x.get('gebouwnummer'))==BAG for x in lbt.get('attributes',[])):break
 converted,transform,ids,n=m.convert(ld,lb,lbt,lf,'');size=struct.unpack_from('<I',converted,12)[0];legacy=subset_legacy(json.loads(converted[20:20+size]));legacy_binary=converted[28+size:]
 # Source-only materials/UV, same local Y-up camera directions; no styled presets.
 for label,d,b in [('legacy',legacy,legacy_binary),('current',isolated,compact)]:
  renderdoc,renderbin=render_inputs(d,b)
  for suffix,direction in [('a',[1,.45,1]),('b',[-1,.45,-1]),('roof',[1,3,1])]:c.render(renderdoc,renderbin,label+'-'+suffix+'.png',direction)
 def stats(d,b):
  ps=[p for mesh in d['meshes'] for p in mesh['primitives']];return {'triangles':sum(m.accessor(d,b,p['indices']).size//3 for p in ps),'primitives':len(ps),'texturedPrimitives':sum('baseColorTexture' in d['materials'][p['material']].get('pbrMetallicRoughness',{}) for p in ps)}
 report={'extractionVerification':verify_extraction(doc,binary,batch,isolated,compact),'bagId':BAG,'currentSource':entry['url'],'currentSourceSha256':m.digest(raw),'currentFeatureTable':feature,'currentSourceAttributes':attrs,'current':stats(isolated,compact),'legacy':stats(legacy,legacy_binary),'legacySource':'source-data/building-appearance/raw/17_134339_27739.cmpt.gz','legacySourceSha256':m.digest(original),'license':'Current municipal source CC BY4.0; legacy source attribution/terms retained separately','photographyDate':'Not established. creationDate is model attribute, not flight date.','sourceGeometryPolicy':'Original positions/normals/UVs and node transforms retained in isolated current GLB, original source B3DM retained. No artistic interpretation.'}
 from pyproj import Transformer
 from scipy.spatial import cKDTree
 oldworld=world_geometry(legacy,legacy_binary,transform[12:15]);newworld=world_geometry(isolated,compact,feature['RTC_CENTER']);oldpoints=oldworld.reshape(-1,3);newpoints=newworld.reshape(-1,3)
 geo=Transformer.from_crs(4978,4979,always_xy=True)
 geometry={}
 for label,points in [('legacy',oldpoints),('current',newpoints)]:
  lon,lat,h=geo.transform(points[:,0],points[:,1],points[:,2]);geometry[label]={'longitudeBounds':[float(min(lon)),float(max(lon))],'latitudeBounds':[float(min(lat)),float(max(lat))],'numericHeightBounds':[float(min(h)),float(max(h))]}
 distances=cKDTree(oldpoints).query(newpoints)[0];geometry['currentVertexToLegacyVertexMetres']={'median':float(np.median(distances)),'max':float(max(distances)),'caution':'Vertex distance includes tessellation changes; not a surveyed surface discrepancy.'};geometry['expandedTrianglesEqualWithinMillimetre']=oldworld.shape==newworld.shape and bool(np.allclose(oldworld,newworld,atol=.001,rtol=0));report['worldGeometryComparison']=geometry
 report['atlasDimensions']={'legacy':[list(im.shape[:2][::-1]) for im in c.images(legacy,legacy_binary)],'current':[list(im.shape[:2][::-1]) for im in c.images(isolated,compact)]}
 (OUT/'comparison.json').write_text(json.dumps(report,indent=2)+'\n')
 sheet=Image.new('RGB',(1400,1890),'#ebebeb');draw=ImageDraw.Draw(sheet)
 for row,suffix in enumerate(['a','b','roof']):
  for col,label in enumerate(['legacy','current']):sheet.paste(Image.open(OUT/(label+'-'+suffix+'.png')),(col*700,row*630+30));draw.text((col*700+8,row*630+8),label.upper()+' original source — '+suffix,fill='black')
 sheet.save(OUT/'comparison.jpg',quality=94);print(json.dumps(report,indent=2))
if __name__=='__main__':main()
