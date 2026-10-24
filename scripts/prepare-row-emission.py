#!/usr/bin/env python3
"""Bind reviewed source-glazing RGB maps to a freshly prepared illustrated row."""
import argparse,hashlib,importlib.util,json,re,shutil,struct,tempfile,zipfile
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'public/data/illustrated-row';RETAINED=ROOT/'source-data/illustrated-row-emission'
s=importlib.util.spec_from_file_location('source',ROOT/'scripts/prepare-building-appearance.py');source=importlib.util.module_from_spec(s);s.loader.exec_module(source)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('archive',type=Path);args=ap.parse_args();archive=args.archive.read_bytes();raw=(OUT/'row.glb').read_bytes();n=struct.unpack_from('<I',raw,12)[0];d=json.loads(raw[20:20+n]);binary=raw[28+n:];base=json.loads((OUT/'manifest.json').read_text());assert source.digest(raw)==base['outputGLBSha256'],'Prepare baseline row first; do not stack emission modifications'
 with tempfile.TemporaryDirectory() as tmp:
  folder=Path(tmp)
  with zipfile.ZipFile(args.archive) as z:
   for name in z.namelist():assert (folder/name).resolve().is_relative_to(folder.resolve())
   z.extractall(folder)
  bindings=json.loads((folder/'mask-bindings.json').read_text());assert bindings['source_decoded_sha256']==base['sourceMunicipalSha256'];assert [(x['material_index'],x['base_color_image_index']) for x in bindings['bindings']]==[(i,i) for i in range(9)]+[(10,9)]
  checks=[];sampler=len(d.setdefault('samplers',[]));d['samplers'].append({'magFilter':9729,'minFilter':9987,'wrapS':33071,'wrapT':33071})
  for b in bindings['bindings']:
   mi,ii=b['material_index'],b['base_color_image_index'];mat=d['materials'][mi];bc=mat['pbrMetallicRoughness']['baseColorTexture'];assert b['uv_set']==bc.get('texCoord',0)==0;assert d['textures'][bc['index']]['source']==ii;assert d['images'][ii]['uri']==f'textures/atlas-{ii:02}.png';assert b['day_emissive_factor']==[0,0,0];assert b['night_example_emissive_factor']==[1,1,1]
   for mesh in d['meshes']:
    for p in mesh['primitives']:
     if p.get('material')==mi:assert 'TEXCOORD_0' in p['attributes']
   emission=np.array(Image.open(folder/b['emissive_texture']).convert('RGB'));mask=np.array(Image.open(folder/b['glazing_mask']).convert('L'));assert emission.shape==(2048,2048,3) and mask.shape==(2048,2048);outside=int(np.count_nonzero(np.any(emission>0,axis=2)&(mask==0)));assert outside==0
   for key in ['emissive_texture','glazing_mask','phase_and_id_map']:
    uri=b[key];assert (folder/uri).resolve().is_relative_to(folder.resolve());target=OUT/uri;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(folder/uri,target)
   ys,xs=np.nonzero(np.any(emission>0,axis=2))
   if not len(xs):
    checks.append({'material':mi,'baseColorImage':ii,'empty':True,'outsideGlazingPixels':outside});continue
   x0,y0=max(0,int(xs.min())-2),max(0,int(ys.min())-2);x1,y1=min(2048,int(xs.max())+3),min(2048,int(ys.max())+3);crop=emission[y0:y1,x0:x1];h,w=crop.shape[:2]
   # Exact native pixels, including a two-pixel black border where available.
   restored=np.zeros_like(emission);restored[y0:y1,x0:x1]=crop;np.testing.assert_array_equal(restored,emission)
   uri=f'masks/emission-crop-{ii:02}.png';Image.fromarray(crop).save(OUT/uri)
   transform={'offset':[-x0/w,-y0/h],'scale':[2048/w,2048/h]}
   image=len(d['images']);d['images'].append({'uri':uri});texture=len(d['textures']);d['textures'].append({'source':image,'sampler':sampler});mat['emissiveTexture']={'index':texture,'texCoord':0,'extensions':{'KHR_texture_transform':transform}};mat['emissiveFactor']=[1,1,1];mat.setdefault('extras',{}).update(glazingMask=b['glazing_mask'],glazingPhase=b['phase_and_id_map'],emissionCropGuard=True,occupancy='Stable illustrative occupancy; not observed or live',sourceEmissionControl='Shared scene night gates existing source emission; effective day factor zero')
   checks.append({'material':mi,'baseColorImage':ii,'emissionImage':image,'sha256':source.digest((folder/b['emissive_texture']).read_bytes()),'outsideGlazingPixels':outside,'crop':[x0,y0,x1,y1],'dimensions':[w,h],'decodedBytesIncludingMips':round(w*h*4*4/3),'textureTransform':transform})
  d.setdefault('extensionsUsed',[])
  if 'KHR_texture_transform' not in d['extensionsUsed']:d['extensionsUsed'].append('KHR_texture_transform')
  assert 'emissiveTexture' not in d['materials'][9]
  output=source.pack_glb(d,binary);(OUT/'row.glb').write_bytes(output)
  RETAINED.mkdir(parents=True,exist_ok=True)
  # Keep complete original annotations, fitting code and preview, not only masks.
  for file in folder.rglob('*'):
   if file.is_file():
    target=RETAINED/file.relative_to(folder);target.parent.mkdir(parents=True,exist_ok=True)
    if file.suffix in {'.json','.md','.txt','.py'}:target.write_text(re.sub(r'libfile_[0-9a-f]+', '[private handoff identifier omitted]', file.read_text()))
    else:shutil.copyfile(file,target)
  manifest={'sourceArchive':'010-source-glazing-emission.zip','archiveSha256':hashlib.sha256(archive).hexdigest(),'baseGLBSha256':source.digest(raw),'outputGLBSha256':source.digest(output),'geometryBinarySha256':source.digest(binary),'sourceMunicipalSha256':base['sourceMunicipalSha256'],'sourceBindings':checks,'dayControl':'emissiveFactor1 multiplied by shared night uniform0; no scene gate means always emissive','colorSpaces':{'emission':'sRGB via standard glTF emissiveTexture','maskAndPhase':'linear data retained as metadata, not loaded as RGB material maps'},'status':'Partial source-observed glazing; illustrative occupancy; runtime visual review required'}
  for target in [RETAINED/'integration-manifest.json',OUT/'emission-manifest.json']:target.write_text(json.dumps(manifest,indent=2)+'\n')
  print(json.dumps(manifest,indent=2))
if __name__=='__main__':main()
