#!/usr/bin/env python3
"""Retained native source buildings in the rejected metro view, geometry-only CPU fixture."""
import importlib.util,gzip,json,numpy as np,sys
from pathlib import Path
from pyproj import Transformer
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('centre',ROOT/'scripts/inspect-current-centre.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c);m=c.m
lon,lat=4.5125991,51.9250915
origin=np.array(Transformer.from_crs(4979,4978,always_xy=True).transform(lon,lat,0));lo,la=np.radians([lon,lat]);basis=np.array([[-np.sin(lo),np.cos(lo),0],[np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)],[np.sin(la)*np.cos(lo),np.sin(la)*np.sin(lo),-np.cos(la)]])
axis=np.array([.983,.182]);axis/=np.linalg.norm(axis);rotation=np.array([[axis[0],0,axis[1]],[0,1,0],[-axis[1],0,axis[0]]]);features={}
sources=[{**source,'kind':'building'} for source in json.loads((ROOT/'source-data/transit-ground-evidence/building-sources.json').read_text())]+[{'file':'33589-6931.b3dm.gz','kind':'ground'}]
for source in sources:
 raw=gzip.decompress((ROOT/'source-data/transit-ground-evidence'/source['file']).read_bytes())
 for doc,binary,batch,feature in m.b3dm_parts(raw):
  yz=np.array([[1,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1]]);shift=np.eye(4);shift[:3,3]=feature['RTC_CENTER']
  def visit(i,parent):
   node=doc['nodes'][i];matrix=parent@np.array(node.get('matrix',np.eye(4).T.ravel())).reshape(4,4).T
   if 'mesh'in node:
    for p in doc['meshes'][node['mesh']]['primitives']:
     v=m.accessor(doc,binary,p['attributes']['POSITION']);idx=m.accessor(doc,binary,p['indices'])[:,0].reshape(-1,3);ids=m.accessor(doc,binary,p['attributes']['_BATCHID'])[:,0];world=(np.c_[v,np.ones(len(v))]@(shift@yz@matrix).T)[:,:3];local=((world-origin)@basis.T)@rotation.T
     for bid in np.unique(ids[idx[:,0]]):
      chosen=idx[ids[idx[:,0]]==bid];points=local[chosen].reshape(-1,3)
      if np.min(points[:,0])>80 or np.max(points[:,0])< -80 or np.min(points[:,2])>80 or np.max(points[:,2])< -80:continue
      if source['kind']=='ground':
       triangles=points.reshape(-1,3,3);points=triangles[(triangles[:,:,1]>-30).all(axis=1)].reshape(-1,3)
      key=source['kind']+':'+batch['id'][int(bid)];entry=features.setdefault(key,{'positions':[],'kind':source['kind'],'attributes':batch.get('attributes',[{}]*len(batch['id']))[int(bid)]});entry['positions'].extend(points.tolist())
   for child in node.get('children',[]):visit(child,matrix)
  for root in doc['scenes'][doc.get('scene',0)]['nodes']:visit(root,np.eye(4))
output=Path(sys.argv[1] if len(sys.argv)>1 else '/tmp/metro-source-buildings.json');output.write_text(json.dumps({'source':'Retained native municipal building triangles; rigid local frame, no simplification','anchor':[lon,lat],'features':[{'id':id,**entry,'positions':np.asarray(entry['positions']).ravel().tolist()}for id,entry in features.items()]}));print(output,len(features))
