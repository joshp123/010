#!/usr/bin/env python3
"""Repair five verified native approach triangles from retained BGT/AHN evidence."""
import importlib.util,gzip,json,hashlib
from pathlib import Path
import numpy as np,laspy
from pyproj import Transformer
from shapely.geometry import Polygon,Point
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'source-data/traffic/soetensteeg-bridge';OUT=ROOT/'public/data/ground-corrections';OUT.mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location('native',ROOT/'scripts/prepare-building-appearance.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
P=Transformer.from_crs(4979,4978,always_xy=True).transform;G=Transformer.from_crs(4978,4979,always_xy=True).transform;RD=Transformer.from_crs(4326,28992,always_xy=True).transform
origin=np.array(P(4.49,51.915,0));lo,la=np.radians([4.49,51.915]);basis=np.array([[-np.sin(lo),np.cos(lo),0],[np.cos(la)*np.cos(lo),np.cos(la)*np.sin(lo),np.sin(la)],[np.sin(la)*np.cos(lo),np.sin(la)*np.sin(lo),-np.cos(la)]])
def local(lon,lat,height):return (np.array(P(lon,lat,height))-origin)@basis.T
raw=gzip.decompress((ROOT/'source-data/traffic/blaak-surface/33584-6932.b3dm.gz').read_bytes());triangles={}
for doc,binary,batch,feature in m.b3dm_parts(raw):
 yz=np.array([[1,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1]]);shift=np.eye(4);shift[:3,3]=feature['RTC_CENTER']
 def visit(i,parent):
  node=doc['nodes'][i];matrix=parent@np.array(node.get('matrix',np.eye(4).T.ravel())).reshape(4,4).T
  if 'mesh' in node:
   for primitive in doc['meshes'][node['mesh']]['primitives']:
    vertices=m.accessor(doc,binary,primitive['attributes']['POSITION']);indices=m.accessor(doc,binary,primitive['indices'])[:,0].reshape(-1,3);ids=m.accessor(doc,binary,primitive['attributes']['_BATCHID'])[:,0]
    points=((np.c_[vertices,np.ones(len(vertices))]@(shift@yz@matrix).T)[:,:3]-origin)@basis.T
    for bid in np.unique(ids[indices[:,0]]):
     identifier=str(batch['attributes'][int(bid)].get('DGDT_ID',''))
     if identifier in ['16299950','15486948']:triangles[identifier]=points[indices[ids[indices[:,0]]==bid]]
  for child in node.get('children',[]):visit(child,matrix)
 for index in doc['scenes'][doc.get('scene',0)]['nodes']:visit(index,np.eye(4))
cloud=laspy.read(SRC/'ahn6-bridge-subset.laz');xyz=np.c_[cloud.x,cloud.y,cloud.z];classification=np.asarray(cloud.classification)
features=json.loads((SRC/'wegdeel.json').read_bytes())['features'];mapping={'16299950':'G0599.170ade244344d2d73e050210a7e24429','15486948':'G0599.88d78b25c8ed48d294fefe9ad75b81a0'};patches=[];reviews=[]
for identifier,current_id in mapping.items():
 feature=next(f for f in features if f['properties']['lokaal_id']==current_id);polygon=Polygon([RD(*q) for q in feature['geometry']['coordinates'][0]]);inner=polygon.buffer(-.2)
 selected=np.array([inner.contains(Point(*q)) for q in xyz[:,:2]])&(classification==26)&(xyz[:,2]>2.5)&(xyz[:,2]<4.5);points=xyz[selected];anchor=points[:,:2].mean(axis=0)
 design=np.c_[np.ones(len(points)),points[:,:2]-anchor];keep=np.ones(len(points),dtype=bool)
 for _ in range(5):
  coefficients=np.linalg.lstsq(design[keep],points[keep,2],rcond=None)[0];keep=abs(design@coefficients-points[:,2])<.08
 rmse=float(np.sqrt(np.mean((design[keep]@coefficients-points[keep,2])**2)));assert rmse<.04 and keep.sum()>25
 distances=[]
 for triangle in triangles[identifier]:
  # Only broad plan triangles descending to water; quay wall faces are excluded.
  if triangle[:,1].min()>=1 or Polygon(triangle[:,[0,2]]).area<=1:continue
  replacement=[];vertex_evidence=[]
  for vertex in triangle:
   lon,lat,_=G(*(origin+vertex@basis));xy=np.array(RD(lon,lat))
   # Source footway points are occluded between its bank and deck endpoints.
   # Use local measured endpoint heights, including adjoining BGT deck surfaces,
   # rather than extrapolating the small visible bank plane ten metres.
   distance=np.linalg.norm(xyz[:,:2]-xy,axis=1)
   eligible=np.flatnonzero(np.isin(classification,[2,26])&(xyz[:,2]>3.2)&(xyz[:,2]<4.1)&(distance<1.5))
   nearest=eligible[np.argsort(distance[eligible])[:12]];assert len(nearest)>=5
   height=float(np.median(xyz[nearest,2]));assert 3.2<height<4
   distances.append(float(distance[nearest].max()))
   replacement.append(float(local(lon,lat,height)[1]))
   vertex_evidence.append({'pointRD':xy.tolist(),'samples':len(nearest),'maximumSampleDistanceMetres':float(distance[nearest].max()),'medianNAP':height,'heightRangeNAP':[float(xyz[nearest,2].min()),float(xyz[nearest,2].max())]})
  patches.append({'featureId':identifier,'expectedWorldPositions':triangle.tolist(),'replacementWorldY':replacement,'currentBGT':current_id,'heightEvidence':vertex_evidence})
 reviews.append({'nativeFeatureId':identifier,'currentBGT':feature['properties'],'fitPoints':int(keep.sum()),'rmseMetres':rmse,'maximumNearestPointDistanceMetres':max(distances),'model':'Triangle endpoint heights: median nearest12 observed class2/26 surface samples within1.5m, range3.2–4.1m; local plane reported only as supporting bank evidence, NOT extrapolated across occluded approach','anchorRD':anchor.tolist(),'coefficients':coefficients.tolist()})
assert len(patches)==5
output={'version':1,'origin':{'longitude':4.49,'latitude':51.915},'sourceTile':'33584/6932.b3dm','sourceSha256':hashlib.sha256(raw).hexdigest(),'review':'Five malformed Soetensteeg approach triangles only; preserve native quay walls and registered pier16063621. Original horizontal coordinates and all traffic routes unchanged.','triangles':patches}
(OUT/'soetensteeg.json').write_text(json.dumps(output,indent=2)+'\n');(SRC/'approach-review.json').write_text(json.dumps({'sourceHashes':{name:hashlib.sha256((SRC/name).read_bytes()).hexdigest() for name in ['wegdeel.json','ahn6-bridge-subset.laz']},'fits':reviews,'triangles':len(patches),'preservedPier':'16063621'},indent=2)+'\n');print(json.dumps(reviews,indent=2))
