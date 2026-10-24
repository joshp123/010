#!/usr/bin/env python3
"""Package a bound artwork handoff with exact geometry and lossless native texels."""
import argparse,copy,importlib.util,json,re,struct
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('source',ROOT/'scripts/prepare-building-appearance.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.EDITION='current'

def write_json(path,data):path.write_text(json.dumps(data,indent=2)+'\n')
def safe_file(folder,name):
 p=(folder/name).resolve()
 if not p.is_relative_to(folder.resolve()) or '.writing.' in p.name:raise ValueError('Invalid referenced asset path')
 return p

def prepare(folder,out,retained):
 meta=json.loads((folder/'georeference-and-identities.json').read_text());raw=safe_file(folder,meta['geometry_asset']).read_bytes();size=struct.unpack_from('<I',raw,12)[0];src=json.loads(raw[20:20+size]);binary=raw[28+size:]
 assert m.digest(raw)==meta['geometry_asset_sha256'];assert src['nodes'][0]['matrix']==meta['root_node_matrix_column_major'];assert src['extensions']['CESIUM_RTC']['center']==meta['rtc_ecef_m']
 namespace=meta['identity_namespace'];assert namespace in ('BAG','OST');key,collection=('bagId','bagIds') if namespace=='BAG' else ('featureId','featureIds')
 identities={x['batchId']:x['sourceId'].removeprefix('BAG_') if namespace=='BAG' else x['sourceId'] for x in meta['batch_identity']}
 for item in meta['batch_identity']:assert item['sourceId'].startswith(namespace+'_')
 referenced={};images={};source_records={r['uri']:r for r in meta['external_images']}
 def texture_image(texture):
  assert texture.get('texCoord',0)==0 and not texture.get('extensions'),'Expected unchanged source UV0'
  ii=src['textures'][texture['index']]['source'];uri=src['images'][ii]['uri']
  if ii not in images:
   data=safe_file(folder,uri).read_bytes();assert m.digest(data)==source_records[uri]['sha256'];image=Image.open(safe_file(folder,uri)).convert('RGB');assert list(image.size)==source_records[uri]['dimensions'];images[ii]=image;referenced[uri]=data
  return ii
 plans=[];rectangles=[]
 for mi,mesh in enumerate(src['meshes']):
  for pi,p in enumerate(mesh['primitives']):
   assert p.get('mode',4)==4;ids=m.accessor(src,binary,p['attributes']['_BATCHID'])[:,0];tri=m.accessor(src,binary,p['indices'])[:,0].reshape(-1,3);assert np.all(ids[tri]==ids[tri[:,0],None]);mat=src['materials'][p['material']]
   assert not any(k in mat for k in ('normalTexture','occlusionTexture'));assert 'metallicRoughnessTexture' not in mat.get('pbrMetallicRoughness',{})
   base=mat.get('pbrMetallicRoughness',{}).get('baseColorTexture');emission=mat.get('emissiveTexture');ii=texture_image(base) if base else None;ei=texture_image(emission) if emission else None
   assert ei is None or ii is not None
   if ei is not None:assert images[ei].size==images[ii].size
   uv=m.accessor(src,binary,p['attributes']['TEXCOORD_0']) if base else None
   for bid in sorted(set(ids[tri[:,0]].astype(int))):
    assert bid in identities;selected=tri[ids[tri[:,0]]==bid]
    islands=m.uv_islands(selected,uv) if base else [list(range(len(selected)))]
    for rows in islands:
     chosen=selected[rows];plan={'mi':mi,'pi':pi,'bid':int(bid),'indices':chosen,'material':p['material'],'rect':None}
     if base:
      size=np.array(images[ii].size);pixels=uv[chosen.ravel()]*size;assert np.all(pixels>=-.01) and np.all(pixels<=size+.01)
      lo=np.floor(pixels.min(0)).astype(int)-2;hi=np.ceil(pixels.max(0)).astype(int)+2;assert np.all(hi>lo)
      r={'sourceImage':ii,'emissionImage':ei,'sourceSize':size.tolist(),'sourceCrop':[*lo.tolist(),*hi.tolist()],'width':int(hi[0]-lo[0]),'height':int(hi[1]-lo[1]),'sourceMesh':mi,'sourcePrimitive':pi,'sourceBatchId':int(bid)};plan['rect']=len(rectangles);rectangles.append(r)
     plans.append(plan)
 width,height=m.pack_rectangles(rectangles);atlas=Image.new('RGB',(width,height));emission_crops={}
 def native_patch(ii,box):
  pixels=np.array(images[ii]);x0,y0,x1,y1=box
  return Image.fromarray(pixels[np.clip(np.arange(y0,y1),0,pixels.shape[0]-1)[:,None],np.clip(np.arange(x0,x1),0,pixels.shape[1]-1)[None,:]])
 for r in rectangles:
  patch=native_patch(r['sourceImage'],r['sourceCrop']);atlas.paste(patch,tuple(r['packedOrigin']))
  # Confirm copied native texels; no resizing, filtering or repainting.
  x,y=r['packedOrigin'];np.testing.assert_array_equal(np.array(atlas.crop((x,y,x+r['width'],y+r['height']))),np.array(patch))
 for ii in sorted({r['emissionImage'] for r in rectangles if r['emissionImage'] is not None}):
  original=np.array(images[ii]);ys,xs=np.nonzero(np.any(original>0,axis=2))
  if not len(xs):continue
  lo=np.maximum(0,[int(xs.min())-2,int(ys.min())-2]);hi=np.minimum(images[ii].size,[int(xs.max())+3,int(ys.max())+3]);box=[*lo.tolist(),*hi.tolist()];patch=images[ii].crop(box);restored=np.zeros_like(original);restored[lo[1]:hi[1],lo[0]:hi[0]]=np.array(patch);np.testing.assert_array_equal(restored,original)
  emission_crops[ii]={'image':patch,'box':box,'sourceSize':images[ii].size}
 has_emission=bool(emission_crops)
 out.mkdir(parents=True,exist_ok=True);retained.mkdir(parents=True,exist_ok=True)
 doc=copy.deepcopy(src);doc.update(meshes=[],accessors=[],bufferViews=[],materials=[],images=[],textures=[],samplers=[{'magFilter':9729,'minFilter':9987,'wrapS':33071,'wrapT':33071}]);payload=bytearray();meshmap={i:[] for i in range(len(src['meshes']))}
 def attr(values,template,target):
  payload.extend(b'\0'*((-len(payload))%4));vi=len(doc['bufferViews']);doc['bufferViews'].append({'buffer':0,'byteOffset':len(payload),'byteLength':values.nbytes,'target':target});payload.extend(values.tobytes());a={k:copy.deepcopy(v) for k,v in template.items() if k not in ('bufferView','byteOffset','count','min','max','sparse')};a.update(bufferView=vi,count=len(values))
  if 'min'in template:a['min']=values.min(0).tolist()
  if 'max'in template:a['max']=values.max(0).tolist()
  doc['accessors'].append(a);return len(doc['accessors'])-1
 atlas.save(out/'colour.png');doc['images'].append({'uri':'colour.png'});doc['textures'].append({'source':0,'sampler':0})
 for ii,crop in emission_crops.items():
  uri=f'emission-{ii}.png';crop['image'].save(out/uri);crop['texture']=len(doc['textures']);doc['images'].append({'uri':uri});doc['textures'].append({'source':len(doc['images'])-1,'sampler':0})
 # Remove only the obsolete atlas produced by the earlier packaging attempt.
 if (out/'emission.png').exists():(out/'emission.png').unlink()
 triangle_count=0
 for plan in plans:
  mi,pi,bid=plan['mi'],plan['pi'],plan['bid'];original=src['meshes'][mi]['primitives'][pi];chosen=plan['indices'];used,remapped=np.unique(chosen.ravel(),return_inverse=True);q=copy.deepcopy(original);q['attributes']={}
  for semantic,ai in original['attributes'].items():
   values=np.ascontiguousarray(m.accessor(src,binary,ai)[used]);np.testing.assert_array_equal(values[remapped.reshape(-1,3)],m.accessor(src,binary,ai)[chosen]);q['attributes'][semantic]=attr(values,src['accessors'][ai],34962)
  it=5123 if len(used)<=65535 else 5125;q['indices']=attr(remapped.astype(m.DTYPES[it]).reshape(-1,1),{'componentType':it,'type':'SCALAR'},34963)
  mat=copy.deepcopy(src['materials'][plan['material']]);mat.pop('emissiveTexture',None);mat['emissiveFactor']=[0,0,0]
  if plan['rect'] is not None:
   r=rectangles[plan['rect']];transform={'offset':((np.array(r['packedOrigin'])-r['sourceCrop'][:2])/[width,height]).tolist(),'scale':(np.array(r['sourceSize'])/[width,height]).tolist()};tex={'index':0,'texCoord':0,'extensions':{'KHR_texture_transform':transform}};mat['pbrMetallicRoughness']['baseColorTexture']=tex
   if r['emissionImage'] in emission_crops:
    crop=emission_crops[r['emissionImage']];w,h=crop['image'].size;x,y=crop['box'][:2];emission_transform={'offset':[-x/w,-y/h],'scale':[crop['sourceSize'][0]/w,crop['sourceSize'][1]/h]}
    mat['emissiveTexture']={'index':crop['texture'],'texCoord':0,'extensions':{'KHR_texture_transform':emission_transform}};mat['emissiveFactor']=[1,1,1];mat.setdefault('extras',{}).update(emissionCropGuard=True,sourceEmissionControl='Existing shared scene night uniform gates emission; day zero',occupancy='Source-observed glazing with illustrative occupancy, not live')
  # These annotations remain retained with the original handoff, not runtime URLs.
  for annotation in ('glazingMask','glazingPhase'):mat.get('extras',{}).pop(annotation,None)
  q['material']=len(doc['materials']);doc['materials'].append(mat);q.setdefault('extras',{})[key]=identities[bid];extras={key:identities[bid],'identityNamespace':namespace,'sourceMesh':mi,'sourcePrimitive':pi,'sourceBatchId':bid};meshmap[mi].append(len(doc['meshes']));doc['meshes'].append({'name':namespace+'_'+identities[bid] if namespace=='BAG' else identities[bid],'primitives':[q],'extras':extras});triangle_count+=len(chosen)
 for node in list(doc['nodes']):
  if 'mesh' not in node:continue
  mi=node.pop('mesh');children=node.setdefault('children',[])
  for index in meshmap[mi]:children.append(len(doc['nodes']));doc['nodes'].append({'mesh':index,'extras':{key:doc['meshes'][index]['extras'][key]}})
 doc.get('extensions',{}).pop('CESIUM_RTC',None)
 for k in ('extensionsUsed','extensionsRequired'):doc[k]=[x for x in doc.get(k,[]) if x!='CESIUM_RTC']
 for k in ('extensionsUsed','extensionsRequired'):
  if 'KHR_texture_transform' not in doc[k]:doc[k].append('KHR_texture_transform')
 doc.setdefault('extras',{}).update({collection:list(identities.values()),'identityNamespace':namespace,'appearanceStatus':'Bound artwork context review, not accepted','texturePacking':{'nativeTexels':True,'sourceUVsRetained':True,'atlasSize':[width,height],'islands':rectangles}})
 points=[];yz=np.array([[1,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1]])
 def walk(index,parent):
  node=doc['nodes'][index];assert not any(k in node for k in ('translation','rotation','scale'));matrix=parent@np.array(node.get('matrix',np.eye(4).flatten(order='F'))).reshape(4,4,order='F')
  if 'mesh'in node:
   for p in doc['meshes'][node['mesh']]['primitives']:
    v=m.accessor(doc,payload,p['attributes']['POSITION']);points.extend((np.c_[v,np.ones(len(v))]@(yz@matrix).T)[:,:3])
  for child in node.get('children',[]):walk(child,matrix)
 for n in doc['scenes'][doc.get('scene',0)]['nodes']:walk(n,np.eye(4))
 points=np.array(points);rtc=meta['rtc_ecef_m'];world=points+rtc;centre=(world.min(0)+world.max(0))/2;radius=float(np.max(np.linalg.norm(world-centre,axis=1)))+.001
 frame=(yz@np.array(meta['root_node_matrix_column_major']).reshape(4,4,order='F'))[:3,:3];assert np.allclose(frame.T@frame,np.eye(3),atol=1e-8);aligned=points@frame;lo,hi=aligned.min(0),aligned.max(0);boxcentre=((lo+hi)/2)@frame.T;box=[*boxcentre,*(frame*((hi-lo)/2+.001)).flatten(order='F')]
 doc['buffers']=[{'byteLength':len(payload)}];output=m.pack_glb(doc,payload);(out/'model.glb').write_bytes(output);assert triangle_count==meta['triangles']
 tiles={'asset':{'version':'1.0','gltfUpAxis':'Y'},'geometricError':0,'root':{'boundingVolume':{'sphere':[*centre,radius]},'geometricError':0,'refine':'REPLACE','children':[{'boundingVolume':{'box':box},'transform':[1,0,0,0,0,1,0,0,0,0,1,0,*rtc,1],'geometricError':0,'content':{'uri':'model.glb'},'extras':{collection:list(identities.values())}}]}};write_json(out/'tileset.json',tiles)
 from pyproj import Transformer
 lon,lat,h=Transformer.from_crs(4978,4979,always_xy=True).transform(*world.T)
 manifest={'status':'context review only','namespace':namespace,collection:list(identities.values()),'sourceGLBSha256':m.digest(raw),'sourceMunicipalSha256':meta['source_decoded_sha256'],'outputGLBSha256':m.digest(output),'triangles':triangle_count,'draws':len(plans),'originalUVsAndGeometryRetained':True,'rtcAppliedOnce':True,'atlasSize':[width,height],'decodedRgbaBytesIncludingMips':m.rgba_mip_bytes(width,height)+sum(m.rgba_mip_bytes(*crop['image'].size) for crop in emission_crops.values()),'sourceReferencedImages':[{ 'uri':uri,'sha256':m.digest(data)} for uri,data in referenced.items()],'emission':has_emission,'boundsLonLatHeight':[np.array([lon,lat,h]).min(1).tolist(),np.array([lon,lat,h]).max(1).tolist()]};write_json(out/'manifest.json',manifest);write_json(retained/'integration.json',manifest)
 (retained/meta['geometry_asset']).write_bytes(raw)
 for uri,data in referenced.items():target=retained/uri;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
 for name in ['README.md','georeference-and-identities.json','verification.json','texture-budget-estimate.json']:
  p=folder/name
  if p.exists():(retained/name).write_text(re.sub(r'libfile_[\w-]+','[private handoff reference omitted]',p.read_text()))
 print(json.dumps({k:manifest[k] for k in ['namespace','triangles','draws','atlasSize','decodedRgbaBytesIncludingMips','emission','boundsLonLatHeight']}));return tiles,manifest

def append_collection(folder,out,tiles,manifest):
 folder.mkdir(parents=True,exist_ok=True);path=folder/'manifest.json';entries=json.loads(path.read_text()).get('assets',[]) if path.exists() else [];uri=out.relative_to(folder).as_posix()+'/tileset.json';entries=[e for e in entries if e['uri']!=uri];entries.append({'uri':uri,'namespace':manifest['namespace'],'identities':manifest.get('bagIds',manifest.get('featureIds')),'sphere':tiles['root']['boundingVolume']['sphere']});assert len({e['namespace'] for e in entries})==1
 identities=[i for e in entries for i in e['identities']];assert len(set(identities))==len(identities),'Overlapping exact identities in collection';centres=np.array([e['sphere'][:3] for e in entries]);centre=centres.mean(0);radius=max(np.linalg.norm(c-centre)+e['sphere'][3] for c,e in zip(centres,entries));write_json(folder/'tileset.json',{'asset':{'version':'1.0','gltfUpAxis':'Y'},'geometricError':0,'root':{'boundingVolume':{'sphere':[*centre,radius]},'geometricError':0,'refine':'ADD','children':[{'boundingVolume':{'sphere':e['sphere']},'geometricError':0,'content':{'uri':e['uri']}} for e in entries]}});write_json(path,{'status':'context review only','assets':entries})

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('input',type=Path);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--retained',type=Path,required=True);ap.add_argument('--collection',type=Path);a=ap.parse_args();tiles,manifest=prepare(a.input,a.output,a.retained)
 if a.collection:append_collection(a.collection,a.output,tiles,manifest)
