# Written by AI on 2026-10-25 by model GPT-6 Astra.
# Convert six model-composed orthographic silhouettes to one shared 3D form.
from pathlib import Path
import json
import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, map_coordinates
root=Path(__file__).parent
image=np.asarray(Image.open(root/'model-drawn-contours.png').convert('RGBA'))
bases=np.array([((1,0,0),(0,-1,0)),((-1,0,0),(0,-1,0)),((0,0,-1),(0,-1,0)),((0,0,1),(0,-1,0)),((1,0,0),(0,0,1)),((1,0,0),(0,0,-1))])
axis=np.linspace(-.57,.57,17)
grid=np.stack(np.meshgrid(axis,axis,axis,indexing='ij'),-1)
field=np.full(grid.shape[:-1],np.inf)
for k,base in enumerate(bases):
 mask=image[(k//3)*512:(k//3+1)*512,(k%3)*512:(k%3+1)*512,3]>127
 signed=distance_transform_edt(mask)-distance_transform_edt(~mask)
 projection=grid@base.T*420+256
 sample=map_coordinates(signed,[projection[...,1],projection[...,0]],order=1,mode='constant',cval=-100)
 field=np.minimum(field,sample)
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
  order=np.argsort(np.arctan2((crossings-centre)@up,(crossings-centre)@right))
  polygon=crossings[order]
  for j in range(1,len(polygon)-1):vertices.extend([polygon[0],polygon[j],polygon[j+1]])
vertices=np.array(vertices)
unique,indices=np.unique(np.round(vertices,6),axis=0,return_inverse=True)
# Keep the inventory envelope exactly; the drawn surface is an interpretation.
coordinates=unique.copy()
lo=unique.min(0);hi=unique.max(0);unique=(unique-lo)/(hi-lo)-.5
triangles=indices.reshape(-1,3)
area=np.linalg.norm(np.cross(unique[triangles[:,1]]-unique[triangles[:,0]],unique[triangles[:,2]]-unique[triangles[:,0]]),axis=1)
triangles=triangles[area>1e-9]
(root/'crown-contour-hull.js').write_text('// Written by AI on 2026-10-25 by model GPT-6 Astra.\nexport const crownPositions='+json.dumps(unique.round(6).ravel().tolist(),separators=(',',':'))+';\nexport const crownCoordinates='+json.dumps(coordinates.round(6).ravel().tolist(),separators=(',',':'))+';\nexport const crownIndices='+json.dumps(triangles.ravel().tolist(),separators=(',',':'))+';\n')
print({'vertices':len(unique),'triangles':len(triangles),'drawnBoundsBeforeEnvelopeFit':[lo.tolist(),hi.tolist()]})
