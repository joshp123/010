#!/usr/bin/env python3
"""Compile model-painted materials inside exact surveyed footprints; no photo RGB.
Run prepare-public-space-mask.py and inspect-ground-markings.py first.
The original photo supplies *reviewed binary paint shapes*, not texture color.
"""
from pathlib import Path
import json,hashlib
import numpy as np
from scipy import ndimage
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'source-data/public-space-pilot';WORK=ROOT/'work/public-space-pilot';OUT=ROOT/'public/data/ground-artwork';OUT.mkdir(parents=True,exist_ok=True)
metadata=json.loads((WORK/'source-mask.json').read_text());review=json.loads((SRC/'marking-review.json').read_text());data=np.load(WORK/'source-mask.npz');feature=data['feature'];surface=data['surface'];h,w=feature.shape
swatch_path=SRC/'generation/material-swatches.png';swatches=np.asarray(Image.open(swatch_path).convert('RGB')).astype(float);sh,sw=swatches.shape[:2];yy,xx=np.mgrid[:h,:w];angle=np.arctan2(181,1200);u=xx*np.cos(angle)+yy*np.sin(angle);v=-xx*np.sin(angle)+yy*np.cos(angle)
# Model swatches are material fields only. Mirror repeats avoid discontinuities,
# and source-world scale is explicit; individual joints are illustration.
def sample(quadrant,metres):
 qx,qy=quadrant;patch=swatches[int(qy*sh/2+sh*.025):int((qy+1)*sh/2-sh*.025),int(qx*sw/2+sw*.025):int((qx+1)*sw/2-sw*.025)];patch=np.asarray(Image.fromarray(patch.astype('uint8')).resize((round(metres/.08),round(metres/.08)),Image.Resampling.LANCZOS)).astype(float);ph,pw=patch.shape[:2]
 def mirror(t):return 1-np.abs(np.mod(t,2)-1)
 ix=mirror(u/(metres/.08))*(pw-1);iy=mirror(v/(metres/.08))*(ph-1)
 return np.stack([ndimage.map_coordinates(patch[:,:,c],[iy,ix],order=1,mode='reflect') for c in range(3)],axis=-1)
materials=[sample((0,0),1.2),sample((1,0),1.2),sample((0,1),1.2),sample((1,1),1.6)]
# Same material directions throughout this surveyed street grid. Source physical
# class + function chooses surface; only the tram reservation has visual override.
rgb=np.zeros((h,w,3),float);eligible=np.zeros((h,w),bool);kind=np.full((h,w),-1,np.int8);ids=[]
for f in metadata['features']:
 a=f['attributes'];bid=f['batchId'];mask=feature==bid;physical=a.get('FYSIEKVK','').lower();purpose=a.get('FUNCTIE','').lower();category=a.get('KLASSE_IMG','').lower()
 if category not in {'wegdeel','ondersteunend wegdeel'} and bid!=310:continue
 if not ('open verharding' in physical or 'gesloten verharding' in physical):continue
 k=0 if 'gesloten' in physical else (1 if purpose in {'voetpad','berm'} else 2)
 if bid==310:k=3
 rgb[mask]=materials[k][mask];kind[mask]=k;eligible[mask]=True;ids.append(str(a.get('DGDT_ID',f['id'])))
# Narrow boundary rendering follows actual shared material boundaries only.
# It is a drawn edge, not new curb geometry or white lane paint.
edge=np.zeros((h,w),bool)
for axis in [0,1]:
 adjacent=np.roll(kind,1,axis=axis);edge|=(kind!=adjacent)&(kind>=0)&(adjacent>=0)
edge[0,:]=edge[-1,:]=edge[:,0]=edge[:,-1]=False
rgb[edge]*=.79
# Bounded native source paint support, intentionally coloured ivory; no original
# photo RGB, source shadows, vehicles or model-created markings can enter output.
candidates=np.load(WORK/'marking-candidates.npz');paint=np.isin(candidates['labels'],review['acceptedComponents'])&candidates['sourceSupport']&eligible&np.isin(kind,[0,3])
paintTexture=materials[0].mean(2);paintTexture=(paintTexture-ndimage.gaussian_filter(paintTexture,3))*.17
for c,base in enumerate([218,216,201]):rgb[:,:,c][paint]=np.clip(base+paintTexture[paint],0,255)
# Bleed colour under transparent texels to prevent black interpolation fringes.
# Alpha remains the exact source mask; this adds no geographic coverage.
nearest=ndimage.distance_transform_edt(~eligible,return_distances=False,return_indices=True)
rgb[~eligible]=rgb[nearest[0][~eligible],nearest[1][~eligible]]
rgba=np.dstack([np.clip(rgb,0,255).astype('uint8'),(eligible*255).astype('uint8')]);Image.fromarray(rgba).save(OUT/'schiedamseweg-ground.png')
# Review neutral context: no photographic island and unknown areas conspicuously
# blank. The runtime consumes alpha only on native eligible source features.
preview=np.full((h,w,3),[229,228,220],np.uint8);preview[eligible]=rgba[:,:,:3][eligible];Image.fromarray(preview).save(WORK/'compiled-ground-review.png')
Image.fromarray((paint*255).astype('uint8')).save(WORK/'accepted-source-paint.png')
source=Image.open(SRC/'schiedamseweg-2026.jpg').convert('RGB');interpreted=Image.fromarray(preview);sheet=Image.new('RGB',(1600,875),'#ecebe5');d=ImageDraw.Draw(sheet);d.text((20,15),'2026 source: cars / shadows / roof lean retained only as evidence',fill='#252a27');d.text((820,15),'Compiled illustration: exact BGT masks + reviewed source paint',fill='#252a27');sheet.paste(source.resize((800,800)),(0,55));sheet.paste(interpreted.resize((800,800)),(800,55));sheet.save(ROOT/'docs/images/ground-artwork-source-comparison.png')
manifest={'status':'review-candidate','texture':'schiedamseweg-ground.png','boundsRD':metadata['boundsRD'],'imageSize':[w,h],'worldToImageUV':metadata['worldToImageUV'],'sourceFeatureIds':ids,'sourceDecodedSha256':metadata['sourceDecodedSha256'],'orthophotoSha256':metadata['orthophotoSha256'],'materialSwatchSha256':hashlib.sha256(swatch_path.read_bytes()).hexdigest(),'paintPixels':int(paint.sum()),'eligiblePixels':int(eligible.sum()),'projectionMaximumErrorPixels':metadata['projectionMaximumErrorPixels'],'generation':'Native imagegen material swatches; geographic model output rejected. No photographic RGB. Exact source-supported paint masks.','notSurveyed':'Individual slab/brick joints are bounded material illustration, not individual mapped objects.','acceptance':'Pending actual WebGL front/rear/phone/night review.'}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');(WORK/'compilation-report.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps({k:manifest[k] for k in ['paintPixels','eligiblePixels','projectionMaximumErrorPixels']}))
