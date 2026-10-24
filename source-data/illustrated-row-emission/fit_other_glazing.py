from pathlib import Path
from PIL import Image,ImageDraw
from scipy import ndimage as nd
import numpy as np,json
R=Path(__file__).resolve().parent;P=R.parent
# Independent observed source-region proposals. These are source observations, not an assumed grid.
proposals={
90:[[500,400,552,493],[604,400,655,493],[704,400,755,493],[500,553,550,645],[604,553,655,645],[704,553,754,645],[500,705,551,797],[95,410,149,502],[185,410,239,502],[95,557,147,648],[185,557,239,648],[90,707,150,763],[180,707,240,763]],
270:[[110,440,133,526],[289,440,317,507],[381,440,409,507],[460,446,500,520],[531,446,572,520],[112,588,135,679],[290,588,317,675],[382,587,410,674],[459,591,504,674],[532,591,575,674],[425,735,471,810],[542,731,584,811],[678,731,712,811],[736,730,767,811]],
0:[[91,396,139,425],[275,386,294,425],[420,386,445,425],[576,386,602,425],[77,480,122,535],[157,486,177,524],[225,500,242,532],[288,501,310,541],[320,501,336,539],[380,490,420,538],[430,492,446,532],[923,544,971,590]]}
for angle,boxes in proposals.items():
 src=np.array(Image.open(P/f'row-plane-{angle}.png').convert('RGB')).astype(float)/255
 mask=np.zeros((1200,1200),np.uint8);annotation=Image.fromarray((src*255).astype('uint8'));d=ImageDraw.Draw(annotation);records=[]
 for k,bb in enumerate(boxes):
  x0,y0,x1,y1=bb;a=src[y0:y1+1,x0:x1+1]
  # Constrain source fitting inside an independently observed pane envelope.
  dark=(a.mean(2)<.64)&((a[...,0]-a[...,2])<.07);yy,xx=np.where(dark)
  if len(xx)<20:continue
  l,t=int(round(np.percentile(xx,4)+x0)),int(round(np.percentile(yy,4)+y0));rr,bot=int(round(np.percentile(xx,96)+x0)),int(round(np.percentile(yy,96)+y0))
  if rr-l<5 or bot-t<12:continue
  reg=src[t:bot+1,l:rr+1];bands=[];vbars=[]
  for ax in [0,1]:
   profile=np.median(reg,axis=ax).mean(1);rail=profile>max(.48,float(np.median(profile)+.17));rail[:2]=False;rail[-2:]=False
   lab,n=nd.label(rail)
   for sl in nd.find_objects(lab):
    st,sp=sl[0].start,sl[0].stop
    if 1<=sp-st<=8:
     (vbars if ax==0 else bands).append([(l if ax==0 else t)+st,(l if ax==0 else t)+sp])
  mask[t:bot+1,l:rr+1]=255
  for aa,b in bands:mask[aa:b,l:rr+1]=0
  for aa,b in vbars:mask[t:bot+1,aa:b]=0
  d.rectangle([l,t,rr,bot],outline='#00ff99',width=2)
  for aa,b in bands:d.line([l,aa,rr,aa],fill='#00ff99',width=2)
  for aa,b in vbars:d.line([aa,t,aa,bot],fill='#00ff99',width=2)
  records.append({'id':k,'source_bounds':[l,t,rr,bot],'source_transom_bands':bands,'source_mullion_bands':vbars,'proposal_bounds':bb,'source':f'row-plane-{angle}.png','confidence':'observed opening; bounded source-fitted extent; uncertain hidden openings excluded','proposal_method':'independent visible-source review for this diagnostic; replaceable by model proposals with same evidence checks','emission_state':'illustrative, not observed occupancy'})
 Image.fromarray(mask).save(R/f'source-glazing-{angle}.png');annotation.save(R/f'source-glazing-{angle}-annotation.png');(R/f'source-glazing-{angle}.json').write_text(json.dumps(records,indent=2));print(angle,len(records))
