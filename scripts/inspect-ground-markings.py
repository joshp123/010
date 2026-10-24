#!/usr/bin/env python3
"""Propose *source-pixel* pale markings for visual classification. Never auto-accept.
Candidates are not geography until reviewed against the dated photograph.
"""
from pathlib import Path
import argparse,json,hashlib
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from scipy import ndimage
ROOT=Path(__file__).resolve().parents[1];SRC=ROOT/'source-data/public-space-pilot';OUT=ROOT/'work/public-space-pilot'
p=argparse.ArgumentParser();p.add_argument('--year',default='2026');args=p.parse_args()
source=Image.open(SRC/f'schiedamseweg-{args.year}.jpg').convert('RGB');rgb=np.asarray(source).astype(float);data=np.load(OUT/'source-mask.npz');surface=data['surface'];eligible=np.isin(surface,[1,3]);brightness=rgb.mean(2);chroma=(rgb.max(2)-rgb.min(2))/np.maximum(rgb.max(2),1)
contrast=brightness-ndimage.median_filter(brightness,size=19)
mask=eligible&(brightness>165)&(chroma<.22)&(contrast>16)
# One-pixel gaps can connect a worn line. Original pixel support is retained
# separately and is the only mask eligible for the final painted marking.
connected=ndimage.binary_closing(mask,iterations=1);labels,count=ndimage.label(connected);objects=ndimage.find_objects(labels);records=[]
for i,box in enumerate(objects,1):
 if box is None:continue
 yy,xx=np.where((labels[box]==i)&mask[box]);n=len(xx)
 if n<9:continue
 width=box[1].stop-box[1].start;height=box[0].stop-box[0].start
 if max(width,height)<5:continue
 records.append({'id':i,'pixelBox':[box[1].start,box[0].start,box[1].stop,box[0].stop],'sourceSupportedPixels':n,'aspect':max(width,height)/max(1,min(width,height)),'status':'unreviewed; may be vehicle, roof lean, pale paving or marking'})
records.sort(key=lambda r:r['sourceSupportedPixels'],reverse=True)
np.savez_compressed(OUT/'marking-candidates.npz',labels=labels,sourceSupport=mask)
(OUT/'marking-candidates.json').write_text(json.dumps({'source':f'schiedamseweg-{args.year}.jpg','imageSha256':hashlib.sha256((SRC/f'schiedamseweg-{args.year}.jpg').read_bytes()).hexdigest(),'candidateCount':len(records),'acceptance':'None. Visual source classification and occlusion exclusion required.','candidates':records},indent=2)+'\n')
for start in range(0,len(records),48):
 page=records[start:start+48];sheet=Image.new('RGB',(1200,150*int(np.ceil(len(page)/6))),'#efeee8');draw=ImageDraw.Draw(sheet)
 for j,r in enumerate(page):
  x0,y0,x1,y1=r['pixelBox'];pad=12;box=(max(0,x0-pad),max(0,y0-pad),min(source.width,x1+pad),min(source.height,y1+pad));im=source.crop(box);im.thumbnail((195,110));x=(j%6)*200;y=(j//6)*150;sheet.paste(im,(x,y+30));draw.text((x+5,y+3),f"ID {r['id']} / {r['sourceSupportedPixels']} px",fill='#28362e')
 sheet.save(OUT/f'marking-candidates-{start//48:02}.jpg',quality=95)
overlay=source.copy();draw=ImageDraw.Draw(overlay)
for r in records:
 x0,y0,x1,y1=r['pixelBox'];draw.rectangle((x0,y0,x1,y1),outline='#ffcc55',width=1);draw.text((x0,y0),str(r['id']),fill='#ffdd66',stroke_width=1,stroke_fill='#222222')
overlay.save(OUT/'marking-candidate-locations.jpg',quality=95);print('Unreviewed candidates:',len(records))
