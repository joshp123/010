# Written by AI on 2026-10-25 by model GPT-6 Astra.
# Deliberate crown composition interpreted from the source envelope and Brixton
# reference: one dominant upper mass, two unequal shoulders, sparse lower mass.
from pathlib import Path
import json
import numpy as np
root=Path(__file__).parent
axis=np.linspace(-.7,.7,23)
grid=np.stack(np.meshgrid(axis,axis,axis,indexing='ij'),-1)
# These are model-composed structural volumes, not random/procedural leaf clumps.
volumes=[((-.06,.275,-.035),(.43,.23,.405)),((.30,.105,-.19),(.215,.235,.25)),((-.235,.015,.255),(.255,.225,.245)),((-.105,-.25,-.10),(.235,.25,.265))]
field=np.full(grid.shape[:-1],-10.)
for centre,radii in volumes:
 p=(grid-centre)/radii
 volume=(1-np.linalg.norm(p,axis=-1))*min(radii)
 # A restrained seam joins adjacent crown shoulders into a continuous canopy.
 k=.14; h=np.maximum(k-np.abs(field-volume),0)/k
 field=np.maximum(field,volume)+h*h*k*.25
# One structural opening between the dominant crown and its lower shoulder.
# The remaining mass stays connected; this is an illustrated foliage break.
cleft=(grid-np.array((.17,.43,-.10)))/np.array((.085,.18,.39))
field=np.minimum(field,(np.linalg.norm(cleft,axis=-1)-1)*.085)
cleft=(grid-np.array((-.27,-.16,.17)))/np.array((.19,.085,.17))
field=np.minimum(field,(np.linalg.norm(cleft,axis=-1)-1)*.085)
corner=np.array([(0,0,0),(1,0,0),(1,1,0),(0,1,0),(0,0,1),(1,0,1),(1,1,1),(0,1,1)])
tetras=[[0,5,1,6],[0,1,2,6],[0,2,3,6],[0,3,7,6],[0,7,4,6],[0,4,5,6]]
vertices=[]
for cell in np.ndindex(*(np.array(field.shape)-1)):
 ids=corner+cell; values=field[tuple(ids.T)]
 if values.min()>0 or values.max()<0:continue
 points=grid[tuple(ids.T)]
 for tetra in tetras:
  p=points[tetra];v=values[tetra];inside=v>0
  if inside.all() or not inside.any():continue
  crossings=[]
  for a in range(4):
   for b in range(a+1,4):
    if inside[a]!=inside[b]:crossings.append(p[a]+(p[b]-p[a])*(v[a]/(v[a]-v[b])))
  crossings=np.array(crossings);centre=crossings.mean(0)
  outward=p[~inside].mean(0)-p[inside].mean(0);outward/=np.linalg.norm(outward)
  right=crossings[0]-centre;right/=np.linalg.norm(right);up=np.cross(outward,right)
  order=np.argsort(np.arctan2((crossings-centre)@up,(crossings-centre)@right));polygon=crossings[order]
  for j in range(1,len(polygon)-1):vertices.extend([polygon[0],polygon[j],polygon[j+1]])
vertices=np.array(vertices)
unique,indices=np.unique(np.round(vertices,6),axis=0,return_inverse=True)
lo=unique.min(0);hi=unique.max(0);unique=(unique-lo)/(hi-lo)-.5
triangles=indices.reshape(-1,3)
area=np.linalg.norm(np.cross(unique[triangles[:,1]]-unique[triangles[:,0]],unique[triangles[:,2]]-unique[triangles[:,0]]),axis=1)
triangles=triangles[area>1e-9]
(root/'crown-connected-masses.js').write_text('// Written by AI on 2026-10-25 by model GPT-6 Astra.\nexport const crownPositions='+json.dumps(unique.round(6).ravel().tolist(),separators=(',',':'))+';\nexport const crownIndices='+json.dumps(triangles.ravel().tolist(),separators=(',',':'))+';\n')
print({'vertices':len(unique),'triangles':len(triangles)})
