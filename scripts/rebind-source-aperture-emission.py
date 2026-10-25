#!/usr/bin/env python3
"""Retain observed source apertures when replaceable daytime artwork changes.
Written by AI on 2026-10-25 by model GPT-6.
"""
import argparse, copy, hashlib, json, shutil, struct
from pathlib import Path

def read_json(path): return json.loads(path.read_text())
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read_glb(path):
 raw=path.read_bytes(); size=struct.unpack_from('<I',raw,12)[0]
 return json.loads(raw[20:20+size]),raw[28+size:]
def write_glb(path,document,binary):
 document_bytes=json.dumps(document,separators=(',',':')).encode();document_bytes+=b' '*((-len(document_bytes))%4)
 path.write_bytes(struct.pack('<4sII',b'glTF',2,28+len(document_bytes)+len(binary))+struct.pack('<I4s',len(document_bytes),b'JSON')+document_bytes+struct.pack('<I4s',len(binary),b'BIN\0')+binary)
def rebind(previous,current,output):
 previous_metadata=read_json(previous/'georeference-and-identities.json');metadata=read_json(current/'georeference-and-identities.json')
 previous_doc,previous_binary=read_glb(previous/previous_metadata['geometry_asset']);document,binary=read_glb(current/metadata['geometry_asset'])
 for key in ['meshes','accessors','bufferViews','nodes','scenes','buffers']:
  if previous_doc.get(key)!=document.get(key):raise ValueError('Source geometry/UV contract changed: '+key)
 if previous_binary!=binary:raise ValueError('Source geometry buffer changed')
 def base_uri(doc,material):
  texture=material.get('pbrMetallicRoughness',{}).get('baseColorTexture')
  return doc['images'][doc['textures'][texture['index']]['source']]['uri'] if texture else None
 previous_materials={base_uri(previous_doc,material):material for material in previous_doc['materials']}
 output.mkdir(parents=True,exist_ok=True)
 for path in current.iterdir():
  if path.is_file():shutil.copyfile(path,output/path.name)
 rebound={}
 for material in document['materials']:
  original=previous_materials.get(base_uri(document,material),{})
  if 'emissiveTexture' not in original:continue
  old_texture=previous_doc['textures'][original['emissiveTexture']['index']];image=previous_doc['images'][old_texture['source']];uri=image['uri']
  if uri not in rebound:
   shutil.copyfile(previous/uri,output/uri);image_index=len(document['images']);document['images'].append(copy.deepcopy(image))
   rebound[uri]=len(document['textures']);document['textures'].append({'source':image_index,'sampler':0})
  material['emissiveTexture']={'index':rebound[uri]};material['emissiveFactor']=original['emissiveFactor'];material.setdefault('extras',{}).update(original.get('extras',{}))
 write_glb(output/metadata['geometry_asset'],document,binary)
 metadata['geometry_asset_sha256']=digest(output/metadata['geometry_asset']);metadata['external_images']+=[image for image in previous_metadata['external_images'] if image['uri'] in rebound]
 (output/'georeference-and-identities.json').write_text(json.dumps(metadata,indent=2)+'\n')
 interpretation=read_json(previous/'aperture-interpretation.json');interpretation['daytimeGeometrySha256']=digest(current/metadata['geometry_asset']);interpretation['observedMasksReusedFrom']=str(previous)
 (output/'aperture-interpretation.json').write_text(json.dumps(interpretation,indent=2)+'\n')
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('previous',type=Path);parser.add_argument('current',type=Path);parser.add_argument('output',type=Path);args=parser.parse_args();rebind(args.previous,args.current,args.output)
