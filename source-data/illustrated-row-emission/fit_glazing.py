"""Source-anchored fitting from replaceable model window proposals.
This diagnostic covers 28 visually observed upper street windows, not a generic grid.
"""
from pathlib import Path
from PIL import Image,ImageDraw
from scipy import ndimage as nd
import numpy as np,json
R=Path(__file__).resolve().parent;P=R.parent
src=np.array(Image.open(P/'row-plane-180.png').convert('RGB')).astype(float)/255
art=np.array(Image.open(P/'paint-plane-180.png').convert('RGB').resize((1200,1200))).astype(float)/255
proposals=json.loads((P/'window-registration-diagnostic.json').read_text())['paint-plane-180']
mask=np.zeros((1200,1200),np.uint8);records=[];annotation=Image.fromarray((src*255).astype('uint8'));d=ImageDraw.Draw(annotation)
for k,bb in enumerate(sorted(proposals,key=lambda b:(b[1]//100,b[0]))):
 x0,y0,x1,y1=bb;pad=5;xa=max(x0-pad,0);ya=max(y0-pad,0);xb=x1+pad;yb=y1+pad
 a=src[ya:yb,xa:xb];dark=(a.mean(2)<.58)&((a[...,0]-a[...,2])<.05)
 # Source observations within proposal extent; reject fringe and isolated speckles.
 dark=nd.binary_opening(dark,iterations=1);yy,xx=np.where(dark)
 if len(xx)<60:continue
 l,t=np.percentile(xx,3),np.percentile(yy,3);rr,bot=np.percentile(xx,97),np.percentile(yy,97)
 l,rr=int(round(l+xa))+1,int(round(rr+xa))-1;t,bot=int(round(t+ya))+1,int(round(bot+ya))-1
 if rr-l<8 or bot-t<20:continue
 region=src[t:bot+1,l:rr+1];profile=np.median(region[:,max(1,(rr-l)//5):max(2,4*(rr-l)//5)],axis=1).mean(1)
 # Straight transom rails are supported by elevated horizontal source intensity.
 rail=(profile>max(.40,float(np.median(profile)+.12)))
 rail[:3]=False;rail[-3:]=False
 bands=[];lab,n=nd.label(rail)
 for i,sl in enumerate(nd.find_objects(lab),1):
  if sl is None:continue
  st,sp=sl[0].start,sl[0].stop
  if 1<=sp-st<=10:bands.append([t+st,t+sp])
 # Clean pane rectangles, never trace noisy texture edges.
 mask[t:bot+1,l:rr+1]=255
 for a,b in bands:mask[max(a-1,t):min(b+1,bot+1),l:rr+1]=0
 d.rectangle([l,t,rr,bot],outline='#00ff99',width=2)
 for a,b in bands:d.line([l,a,rr,a],fill='#00ff99',width=2)
 records.append({'id':k,'source_bounds':[l,t,rr,bot],'source_transom_bands':bands,'proposal_bounds':bb,'source':'row-plane-180.png','confidence':'observed opening; source-fitted extent, rectified drawing approximation','emission_state':'illustrative, not observed occupancy'})
Image.fromarray(mask).save(R/'source-glazing-180.png');annotation.save(R/'source-glazing-180-annotation.png')
(R/'source-glazing-180.json').write_text(json.dumps(records,indent=2));print('source fitted openings',len(records))
