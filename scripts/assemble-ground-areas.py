#!/usr/bin/env python3
"""Place already-reviewed ground crops into one georeferenced atlas without resampling.
The existing runtime shader accepts the same manifest schema; no scene ownership.
"""
from pathlib import Path
import argparse,json,hashlib
import numpy as np
from PIL import Image
p=argparse.ArgumentParser();p.add_argument('--inputs',nargs='+',required=True);p.add_argument('--output',required=True);args=p.parse_args();out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
areas=[]
for name in args.inputs:
 root=Path(name);m=json.loads((root/'manifest.json').read_text());im=Image.open(root/m['texture']).convert('RGBA');b=m['boundsRD'];sx=(b[2]-b[0])/im.width;sy=(b[3]-b[1])/im.height;assert abs(sx-sy)<1e-10;areas.append((root,m,im,sx))
pixel=areas[0][3];assert all(abs(a[3]-pixel)<1e-10 for a in areas);bounds=[min(a[1]['boundsRD'][0] for a in areas),min(a[1]['boundsRD'][1] for a in areas),max(a[1]['boundsRD'][2] for a in areas),max(a[1]['boundsRD'][3] for a in areas)];size=[round((bounds[2]-bounds[0])/pixel),round((bounds[3]-bounds[1])/pixel)];canvas=Image.new('RGBA',size);occupied=np.zeros((size[1],size[0]),bool);points=[];uv=[];reports=[]
for root,m,im,_ in areas:
 b=m['boundsRD'];offset=np.array([(b[0]-bounds[0])/pixel,(bounds[3]-b[3])/pixel]);assert np.max(abs(offset-np.round(offset)))<1e-8;x,y=offset.astype(int);assert not occupied[y:y+im.height,x:x+im.width].any(),'Overlapping crops require an explicit source precedence decision';occupied[y:y+im.height,x:x+im.width]=True;canvas.paste(im,(x,y));matrix=np.array(m['worldToImageUV']);xz=matrix[:,[0,2]]
 for u in np.linspace(0,1,5):
  for v in np.linspace(0,1,5):
   for elevation in [0,30]:
    east,south=np.linalg.solve(xz,np.array([u,v])-matrix[:,1]*elevation-matrix[:,3]);points.append([east,elevation,south,1]);uv.append((np.array([u*im.width,v*im.height])+offset)/size)
 reports.append({'directory':str(root),'areaId':m.get('areaId'),'boundsRD':b,'orthophotoAvailable':m.get('orthophotoAvailable',True),'sourceDecodedSha256':m['sourceDecodedSha256'],'orthophotoSha256':m.get('orthophotoSha256'),'textureSha256':hashlib.sha256((root/m['texture']).read_bytes()).hexdigest(),'offsetPixels':[int(x),int(y)],'paintPixels':m['paintPixels']})
projection=np.linalg.lstsq(np.array(points),np.array(uv),rcond=None)[0].T;error=np.linalg.norm((np.array(points)@projection.T-np.array(uv))*size,axis=1).max();assert error<.01,error
canvas.save(out/'adjoining-ground.png');manifest={'status':'review-candidate','texture':'adjoining-ground.png','boundsRD':bounds,'imageSize':size,'worldToImageUV':projection.tolist(),'sourceFeatureIds':sorted({i for _,m,_,_ in areas for i in m['sourceFeatureIds']}),'areas':reports,'projectionJoinMaximumErrorPixels':float(error),'paintPixels':sum(a['paintPixels'] for a in reports),'eligiblePixels':int((np.array(canvas)[:,:,3]>0).sum()),'acceptance':'Unaccepted source-bound review candidate; actual whole-scene review required.'};
if all(m.get('alphaEncoding')=='material128-marking255' for _,m,_,_ in areas):manifest['alphaEncoding']='material128-marking255'
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps({'size':size,'joinErrorPixels':float(error),'features':len(manifest['sourceFeatureIds'])}))
