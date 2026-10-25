# Written by AI on 2026-10-25 by model GPT-6 Astra.
# Explicit model-composed crown contours. One closed mass, no repeated spheres,
# silhouette intersections, random leaves, internal holes or invented branches.
from pathlib import Path
import json, math
import numpy as np
radius=[1,.96,1,.85,.98,.90,.96,.88,.99,.94,.80,.96]
rings=[
 (.10,[-.44,-.47,-.45,-.48,-.50,-.46,-.44,-.42,-.47,-.50,-.45,-.44],(.01,-.03)),
 (.26,[-.31,-.36,-.25,-.28,-.42,-.35,-.27,-.31,-.36,-.30,-.34,-.28],(-.06,.02)),
 (.44,[-.12,-.08,-.14,-.03,-.07,-.15,-.10,-.05,-.15,-.10,-.04,-.10],(-.02,.01)),
 (.50,[.13,.22,.28,.25,.16,.29,.22,.15,.25,.22,.17,.26],(0,0)),
 (.27,[.39,.42,.50,.45,.37,.43,.40,.37,.42,.44,.40,.46],(-.08,-.04)),
]
points=[]
for scale,heights,centre in rings:
 for i,(r,y) in enumerate(zip(radius,heights)):
  theta=i*math.tau/12
  points.append((centre[0]+math.cos(theta)*r*scale,y,centre[1]+math.sin(theta)*r*scale))
triangles=[]
for ring in range(len(rings)-1):
 for i in range(12):
  a=ring*12+i;b=ring*12+(i+1)%12;c=(ring+1)*12+i;d=(ring+1)*12+(i+1)%12
  triangles.extend([(a,c,b),(b,c,d)])
points.extend([(0,-.48,0),(-.08,.445,-.04)])
for i in range(12):triangles.extend([(60,i,(i+1)%12),(61,48+(i+1)%12,48+i)])
points=np.array(points);lo=points.min(0);hi=points.max(0);points=(points-lo)/(hi-lo)-.5
root=Path(__file__).parent
(root/'crown-structured-contours.js').write_text('// Written by AI on 2026-10-25 by model GPT-6 Astra.\nexport const crownPositions='+json.dumps(points.round(6).ravel().tolist(),separators=(',',':'))+';\nexport const crownIndices='+json.dumps(np.array(triangles).ravel().tolist(),separators=(',',':'))+';\n')
print({'vertices':len(points),'triangles':len(triangles)})
