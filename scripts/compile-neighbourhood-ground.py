#!/usr/bin/env python3
"""Written by AI, GPT-6, 2026-10-24. Bind model drawing to surveyed public space."""
from pathlib import Path
import hashlib,json
import numpy as np
from PIL import Image
from scipy import ndimage
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'source-data/public-space-neighbourhood';work=ROOT/'work/public-space-neighbourhood';out=ROOT/'public/data/ground-artwork-neighbourhood-v2';out.mkdir(parents=True,exist_ok=True)
metadata=json.loads((work/'source-mask.json').read_text());surface=np.load(work/'source-mask.npz');feature=surface['feature'];height,width=feature.shape
# Source material footprints carry geography. Small joints are illustrative,
# aligned with the observed street axes; no generated geographic field transfers.
rows,columns=np.indices((height,width));pixel=(metadata['boundsRD'][2]-metadata['boundsRD'][0])/width
angle=.14970488
along=(columns*np.cos(angle)+rows*np.sin(angle))*pixel
across=(-columns*np.sin(angle)+rows*np.cos(angle))*pixel
rgb=np.zeros((height,width,3),float);eligible=surface['surface']>0;material=np.zeros((height,width),np.uint8)
colours={1:[107,113,114],2:[157,110,95],3:[179,177,163],4:[112,133,76],5:[68,97,102],6:[143,132,117],7:[160,118,99]}
pavingPath=source/'drawing/pavement-material.png'
paving=np.array(Image.open(pavingPath).convert('RGB'),float)
# Nine drawn units span2.7m; the source-bound atlas therefore keeps .30m units.
pavingCoordinates=[np.mod(across,2.7)/2.7*(paving.shape[0]-1),np.mod(along,2.7)/2.7*(paving.shape[1]-1)]
pavingField=np.stack([ndimage.map_coordinates(paving[:,:,channel],pavingCoordinates,order=1,mode='wrap') for channel in range(3)],axis=-1)
sourceIds=[]
for record in metadata['features']:
 mask=feature==record['batchId'];a=record['attributes'];physical=a.get('FYSIEKVK','').lower();purpose=a.get('FUNCTIE','').lower();kind=int(surface['surface'][mask][0]) if mask.any() else 0
 if not kind:continue
 if purpose=='fietspad':kind=2
 elif 'open verharding' in physical and purpose in {'rijbaan lokale weg','parkeervlak'}:kind=6
 elif purpose=='ov-baan' and 'open verharding' in physical:kind=7
 sourceIds.append(str(a.get('DGDT_ID',record['id'])));material[mask]=kind
 if purpose=='ov-baan':kind=7;material[mask]=kind
 # At this view individual joints remain quiet. Unit layout is illustrative;
 # the source confirms small paving and orientation, not every slab boundary.
 field=np.ones((height,width))
 if kind in {3,6,7}:
  spacing=.30 if kind==3 else .21
  lineWidth=.012
  def joint_coverage(axis):
   phase=np.mod(axis,spacing);distance=np.minimum(phase,spacing-phase)
   return np.clip((pixel*.5+lineWidth*.5-distance)/pixel,0,lineWidth/pixel)
  coverage=np.maximum(joint_coverage(along),joint_coverage(across))
  field-=coverage*.22
 rgb[mask]=pavingField[mask] if kind==3 else np.array(colours[kind])*field[mask,None]
# Exact source material boundaries are quietly inked inside the native footprint.
edge=np.zeros_like(eligible)
for axis in [0,1]:
 adjacent=np.roll(material,1,axis);edge|=(material!=adjacent)&(material>0)&(adjacent>0)
edge[[0,-1],:]=False;edge[:,[0,-1]]=False;rgb[edge]*=.94
# Retain previously reviewed road paint at its RD coordinates.
old=np.array(Image.open(ROOT/'public/data/ground-artwork-neighbourhood/adjoining-ground-materials.png'))
oldPaint=old[:,:,3]==255;oldBounds=json.loads((ROOT/'public/data/ground-artwork-neighbourhood/manifest.json').read_text())['boundsRD']
paint=np.zeros_like(eligible);oldImage=Image.fromarray(oldPaint.astype('uint8')*255).resize((round((oldBounds[2]-oldBounds[0])/.125),round((oldBounds[3]-oldBounds[1])/.125)),Image.Resampling.NEAREST)
x=round((oldBounds[0]-metadata['boundsRD'][0])/.125);y=round((metadata['boundsRD'][3]-oldBounds[3])/.125);paint[y:y+oldImage.height,x:x+oldImage.width]=np.array(oldImage)>0
# These small source regions were read in the retained dated orthophoto. They
# contain actual crossing bars; source shadows/occlusions remain gaps.
regions=[['west north crossing',[190,796,230,827]],['west east crossing',[500,853,545,885]],['west south crossing',[376,1000,476,1040]],['west shaded crossing',[160,903,198,924]],['east north crossing',[1730,1034,1765,1074]],['east shaded crossing',[1663,1158,1699,1184]]]
photo=np.array(Image.open(source/'adjoining-neighbourhood-2026.jpg').convert('RGB'),float);brightness=photo.mean(2);local=ndimage.median_filter(brightness,size=17);sourceSupport=(brightness-local>12)&(photo.max(2)-photo.min(2)<np.maximum(35,brightness*.32))
for name,(x0,y0,x1,y1) in regions:paint[y0:y1,x0:x1]|=sourceSupport[y0:y1,x0:x1]
road=np.isin(material,[1,2,6,7]);paint&=eligible&road;rgb[paint]=[222,219,200]
# Bleed only RGB beneath transparent pixels; exact surveyed alpha stays intact.
nearest=ndimage.distance_transform_edt(~eligible,return_distances=False,return_indices=True);rgb[~eligible]=rgb[nearest[0][~eligible],nearest[1][~eligible]]
rgba=np.dstack([np.clip(rgb,0,255).astype('uint8'),eligible.astype('uint8')*255]);Image.fromarray(rgba).save(out/'neighbourhood-ground.png')
preview=rgba[:,:,:3].copy();preview[~eligible]=[42,46,48];Image.fromarray(preview).save(work/'drawn-ground-review.png')
manifest={k:metadata[k] for k in ['boundsRD','imageSize','worldToImageUV','sourceDecodedSha256','orthophotoSha256','projectionMaximumErrorPixels']};manifest.update(status='review-candidate',texture='neighbourhood-ground.png',areaId='adjoining-neighbourhood',sourceFeatureIds=sourceIds,eligiblePixels=int(eligible.sum()),paintPixels=int(paint.sum()),pavementMaterialSha256=hashlib.sha256(pavingPath.read_bytes()).hexdigest(),interpretation='Model-drawn local .30m pavement units inside exact source footway regions. Exact source material footprints and observed crossing fragments. Small quiet local paving joints follow observed street axes; generated geographic bands are excluded. Source OV reservation remains red-brown.',notSurveyed='Individual paving unit boundaries and .30/.21m drawing units are approximate illustration, not measured slab inventory.',acceptance='Unaccepted whole-neighbourhood actual city candidate.')
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');(source/'drawing/source-marking-review.json').write_text(json.dumps({'sourceSha256':metadata['orthophotoSha256'],'regions':regions,'method':'Observed crossing bars retain source local-contrast support only; no gap filling. Existing reviewed source paint retained at exact RD coordinates.'},indent=2)+'\n');print(json.dumps({'features':len(sourceIds),'paintPixels':int(paint.sum())}))
