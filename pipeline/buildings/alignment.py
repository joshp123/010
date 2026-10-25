"""Written by AI on 2026-10-25 by model GPT-6.1 Sol.

Measure local roof/photo edge offsets. Never moves scene geometry. The edge-fit
result is an image comparison, not surveyed ground-truth accuracy.
"""
import hashlib,json
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from scipy.ndimage import gaussian_filter,map_coordinates
from shapely.geometry import shape
from shapely import union_all
ROOT=Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
OUT=ROOT/'renders/debug-buildings'
TILE='x90250_y436000'

def main():
 aerial=Image.open(OUT/f'aerial-{TILE}.jpg').convert('RGB')
 rgb=np.asarray(aerial)/255.;gray=rgb@np.array([.2126,.7152,.0722]);smooth=gaussian_filter(gray,.8);gy,gx=np.gradient(smooth)
 features=json.loads((OUT/f'projected-roof-edges-{TILE}.json').read_text())['features']
 results=[]
 for label,bags in [('low_courtyard_sheds',['0599100100019948','0599100100019949']),('tall_northern_tower',['0599100000752501'])]:
  lines=[shape(f['geometry']) for f in features if f['properties']['bag_id'] in bags]
  # Union boundaries retains the shared seam. It is not used for the fit: polygon
  # union removes shared walls, leaving only the visible external roof boundary.
  from shapely.ops import polygonize
  polygons=[p for line in lines for p in polygonize(line)]
  boundary=union_all(polygons).exterior
  coords=np.array(boundary.coords);pixels=np.column_stack(((coords[:,0]-90250)*10,(436250-coords[:,1])*10));samples=[];normals=[]
  for a,b in zip(pixels[:-1],pixels[1:]):
   length=np.linalg.norm(b-a)
   if length<6:continue
   # Avoid ambiguous corners: sample the central 70% of each roof edge.
   t=np.linspace(.15,.85,max(4,int(length*.7)));samples.extend(a+(b-a)*t[:,None]);normal=np.array([b[1]-a[1],a[0]-b[0]])/length;normals.extend(np.tile(normal,(len(t),1)))
  samples=np.array(samples);normals=np.array(normals)
  candidates=[];search=5 if label=='low_courtyard_sheds' else 15
  for dy in np.arange(-search,search+.01,.25):
   for dx in np.arange(-search,search+.01,.25):
    xy=samples+[dx,dy];horizontal=map_coordinates(gx,[xy[:,1],xy[:,0]],order=1,mode='nearest');vertical=map_coordinates(gy,[xy[:,1],xy[:,0]],order=1,mode='nearest');score=np.mean(np.abs(horizontal*normals[:,0]+vertical*normals[:,1]));candidates.append((score,dx,dy))
  score,dx,dy=max(candidates)
  item={'label':label,'bag_ids':bags,'offset_pixels_source_to_photo':[dx,dy],'offset_rd_m':[dx*.1,-dy*.1],'offset_m':float(np.hypot(dx,dy)*.1),'score':float(score),'search_pixels':search,'search_step_pixels':.25,'edge_samples':len(samples)}
  results.append(item)
  x0,y0=np.floor(pixels.min(axis=0)-25).astype(int);x1,y1=np.ceil(pixels.max(axis=0)+25).astype(int);crop=aerial.crop((x0,y0,x1,y1)).resize(((x1-x0)*4,(y1-y0)*4));draw=ImageDraw.Draw(crop)
  for delta,color in [(np.array([0,0]),'#00ffff'),(np.array([dx,dy]),'#ff40f0')]:
   points=[tuple((v+delta-[x0,y0])*4) for v in pixels];draw.line(points,fill=color,width=2)
  crop.save(OUT/f'alignment-{label}.png')
 report={'written_by':'AI, GPT-6.1 Sol, 2026-10-25','tile':TILE,'image':str(OUT/f'aerial-{TILE}.jpg'),'image_sha256':hashlib.sha256((OUT/f'aerial-{TILE}.jpg').read_bytes()).hexdigest(),'method':'Fit a rigid XY translation of the external source roof outline to maximum mean absolute aerial intensity gradient normal to the roof edges. 0.8px Gaussian smoothing, central70% of edges, +/-5px local search for sheds, +/-15px for tower, at0.25px. The unconstrained shed optimum matched nearby paving instead of the roof and was rejected after visual inspection. Cyan source; magenta fitted photo boundary. No geometry adjustment. Inspect crops to reject spurious edge matches. Sampling scale0.1m/px; search resolution is not survey accuracy.','samples':results}
 (OUT/'alignment-measurement.json').write_text(json.dumps(report,indent=2));print(json.dumps(results,indent=2))
if __name__=='__main__':main()
