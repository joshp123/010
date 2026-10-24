#!/usr/bin/env python3
"""Written by AI, GPT-6, 2026-10-24. Bind model drawing to surveyed public space."""
from pathlib import Path
import json
import numpy as np
from PIL import Image
from scipy import ndimage
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'source-data/public-space-neighbourhood';work=ROOT/'work/public-space-neighbourhood';out=ROOT/'public/data/ground-artwork-neighbourhood-v3';out.mkdir(parents=True,exist_ok=True)
metadata=json.loads((work/'source-mask.json').read_text());surface=np.load(work/'source-mask.npz');feature=surface['feature'];height,width=feature.shape
# Source material footprints carry geography. Small joints are illustrative,
# aligned with the observed street axes; no generated geographic field transfers.
rows,columns=np.indices((height,width));pixel=(metadata['boundsRD'][2]-metadata['boundsRD'][0])/width
rgb=np.zeros((height,width,3),float);eligible=surface['surface']>0;material=np.zeros((height,width),np.uint8)
sourceIds=[]
# Values are a visual interpretation of the retained aerial: parking brick is
# darker than walking stone, asphalt cooler, and the observed tram strip muted red.
# Source feature geometry supplies every regional shape. No generated map transfers.
compositionColours={1:[101,110,112],2:[160,111,96],3:[181,181,169],4:[105,123,76],5:[67,91,95],6:[132,120,108],7:[150,112,96]}
for record in metadata['features']:
 mask=feature==record['batchId'];a=record['attributes'];physical=a.get('FYSIEKVK','').lower();purpose=a.get('FUNCTIE','').lower();kind=int(surface['surface'][mask][0]) if mask.any() else 0
 if not kind:continue
 if purpose=='fietspad':kind=2
 elif 'open verharding' in physical and purpose in {'rijbaan lokale weg','parkeervlak'}:kind=6
 elif purpose=='ov-baan':kind=7
 sourceIds.append(str(a.get('DGDT_ID',record['id'])));material[mask]=kind
 rgb[mask]=compositionColours[kind]
 # The long axis belongs to this retained feature, so north/south footways do
 # not inherit east/west paving. Individual unit boundaries remain illustration.
 points=np.column_stack(np.nonzero(mask))[:,::-1].astype(float)
 axis=np.linalg.eigh(np.cov(points.T))[1][:,-1] if len(points)>2 else np.array([1.,0.])
 localAlong=(columns*axis[0]+rows*axis[1])*pixel
 localAcross=(-columns*axis[1]+rows*axis[0])*pixel
 if kind in {3,6,7}:
  unitAlong,unitAcross=(.30,.30) if kind==3 else (.21,.105)
  stagger=(np.floor(localAcross/unitAcross)%2)*unitAlong*.5 if kind!=3 else 0
  def joint_coverage(coordinate,spacing):
   phase=np.mod(coordinate,spacing);distance=np.minimum(phase,spacing-phase)
   return np.clip((pixel*.5+.008*.5-distance)/pixel,0,.008/pixel)
  coverage=np.maximum(joint_coverage(localAlong+stagger,unitAlong),joint_coverage(localAcross,unitAcross))
  rgb[mask]*=(1-coverage[mask,None]*.20)
 if kind==4:
  # A connected, drawn planted mass inside its exact inventory footprint.
  # A narrow dark underside establishes the observed bed edge; no new greenery.
  insideDistance=ndimage.distance_transform_edt(mask)*pixel
  broadMass=np.clip(insideDistance/1.1,0,1)
  rgb[mask]*=(.82+.18*broadMass[mask,None])
 if kind==5:
  # Quiet source shoreline, with no inferred water depth, wakes or boats.
  insideDistance=ndimage.distance_transform_edt(mask)*pixel
  shore=np.clip(insideDistance/2.0,0,1)
  rgb[mask]*=(.88+.12*shore[mask,None])
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
manifest={k:metadata[k] for k in ['boundsRD','imageSize','worldToImageUV','sourceDecodedSha256','orthophotoSha256','projectionMaximumErrorPixels']};manifest.update(status='review-candidate',texture='neighbourhood-ground.png',areaId='adjoining-neighbourhood',sourceFeatureIds=sourceIds,eligiblePixels=int(eligible.sum()),paintPixels=int(paint.sum()),interpretation='Complete source-feature composition: cool asphalt, pale walking stone, darker parking brick, muted red source tram reservation, connected planted beds and quiet canal shore. All regional forms are retained BGT footprints. Local unit directions follow each source feature. Observed crossing fragments retain their original support; generated aerial-map output is rejected.',notSurveyed='Individual paving unit boundaries and .30m stone and .21x.105m brick drawing units are approximate illustration, not measured slab inventory.',acceptance='Unaccepted whole-neighbourhood actual city candidate.')
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');(source/'drawing/source-marking-review.json').write_text(json.dumps({'sourceSha256':metadata['orthophotoSha256'],'regions':regions,'method':'Observed crossing bars retain source local-contrast support only; no gap filling. Existing reviewed source paint retained at exact RD coordinates.'},indent=2)+'\n');print(json.dumps({'features':len(sourceIds),'paintPixels':int(paint.sum())}))
