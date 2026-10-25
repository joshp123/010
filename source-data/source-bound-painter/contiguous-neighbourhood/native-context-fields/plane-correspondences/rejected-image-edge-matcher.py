"""Rejected offline diagnostic. Written by AI on 2026-10-25 by model GPT-6.
Window/cornice gradients do not identify matching architectural planes.
This function worsened the rendered drawing and is excluded from production.
Retained only to explain the rejected registered-planes assets.
"""
def register_drawn_surface_edges(source,plan,out,records):
 """Rejected diagnostic: image edges do not identify architectural planes."""
 from scipy.spatial import ConvexHull
 transforms={};drawings={};depths={}
 for record in records:
  view=next(v for v in plan['views'] if v['name']==record['view']);name=view['name'];c=view['camera'];faces=record['triangles']
  if name not in drawings:
   drawing=np.asarray(Image.open(out/view['paint']).convert('RGB').resize((c['size'],c['size']),Image.Resampling.NEAREST),dtype=float);drawings[name]=m.ndimage.gaussian_filter(drawing.mean(2),.7);depths[name]=np.load(out/view['depth'],mmap_mode='r')
  luminance=drawings[name];depth=depths[name];points=source.positions[faces].reshape(-1,3);q,xy=project(points,c)
  if np.ptp(xy,axis=0).min()<8:continue
  polygon=xy[ConvexHull(xy).vertices];centre=polygon.mean(0);normal=np.array(record['normal'])@np.array(c['basis']);plane_point=(points.mean(0)-np.array(c['centre']))@np.array(c['basis']);equations=[];targets=[];edges=[]
  for first,second in zip(polygon,np.roll(polygon,-1,axis=0)):
   length=np.linalg.norm(second-first)
   if length<8:continue
   tangent=(second-first)/length;edge_normal=np.array([-tangent[1],tangent[0]]);mid=(first+second)/2;samples=first+(second-first)*np.linspace(.18,.82,min(64,max(8,round(length))))[:,None]
   interior=samples+(centre-mid)/max(np.linalg.norm(centre-mid),1)*1.5;px=np.floor(interior).astype(int);inside=(px[:,0]>=0)&(px[:,0]<c['size'])&(px[:,1]>=0)&(px[:,1]<c['size']);px=px.clip(0,c['size']-1);plane_xy=(interior-c['size']/2)/[c['scale'],-c['scale']]+c['mid'];expected=plane_point[2]-((plane_xy-plane_point[:2])@normal[:2])/normal[2];visible=inside&(abs(expected-depth[px[:,1],px[:,0]])<.12)
   if visible.mean()<.55:continue
   samples=samples[visible];best=None
   for angle in [-1.5,0,1.5]:
    radians=np.radians(angle);rotation=np.array([[np.cos(radians),-np.sin(radians)],[np.sin(radians),np.cos(radians)]]);target_normal=rotation@edge_normal;rotated=(samples-mid)@rotation.T+mid
    for offset in range(-8,9):
     candidate=rotated+target_normal*offset
     def sample_luminance(delta):
      p=candidate+target_normal*delta;return m.ndimage.map_coordinates(luminance,[p[:,1],p[:,0]],order=1,mode='nearest')
     middle=sample_luminance(0);ridge=(sample_luminance(-2)+sample_luminance(2))/2-middle;score=np.mean(np.maximum(ridge,0))-.12*abs(offset)-.15*abs(angle)
     if best is None or score>best[0]:best=(score,target_normal.copy(),offset,angle)
   score,target_normal,offset,angle=best
   for p in samples[::max(1,len(samples)//8)]:
    x,y=p-centre;nx,ny=target_normal;equations.append([nx*x,nx*y,nx,ny*x,ny*y,ny]);targets.append(float(target_normal@(mid+target_normal*offset-p)))
   edges.append({'sourceLine':[first.tolist(),second.tolist()],'normal':target_normal.tolist(),'offsetPixels':offset,'angleDegrees':angle})
  if len(edges)<3:continue
  matrix=np.array(equations);target=np.array(targets);regularization=np.diag([12,12,.2,12,12,.2]);parameters=np.linalg.lstsq(np.vstack([matrix,regularization]),np.r_[target,np.zeros(6)],rcond=None)[0];affine=np.array([[1+parameters[0],parameters[1]],[parameters[3],1+parameters[4]]]);translation=np.array([parameters[2],parameters[5]])+centre-affine@centre;movement=polygon@affine.T+translation-polygon
  if np.linalg.norm(movement,axis=1).max()>12:continue
  record['drawnPlaneRegistration']={'affine':affine.tolist(),'translation':translation.tolist(),'matchedStraightEdges':edges}
  for face in faces:transforms[face]=(affine,translation)
 return transforms

