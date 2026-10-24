from pathlib import Path
import sys,json,hashlib,zipfile,os
import numpy as np
from PIL import Image
from scipy import ndimage as nd
R=Path(__file__).resolve().parent;P=R.parent;sys.path.insert(0,str(P))
import row_probe as block
from surface_bake import bake
r=block.r;source_shapes=[a.shape for a in r.textures]
views=[(a,R/f'plane-{a}.png',0,.55) for a in [0,90,180,270]]+[(0,P/'clean-plane-roof.png',90,.3)]
albedo,scores=bake(r,views)
r.textures=albedo
# Reuse audited source-invalid plane material completion, without changing delivered candidate files.
code=(P/'complete_materials.py').read_text();start=code.index('records=json.loads');end=code.index('for a in [30,120,210,300]:')
exec(code[start:end],{'r':r,'R':P,'np':np,'json':json})
# Source-audited rear plane 8: its lower texture is tree-occluded. Preserve all interpreted pixels;
# complete only the remaining photographic fallback with adjacent observed pale render.
q=json.loads((P/'plane-audit.json').read_text())[8]
for pi,tri in q['triangles']+[[8,21],[8,22]]:
 p=r.prims[pi];t=tri*3;tex=albedo[r.mat_texture[p['mat']]];sc=scores[r.mat_texture[p['mat']]];h,w=tex.shape[:2];uv=p['uv'][t:t+3]*[w,h]
 x0,y0=np.maximum(np.floor(uv.min(0)).astype(int),0);x1,y1=np.minimum(np.ceil(uv.max(0)).astype(int),[w-1,h-1]);ax,ay=uv[0];bx,by=uv[1];cx,cy=uv[2];den=(by-cy)*(ax-cx)+(cx-bx)*(ay-cy)
 if abs(den)<1e-8:continue
 xx,yy=np.meshgrid(np.arange(x0,x1+1)+.5,np.arange(y0,y1+1)+.5);a=((by-cy)*(xx-cx)+(cx-bx)*(yy-cy))/den;b=((cy-ay)*(xx-cx)+(ax-cx)*(yy-cy))/den;c=1-a-b
 valid=(a>=0)&(b>=0)&(c>=0)&((sc[y0:y1+1,x0:x1+1]==0)|((pi==8) and (tri in [21,22])))
 xyz=a[...,None]*p['pos'][t]+b[...,None]*p['pos'][t+1]+c[...,None]*p['pos'][t+2]
 grain=np.sin(xyz[...,0]*133+xyz[...,2]*93+xyz[...,1]*79)*.006
 color=np.clip(np.array([.36,.37,.38] if pi==8 and tri in [21,22] else [.79,.775,.73])+grain[...,None],0,1)
 tex[y0:y1+1,x0:x1+1][valid]=color[valid]
(R/'rear-material-completion.json').write_text(json.dumps({'plane':q,'operation':'Unpainted, tree-occluded source texels only; adjacent observed pale render continued without openings. All previously interpreted pixels retained.'},indent=2))
# Small nearest-edge atlas gutters stop photographic bleed at rasterized UV boundaries.
for i,(tex,s) in enumerate(zip(albedo,scores)):
 valid=s>0
 if not valid.any():continue
 dist,ind=nd.distance_transform_edt(~valid,return_indices=True);edge=(dist>0)&(dist<=1.5)
 tex[edge]=tex[ind[0][edge],ind[1][edge]]
np.savez_compressed(R/'albedo-writing.npz',**{f'texture_{i}':(a.clip(0,1)*255).astype('uint8') for i,a in enumerate(albedo)})
with zipfile.ZipFile(R/'albedo-writing.npz') as zz:assert zz.testzip() is None
os.replace(R/'albedo-writing.npz',R/'albedo.npz')
for i,a in enumerate(albedo):Image.fromarray((a.clip(0,1)*255).astype('uint8')).save(R/f'albedo-{i:02}.png')
# Encode source-supported glazing + per-opening stable phase + identifier in a separate UV channel image.
features=[];maskviews=[];gid=0
for angle in [0,90,180,270]:
 records=json.loads((R/f'source-glazing-{angle}.json').read_text());mono=np.array(Image.open(R/f'source-glazing-{angle}.png'))>0;im=np.zeros((1200,1200,3),np.uint8)
 ids=np.array(r.render(angle,'batch_id',1200,elevation=0)[0])[:,:,0]
 for f in records:
  gid+=1;l,t,rr,bot=f['source_bounds'];sub=mono[t:bot+1,l:rr+1]
  token=f'{angle}:{l},{t},{rr},{bot}';phase=hashlib.sha256(token.encode()).digest()[0]
  im[t:bot+1,l:rr+1][sub]=[255,phase,gid]
  bid=int(ids[(t+bot)//2,(l+rr)//2]);f.update({'global_glazing_region_id':gid,'view_angle':angle,'batch_id':bid,'bag_id':r.batch_table['id'][bid],'stable_phase':phase,'binding':'original UVs; surface depth and normal gated projection'});features.append(f)
 path=R/f'glazing-phase-input-{angle}.png';Image.fromarray(im).save(path);maskviews.append((angle,path,0,.55))
r.textures=[np.zeros(sh) for sh in source_shapes]
encoded,_=bake(r,maskviews)
emissions=[];masks=[]
for i,(data,alb) in enumerate(zip(encoded,albedo)):
 glass=(data[:,:,0]>.8)
 # Conservative intersection with illustrated cream frames and warm masonry; never emit them.
 glass &= (alb.mean(2)<.66)&(alb[:,:,2]>alb[:,:,0]*.78)
 data[~glass]=0;masks.append(data)
 phase=np.round(data[:,:,1]*255).astype(int)
 intensity=(.45+.35*(phase%53)/52)*(phase<190)*glass
 warm=np.empty_like(alb);warm[:]=[1.,.68,.34]
 warm[(phase%3)==0]=[.85,.72,.49]
 em=warm*intensity[...,None];emissions.append(em)
 Image.fromarray((glass*255).astype('uint8')).save(R/f'glazing-mask-{i:02}.png')
 Image.fromarray((data.clip(0,1)*255).astype('uint8')).save(R/f'glazing-phase-{i:02}.png')
 Image.fromarray((em.clip(0,1)*255).astype('uint8')).save(R/f'emission-{i:02}.png')
np.savez_compressed(R/'emission.npz',**{f'texture_{i}':(a*255).astype('uint8') for i,a in enumerate(emissions)})
(R/'glazing-features.json').write_text(json.dumps({'regions':features,'region_count':gid,'contract':'Source-observed glazing only. Unobserved/occluded openings excluded. Phase represents illustrative occupancy, never real observation. R=glazing, G=phase, B=region ID in the phase PNGs. Separate emission maps; no albedo brightness-based night grid. Partial facade inventory, not a claim that every real window is identified.'},indent=2))
for night in [False,True]:
 r.textures=[np.clip(a*np.array([.20,.24,.32])+e*.9,0,1) for a,e in zip(albedo,emissions)] if night else albedo
 for angle in [0,30,60,90,120,150,180,210,240,270,300,330]:
  im=r.render(angle,'source',1000)[0]
  if night:
   a=np.array(im);a[(a==[232,234,229]).all(2)]=[18,24,35];im=Image.fromarray(a)
  im.save(R/f'{"night" if night else "day"}-{angle}.png')
  im.resize((420,420),Image.Resampling.LANCZOS).save(R/f'{"night" if night else "day"}-city-{angle}.png')
print('completed',gid,'source-observed glazing regions')
