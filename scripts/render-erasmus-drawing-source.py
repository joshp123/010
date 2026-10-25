#!/usr/bin/env python3
"""Render retained bridge and shore geometry in one true observation frame.
Written by AI on 2026-10-25 by model GPT-6 Astra.
"""
import gzip,hashlib,importlib.util,json,urllib.request,struct,sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from PIL import Image
from pyproj import Transformer
ROOT=Path(__file__).resolve().parents[1];out=ROOT/'source-data/erasmus-structure-drawing'
spec=importlib.util.spec_from_file_location('views',Path('/Users/josh/code/010-rescue-art/scripts/source-view-painter.py'));views=importlib.util.module_from_spec(spec);spec.loader.exec_module(views)
metadata=json.loads((out/'source-planes.json').read_text());arrays=np.load(out/'source-planes.npz');positions=arrays['positions'];centre=arrays['sourceCentreRD']
source=SimpleNamespace(triangles=[dict(t,positions=positions[t['sourceTriangle']],uv=np.array(t['uv']),image=0) for t in metadata['triangles']],images=[np.array([[[207,213,210]]],np.uint8)])
leaf=out/'18_268672_55471.b3dm';url='https://www.3drotterdam.nl/datasource-data/3adbe5af-d05c-475a-b34c-59e69ba8dadc/18/268672/55471.b3dm'
if not leaf.exists():
 raw=urllib.request.urlopen(url,timeout=45).read();raw=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw;leaf.write_bytes(raw)
(out/'shore-source.json').write_text(json.dumps({'url':url,'decodedSha256':hashlib.sha256(leaf.read_bytes()).hexdigest(),'selectedBag':'0599100000750049'},indent=2)+'\n')
shore=views.m.Source(leaf);rotation=np.array(shore.doc['nodes'][0]['matrix']).reshape(4,4,order='F')[:3,:3];rtc=np.array(shore.feature['RTC_CENTER']);gltf_to_earth=np.array([[1.,0.,0.],[0.,0.,-1.],[0.,1.,0.]])
transformer=Transformer.from_crs(4978,28992,always_xy=True);height_transform=Transformer.from_crs(4978,4979,always_xy=True)
reconciled='--reconciled' in sys.argv
if reconciled:
 shore=views.m.Source(out/'reconciled-shore/source-bound-row.glb')
 for triangle in shore.triangles:triangle['identity']='0599100000750049'
image_start=len(source.images);source.images.extend(shore.images)
for triangle in shore.triangles:
 if triangle['identity']!='0599100000750049':continue
 earth=(triangle['positions']@rotation.T)@gltf_to_earth.T+rtc
 x,y,_=transformer.transform(*earth.T);_,_,height=height_transform.transform(*earth.T)
 local=(np.c_[x,y,height]-centre)[...,[0,2,1]];local[...,2]*=-1
 source.triangles.append({**triangle,'positions':local,'image':triangle['image']+image_start})
# Retained BGT deck regions in the same RD observation frame.
raw=(ROOT/'public/data/bridge-surfaces/erasmus.glb').read_bytes();json_size=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+json_size]);binary=raw[28+json_size:]
lat,lon=np.deg2rad([51.915,4.49]);east=np.array([-np.sin(lon),np.cos(lon),0]);up=np.array([np.cos(lat)*np.cos(lon),np.cos(lat)*np.sin(lon),np.sin(lat)]);south=np.array([np.sin(lat)*np.cos(lon),np.sin(lat)*np.sin(lon),-np.cos(lat)]);origin=np.array(Transformer.from_crs(4979,4978,always_xy=True).transform(4.49,51.915,0))
colours={'road':[101,107,105],'cycleway':[172,117,94],'bridge-footway':[184,185,173],'bridge-divider':[115,122,114],'bridge-track-bed':[139,136,122],'rail-groove':[69,75,73],'rail-steel':[178,183,174],'bridge-edge-paint':[215,214,199]}
for mesh in doc['meshes']:
 kind=mesh.get('extras',{}).get('surfaceKind');colour=colours.get(kind,[184,185,173]);image=len(source.images);source.images.append(np.array([[colour]],np.uint8))
 for primitive in mesh['primitives']:
  points=views.m.appearance.accessor(doc,binary,primitive['attributes']['POSITION']);earth=origin+points[:,0,None]*east+points[:,1,None]*up+points[:,2,None]*south;x,y,_=transformer.transform(*earth.T);_,_,height=height_transform.transform(*earth.T);local=(np.c_[x,y,height+.025]-centre)[...,[0,2,1]];local[...,2]*=-1
  for t in local.reshape(-1,3,3):source.triangles.append({'positions':t,'uv':np.zeros((3,2)),'image':image,'identity':'BGT-'+kind})
source.positions=np.array([t['positions'] for t in source.triangles]);source.normals=np.cross(source.positions[:,1]-source.positions[:,0],source.positions[:,2]-source.positions[:,0]);source.areas=np.linalg.norm(source.normals,axis=1)/2;source.normals/=np.maximum(source.areas[:,None]*2,1e-12)
plans=[]
for angle in ([] if reconciled else [125,305]):
 camera=views.camera(source,angle,28,1600);rgb,depth=views.render(source,camera);guide,_=views.render(source,camera,True)
 name=f'whole-{angle}';Image.fromarray(rgb).save(out/f'{name}-source.png');Image.fromarray(guide).save(out/f'{name}-geometry.png');np.save(out/f'{name}-depth.npy',depth);plans.append({'name':name,'camera':camera})
# Two normal-scale source context windows preserve actual structure and deck layout.
import copy
for name,rd_centre,span in [('north',[92787,436220,12],240),('pylon',[93085,435980,60],280)]:
 if reconciled and name!='north':continue
 for angle in [125,305]:
  camera=views.camera(source,angle,28,1600);camera['centre']=((np.array(rd_centre)-centre)[[0,2,1]]*[1,1,-1]).tolist();camera['mid']=[0,0];camera['scale']=1500/span
  rgb,depth=views.render(source,camera);guide,_=views.render(source,camera,True);key=('reconciled-' if reconciled else '')+f'{name}-{angle}';Image.fromarray(rgb).save(out/f'{key}-source.png');Image.fromarray(guide).save(out/f'{key}-geometry.png');np.save(out/f'{key}-depth.npy',depth);plans.append({'name':key,'camera':camera})
(out/('reconciled-views.json' if reconciled else 'views.json')).write_text(json.dumps({'authorship':'Written by AI on 2026-10-25 by model GPT-6 Astra','sourceCentreRD':centre.tolist(),'views':plans},indent=2)+'\n')
print('Rendered retained bridge and shore building, source coordinate frame unchanged')
