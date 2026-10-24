#!/usr/bin/env python3
"""Bounded source-visible road-paint detail for the selected block's shared frontage.
No photograph RGB reaches the artwork; local contrast recovers visibly shaded paint.
"""
from pathlib import Path
import json,hashlib
import numpy as np
from PIL import Image,ImageDraw
from scipy import ndimage
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'source-data/public-space-pilot';WORK=ROOT/'work/public-space-pilot';OUT=ROOT/'public/data/ground-artwork-frontage';OUT.mkdir(parents=True,exist_ok=True)
sourcePath=SRC/'schiedamseweg-2026.jpg';source=Image.open(sourcePath).convert('RGB');rgb=np.array(source).astype(float);h,w=rgb.shape[:2];yy,xx=np.mgrid[:h,:w];brightness=rgb.mean(2);local=ndimage.median_filter(brightness,size=19)
regions=[('north crossing west',[0,230,55,295]),('tram crossing west',[0,320,35,420]),('north crossing middle',[323,295,365,341]),('north crossing east',[702,363,753,419]),('south speed30',[57,421,93,470]),('north speed30',[1160,447,1193,487])]
allowed=np.zeros((h,w),bool)
for _,(x0,y0,x1,y1) in regions:allowed[y0:y1,x0:x1]=True
northDashes=(xx>=755)&(xx<=1245)&(abs(yy-(.149*xx+275))<6)
southDashes=(((xx>=575)&(xx<=650))|((xx>=900)&(xx<=1230)))&(abs(yy-(.15*xx+461))<7)
crossingAndSpeed=allowed.copy();allowed|=northDashes|southDashes
# Each region has been inspected in the dated photograph; only locally pale
# source pixels survive. Occluded/indistinct portions remain missing.
supported=(brightness>42)&((brightness-local)>9)&((rgb.max(2)-rgb.min(2))<np.maximum(42,brightness*.35))
# Reject isolated glints/pole-edge fragments within the dash review corridors.
# Keep only short source-supported horizontal components; never fill gaps.
dashLabels,n=ndimage.label(supported&(northDashes|southDashes));dashKeep=np.zeros((h,w),bool)
for i,box in enumerate(ndimage.find_objects(dashLabels),1):
 if box is None:continue
 pixels=dashLabels[box]==i;dx=box[1].stop-box[1].start;dy=box[0].stop-box[0].start
 if pixels.sum()>=5 and dx>=4 and dy<=max(4,dx*.5):dashKeep[box]|=pixels
paint=(supported&crossingAndSpeed)|dashKeep
semantic=np.load(WORK/'source-mask.npz');meta=json.loads((WORK/'source-mask.json').read_text());roadIds=[f['batchId'] for f in meta['features'] if f['attributes'].get('FUNCTIE','').lower() in {'rijbaan lokale weg','ov-baan'} or f['batchId']==310];paint&=np.isin(semantic['feature'],roadIds)
base=np.array(Image.open(ROOT/'public/data/ground-artwork/schiedamseweg-ground.png'));paint&=base[:,:,3]>0;base[paint,:3]=[218,216,201]
# Model-painted low planting stays inside surveyed green ground footprints.
# Existing source height and real canopy geometry remain untouched.
plantPath=SRC/'generation/planted-ground-paint.png';plant=np.array(Image.open(plantPath).convert('RGB').resize((50,50),Image.Resampling.LANCZOS));green=semantic['surface']==4
mx=np.abs((xx%100)-50).clip(0,49);my=np.abs((yy%100)-50).clip(0,49);base[green,:3]=plant[my[green],mx[green]];base[green,3]=255
nearest=ndimage.distance_transform_edt(base[:,:,3]==0,return_distances=False,return_indices=True);empty=base[:,:,3]==0;base[empty,:3]=base[nearest[0][empty],nearest[1][empty],:3]
Image.fromarray(base).save(OUT/'frontage-ground.png')
overlay=np.array(source);overlay[paint]=[255,210,60];Image.fromarray(overlay).save(WORK/'street-paint-source-review.png');Image.fromarray((paint*255).astype('uint8')).save(WORK/'street-paint-detail-mask.png')
manifest=json.loads((ROOT/'public/data/ground-artwork/manifest.json').read_text());greenIds=[str(f['attributes'].get('DGDT_ID',f['id'])) for f in meta['features'] if (green&(semantic['feature']==f['batchId'])).any()];manifest['sourceFeatureIds']=sorted(set(manifest['sourceFeatureIds']+greenIds));oldPaint=np.array(Image.open(WORK/'accepted-source-paint.png'))>0;manifest['paintPixels']=int((oldPaint|paint).sum());manifest['eligiblePixels']=int((base[:,:,3]>0).sum())
manifest.update(plantMaterialSha256=hashlib.sha256(plantPath.read_bytes()).hexdigest(),plantMaterialInterpretation='Painted low planted surface inside native green footprints; no new bushes, crown geometry or heights.',texture='frontage-ground.png',areaId='schiedamseweg-frontage',paintDetailPixels=int(paint.sum()),sourcePaintDetail='Verified local-contrast source pixels inside individually inspected crossing/speed and cycle-dash regions; no photo RGB, no continuation behind cars/shadows.');(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
review={'sourceSha256':hashlib.sha256(sourcePath.read_bytes()).hexdigest(),'regions':regions,'northCycleDashBand':{'xRange':[755,1245],'sourcePixelY':'.149*x+275','halfWidth':6},'southCycleDashBand':{'xRanges':[[575,650],[900,1230]],'sourcePixelY':'.15*x+461','halfWidth':7},'method':'Review regions constrain original-image local-contrast support. They are not generated stroke geometry. Dash components reject isolated glints and steep pole-edge fragments without filling any gap. Thresholds retain only actual visibly pale pixels, recoloured ivory.','paintDetailPixels':int(paint.sum()),'rails':'Not added: overhead-wire shadows make some apparent linear detail ambiguous. No continuous rail tracing inferred.'};(SRC/'street-detail-review.json').write_text(json.dumps(review,indent=2)+'\n');print(int(paint.sum()))
