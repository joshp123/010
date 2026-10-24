#!/usr/bin/env python3
"""Derive exact BGT eligible-feature and highest-surface masks on the dated ortho grid."""
import gzip,hashlib,importlib.util,json,argparse
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from pyproj import Transformer
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'source-data/public-space-pilot';OUT=ROOT/'work/public-space-pilot';OUT.mkdir(exist_ok=True)
parser=argparse.ArgumentParser();parser.add_argument('--year',default='2026');args=parser.parse_args();year=args.year
s=importlib.util.spec_from_file_location('source',ROOT/'scripts/prepare-building-appearance.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
meta=json.loads((SRC/('schiedamseweg-'+year+'.json')).read_text());bounds=meta['boundsRD'];width,height=meta['imageSize'];pixel=meta['pixelMetres']
raw=gzip.decompress((SRC/'33577-6934.b3dm.gz').read_bytes());doc,buf,batch,ft=next(m.b3dm_parts(raw));assert hashlib.sha256(raw).hexdigest()==json.loads((SRC/'33577-6934.b3dm.json').read_text())['decodedSha256']
rd=Transformer.from_crs(4978,28992,always_xy=True);geo=Transformer.from_crs(4978,4979,always_xy=True)
yz=np.array([[1,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1]]);rtc=np.eye(4);rtc[:3,3]=ft['RTC_CENTER'];idmap=np.full((height,width),-1,np.int32);zbuf=np.full((height,width),-np.inf);surface=np.zeros((height,width),np.uint8);triangles=[]
# Actual source physical class, not a content-generating guess.
def category(a):
 k=a.get('KLASSE_IMG','').lower();p=a.get('FYSIEKVK','').lower();f=a.get('FUNCTIE','').lower()
 if k not in {'wegdeel','ondersteunend wegdeel','begroeid terreindeel','onbegroeid terreindeel','waterdeel','ondersteunend waterdeel'}:return 0
 if 'water'in k:return 5
 if k.startswith('begroeid'):return 4
 if 'open verharding'in p:return 3
 if 'gesloten verharding'in p:return 1
 return 0

def visit(i,parent):
 n=doc['nodes'][i];mat=parent@np.array(n.get('matrix',np.eye(4).T.ravel())).reshape(4,4).T
 if 'mesh'in n:
  for p in doc['meshes'][n['mesh']]['primitives']:
   v=m.accessor(doc,buf,p['attributes']['POSITION']);idx=m.accessor(doc,buf,p['indices'])[:,0].reshape(-1,3);ids=m.accessor(doc,buf,p['attributes']['_BATCHID'])[:,0];world=(np.c_[v,np.ones(len(v))]@(rtc@yz@mat).T)[:,:3];x,y,z=rd.transform(*world.T);lo,la,alt=geo.transform(*world.T);screen=np.c_[(x-bounds[0])/pixel,(bounds[3]-y)/pixel];rz=np.c_[x,y,alt]
   for indices in idx:
    bid=int(ids[indices[0]]);xy=screen[indices];low=np.maximum(np.floor(xy.min(0)).astype(int),0);high=np.minimum(np.ceil(xy.max(0)).astype(int),[width-1,height-1]);x0,y0=low;x1,y1=high
    if x1<x0 or y1<y0:continue
    a=np.vstack([xy.T,np.ones(3)])
    if abs(np.linalg.det(a))<1e-8:continue
    xx,yy=np.meshgrid(np.arange(x0,x1+1)+.5,np.arange(y0,y1+1)+.5);w=np.stack([xx,yy,np.ones_like(xx)],axis=-1)@np.linalg.inv(a).T;inside=(w.min(-1)>=-1e-7);zz=w@np.asarray(alt)[indices];current=zbuf[y0:y1+1,x0:x1+1];ok=inside&(zz>current);current[ok]=zz[ok];idmap[y0:y1+1,x0:x1+1][ok]=bid;surface[y0:y1+1,x0:x1+1][ok]=category(batch['attributes'][bid]);triangles.append({'batchId':bid,'rd':rz[indices].tolist()})
 for child in n.get('children',[]):visit(child,mat)
for i in doc['scenes'][doc.get('scene',0)]['nodes']:visit(i,np.eye(4))
palette=np.array([[42,46,48],[135,139,136],[171,122,102],[191,187,173],[111,135,91],[63,87,91]],np.uint8);Image.fromarray(palette[surface]).save(OUT/'source-semantic-mask.png');eligible=surface>0;Image.fromarray((eligible*255).astype('uint8')).save(OUT/'eligible-ground.png');np.savez_compressed(OUT/'source-mask.npz',feature=idmap,surface=surface,height=zbuf)
source=Image.open(SRC/('schiedamseweg-'+year+'.jpg')).convert('RGB');overlay=np.array(source);edge=np.zeros_like(eligible);edge[:,1:]|=idmap[:,1:]!=idmap[:,:-1];edge[1:,:]|=idmap[1:,:]!=idmap[:-1,:];overlay[edge]=[245,212,109];Image.fromarray(overlay).save(OUT/'source-with-bgt-edges.png')
# Fit metre-exact local-world to RD image projection, verifying independent points.
ll=Transformer.from_crs(28992,4326,always_xy=True);earth=Transformer.from_crs(4979,4978,always_xy=True);origin=np.array(earth.transform(4.49,51.915,0));lon,lat=np.radians([4.49,51.915]);basis=np.array([[-np.sin(lon),np.cos(lon),0],[np.cos(lat)*np.cos(lon),np.cos(lat)*np.sin(lon),np.sin(lat)],[np.sin(lat)*np.cos(lon),np.sin(lat)*np.sin(lon),-np.cos(lat)]])
points=[];uv=[]
for x in np.linspace(bounds[0],bounds[2],5):
 for y in np.linspace(bounds[1],bounds[3],5):
  for z in [0,30]:
   l,o=ll.transform(x,y);p=(np.array(earth.transform(l,o,z))-origin)@basis.T;points.append([*p,1]);uv.append([(x-bounds[0])/(width*pixel),(bounds[3]-y)/(height*pixel)])
projection=np.linalg.lstsq(np.array(points),np.array(uv),rcond=None)[0].T;errors=np.linalg.norm((np.array(points)@projection.T-np.array(uv))*[width,height],axis=1)
ids=sorted(set(idmap[eligible].tolist()));report={'boundsRD':bounds,'imageSize':[width,height],'worldToImageUV':projection.tolist(),'projectionMaximumErrorPixels':float(errors.max()),'sourceFeatureIds':[str(batch['attributes'][i].get('DGDT_ID',batch['id'][i])) for i in ids],'features':[{'batchId':i,'id':batch['id'][i],'attributes':batch['attributes'][i]} for i in ids],'sourceDecodedSha256':hashlib.sha256(raw).hexdigest(),'orthophotoSha256':meta['decodedSha256'],'eligiblePixels':int(eligible.sum()),'sourcePixelCount':width*height}
(OUT/'source-mask.json').write_text(json.dumps(report,indent=2)+'\n');(OUT/'source-triangles.json').write_text(json.dumps(triangles,separators=(',',':')));print(json.dumps({k:report[k] for k in ['eligiblePixels','sourcePixelCount','projectionMaximumErrorPixels']}))
