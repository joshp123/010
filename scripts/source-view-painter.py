#!/usr/bin/env python3
"""Compose model-drawn source views onto retained geometry and original UVs.
Written by AI on 2026-10-24 by model GPT-6.
"""
import argparse,importlib.util,json,math
from pathlib import Path
import numpy as np
from PIL import Image
spec=importlib.util.spec_from_file_location('bound',Path(__file__).with_name('source-bound-painter.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class SourceCollection:
 """Observe adjoining sources together; export their original geometry separately."""
 def __init__(self,folder):
  self.path=folder;definition_path=folder/'source-collection.json';definition=json.loads(definition_path.read_text()) if definition_path.exists() else {};source_names=definition.get('sourceNames');paths=[folder/name for name in source_names] if source_names else sorted(folder.glob('*.b3dm'));self.sources=[m.Source(p) for p in paths];assert self.sources,'No retained municipal sources'
  included_identities=set(definition['includeBagIds']) if definition.get('includeBagIds') else None
  anchor=next((s for s in self.sources if s.path.name==definition.get('anchorSource')),self.sources[0]);anchor_rotation=np.array(anchor.doc['nodes'][0]['matrix']).reshape(4,4,order='F')[:3,:3];anchor_centre=np.array(anchor.feature['RTC_CENTER'])
  self.images=[];self.triangles=[];self.source_image_ranges=[];coordinate_frame=definition.get('coordinateFrame','legacy-unconverted-rtc');ecef_to_gltf=np.array([[1.,0.,0.],[0.,0.,1.],[0.,-1.,0.]]) if coordinate_frame=='ecef-rtc-in-gltf-y-up' else np.eye(3)
  for source in self.sources:
   image_start=len(self.images);self.images.extend(source.images);self.source_image_ranges.append((image_start,len(self.images)))
   rotation=np.array(source.doc['nodes'][0]['matrix']).reshape(4,4,order='F')[:3,:3];relative_rotation=anchor_rotation.T@rotation;relative_centre=anchor_rotation.T@ecef_to_gltf@(np.array(source.feature['RTC_CENTER'])-anchor_centre)
   for triangle in source.triangles:
    original_identity=str(source.batch['id'][triangle['batch']])
    if not original_identity.startswith('BAG_') or (included_identities is not None and triangle['identity'] not in included_identities):continue
    self.triangles.append({**triangle,'positions':triangle['positions']@relative_rotation.T+relative_centre,'image':triangle['image']+image_start})
  self.positions=np.array([t['positions'] for t in self.triangles]);self.normals=np.cross(self.positions[:,1]-self.positions[:,0],self.positions[:,2]-self.positions[:,0]);self.areas=np.linalg.norm(self.normals,axis=1)/2;self.normals/=np.maximum(self.areas[:,None]*2,1e-12)
  self.raw='\n'.join(m.digest(s.raw) for s in self.sources).encode();self.anchor_rotation=anchor_rotation;self.anchor_centre=anchor_centre
  if coordinate_frame!='legacy-unconverted-rtc':self.raw+=('\n'+coordinate_frame).encode()

 def export_handoff(self,images,identities,folder):
  folder.mkdir(parents=True,exist_ok=True);tiles=[]
  for source,(first,last) in zip(self.sources,self.source_image_ranges):
   selected={str(i).removeprefix('BAG_') for i in source.batch['id'] if str(i).startswith('BAG_')} & identities
   if not selected:continue
   tile_folder=folder/source.path.stem;source.export_handoff(images[first:last],selected,tile_folder);tiles.append({'directory':source.path.stem,'sourceDecodedSha256':m.digest(source.raw),'bagIds':sorted(selected)})
  m.save_json(folder/'collection.json',{'authorship':'Written by AI on 2026-10-25 by model GPT-6','status':'Shared neighbourhood drawing candidate, requires actual source/opposing city review','observationFingerprint':m.digest(self.raw),'tiles':tiles})

def load_source(path):
 return SourceCollection(path) if path.is_dir() else m.Source(path)

def camera(source,angle,elevation,size=1600):
 points=source.positions.reshape(-1,3);centre=(points.min(0)+points.max(0))/2;yaw=np.radians(angle);elev=np.radians(elevation);toward=np.array([np.sin(yaw)*np.cos(elev),np.sin(elev),np.cos(yaw)*np.cos(elev)]);right=np.array([np.cos(yaw),0,-np.sin(yaw)]);up=np.cross(toward,right);basis=np.stack([right,up,toward],axis=1);projected=(points-centre)@basis;scale=(size-48)/max(np.ptp(projected[:,:2],axis=0));mid=(projected[:,:2].max(0)+projected[:,:2].min(0))/2
 return {'centre':centre.tolist(),'basis':basis.tolist(),'scale':float(scale),'mid':mid.tolist(),'size':size,'angle':angle,'elevation':elevation}

def project(points,c):
 q=(points-np.array(c['centre']))@np.array(c['basis']);return q,(q[...,:2]-c['mid'])*[c['scale'],-c['scale']]+c['size']/2

def render(source,c,geometry_only=False):
 size=c['size'];rgb=np.full((size,size,3),[232,234,229],np.uint8);depth=np.full((size,size),-np.inf)
 for triangle_index,t in enumerate(source.triangles):
  q,xy=project(t['positions'],c)
  for x0,y0,x1,y1,w,inside in m.raster_triangle(xy,size,size):
   zz=w@q[:,2];valid=inside&(zz>depth[y0:y1+1,x0:x1+1])
   if geometry_only:
    light=np.array([.4,.8,.5]);light/=np.linalg.norm(light);shade=round(180+55*float(source.normals[triangle_index]@light));rgb[y0:y1+1,x0:x1+1][valid]=[shade]*3
   else:
    im=source.images[t['image']];uv=w@t['uv'];px=np.floor(uv*[im.shape[1],im.shape[0]]).astype(int);px[:,:,0]=px[:,:,0].clip(0,im.shape[1]-1);px[:,:,1]=px[:,:,1].clip(0,im.shape[0]-1);rgb[y0:y1+1,x0:x1+1][valid]=im[px[:,:,1][valid],px[:,:,0][valid]]
   depth[y0:y1+1,x0:x1+1][valid]=zz[valid]
 return rgb,depth

def prepare(source,out):
 out.mkdir(parents=True,exist_ok=True);views=[];previous=json.loads((out/'views.json').read_text()) if (out/'views.json').exists() else {}
 if previous:assert previous['sourceSha256']==m.digest(source.raw)
 accepted_views={v['name']:v for v in previous.get('views',[])}
 for angle,elevation in [(0,0),(90,0),(180,0),(270,0),(0,90),(120,28),(300,28),(0,45),(180,45)]:
  name=f'view-{angle}-{elevation}';c=camera(source,angle,elevation);rgb,depth=render(source,c);Image.fromarray(rgb).save(out/(name+'-source.png'));np.save(out/(name+'-depth.npy'),depth);views.append({'name':name,'camera':c,'source':name+'-source.png','paint':name+'-paint.png','depth':name+'-depth.npy',**accepted_views.get(name,{})})
 m.save_json(out/'views.json',{'authorship':'Written by AI on 2026-10-24 by model GPT-6','status':'Model drawing fields require actual source architecture review before acceptance',**previous,'sourceSha256':m.digest(source.raw),'sourcePath':str(source.path.resolve()),'views':views})

def prepare_focused_block(source,out):
 """Observe explicit neighbouring identities with their surrounding source context."""
 import copy
 definition=json.loads((out/'block-observation.json').read_text());identities=set(definition['bagIds']);focused=copy.copy(source);focused.positions=np.array([t['positions'] for t in source.triangles if t['identity'] in identities]);views=[]
 for angle,elevation in definition['cameraAngles']:
  name=f'view-{angle}-{elevation}';c=camera(focused,angle,elevation,definition.get('size',1600));c['scale']=min(c['scale'],definition['sourcePixelsPerMetre']);rgb,depth=render(source,c);guide,_=render(source,c,geometry_only=True);Image.fromarray(rgb).save(out/(name+'-source.png'));Image.fromarray(guide).save(out/(name+'-geometry.png'));np.save(out/(name+'-depth.npy'),depth)
  _,xy=project(focused.positions.reshape(-1,3),c);lo=np.maximum(0,np.floor(xy.min(0)-20).astype(int));hi=np.minimum(c['size'],np.ceil(xy.max(0)+20).astype(int));bounds=[int(lo[0]),int(lo[1]),int(hi[0]),int(hi[1])]
  Image.fromarray(rgb).crop(bounds).save(out/(name+'-source-context.png'));Image.fromarray(guide).crop(bounds).save(out/(name+'-geometry-context.png'));views.append({'name':name,'camera':c,'source':name+'-source.png','geometryGuide':name+'-geometry.png','depth':name+'-depth.npy','paint':name+'-paint.png','includeBagIds':sorted(identities),'contextCropBounds':bounds})
 m.save_json(out/'views.json',{'authorship':'Written by AI on 2026-10-25 by model GPT-6','sourceSha256':m.digest(source.raw),'sourcePath':str(source.path.resolve()),'status':'Exact adjoining source observations; not interpreted artwork','views':views})

def prepare_overlapping_context(source,out,native_pixels=1254,drawing_pixels_per_metre=6):
 out.mkdir(parents=True,exist_ok=True);views=[];size=1600;context_span=(native_pixels-32)/drawing_pixels_per_metre;scale=size*drawing_pixels_per_metre/native_pixels
 identity_points={}
 for triangle in source.triangles:identity_points.setdefault(triangle['identity'],[]).extend(triangle['positions'])
 for angle,elevation in [(120,28),(300,28),(0,45),(180,45),(0,90)]:
  whole_camera=camera(source,angle,elevation,size);projected,_=project(source.positions.reshape(-1,3),whole_camera);minimum=projected[:,:2].min(0);maximum=projected[:,:2].max(0)
  axes=[]
  for low,high in zip(minimum,maximum):
   count=max(1,math.ceil((high-low)/context_span))
   axes.append(np.linspace(low+context_span/2,high-context_span/2,count) if count>1 else np.array([(low+high)/2]))
  centres=np.array([(x,y) for y in axes[1] for x in axes[0]])
  ownership=[[] for _ in centres]
  for identity,points in identity_points.items():
   q,_=project(np.asarray(points),whole_camera);centre=(q[:,:2].min(0)+q[:,:2].max(0))/2;ownership[int(np.argmin(np.sum((centres-centre)**2,axis=1)))].append(identity)
  for index,(centre,identities) in enumerate(zip(centres,ownership)):
   if not identities:continue
   name=f'context-{angle}-{elevation}-{index}';c={**whole_camera,'scale':scale,'mid':centre.tolist()};rgb,depth=render(source,c);Image.fromarray(rgb).save(out/(name+'-source.png'));np.save(out/(name+'-depth.npy'),depth);guide,_=render(source,c,geometry_only=True);Image.fromarray(guide).save(out/(name+'-geometry.png'))
   views.append({'name':name,'camera':c,'source':name+'-source.png','geometryGuide':name+'-geometry.png','paint':name+'-paint.png','depth':name+'-depth.npy','includeBagIds':sorted(identities),'drawingConfidence':1 if elevation==28 else .45 if elevation==45 else .2})
 m.save_json(out/'views.json',{'authorship':'Written by AI on 2026-10-25 by model GPT-6','status':'Overlapping native-scale source observations; no model drawing or art acceptance yet','sourceSha256':m.digest(source.raw),'sourcePath':str(source.path.resolve()),'nativeGenerationPixels':native_pixels,'drawingPixelsPerMetre':drawing_pixels_per_metre,'contextSpanMetres':context_span,'handoffDirectory':'bound-overlapping-neighbourhood','views':views})

def coherent_surface_views(source,plan,out):
 """Choose one observed drawing for each connected source-supported surface."""
 chosen={};records=[];sample_weights=np.array([[1/3,1/3,1/3],[.6,.2,.2],[.2,.6,.2],[.2,.2,.6]])
 for faces in m.Source.surfaces(source,normal_cosine=math.cos(math.radians(5))):
  normal=np.average(source.normals[faces],axis=0,weights=source.areas[faces]);normal/=np.linalg.norm(normal);identity=source.triangles[faces[0]]['identity'];candidates=[]
  for view_index,view in enumerate(plan['views']):
   if view.get('includeBagIds') and identity not in view['includeBagIds']:continue
   if not (out/view['paint']).exists():continue
   c=view['camera'];basis=np.array(c['basis']);facing=float(normal@basis[:,2])
   if facing<.4:continue
   depth=np.load(out/view['depth'],mmap_mode='r');visible_area=0
   for face in faces:
    q,xy=project(sample_weights@source.positions[face],c);px=np.floor(xy).astype(int);inside=(px[:,0]>=0)&(px[:,0]<c['size'])&(px[:,1]>=0)&(px[:,1]<c['size']);px=px.clip(0,c['size']-1);delta=(px+.5-xy)/c['scale'];n=source.normals[face]@basis;expected=q[:,2]-(n[0]*delta[:,0]-n[1]*delta[:,1])/n[2];visible=inside&(abs(expected-depth[px[:,1],px[:,0]])<.12);visible_area+=source.areas[face]*visible.mean()
   visible_fraction=visible_area/source.areas[faces].sum();score=facing*view.get('drawingConfidence',1)*visible_fraction**2
   if visible_fraction:candidates.append((score,view_index,visible_fraction))
  if not candidates:continue
  score,view_index,visible_fraction=max(candidates)
  for face in faces:chosen[face]=view_index
  records.append({'identity':identity,'triangles':faces,'view':plan['views'][view_index]['name'],'observedAreaFraction':float(visible_fraction),'normal':normal.tolist()})
 return chosen,records

def prepare_plane_correspondences(source,out):
 """Expose exact source planes for model-judged architectural correspondence."""
 from scipy.spatial import ConvexHull
 from PIL import ImageDraw
 plan=json.loads((out/'views.json').read_text());records=json.loads((out/'baked-coherent-planes.json').read_text())['connectedSurfaceObservations'];folder=out/'plane-correspondences';folder.mkdir(exist_ok=True);observations=[]
 for view in plan['views']:
  candidates=[];c=view['camera']
  for record in records:
   if record['view']!=view['name']:continue
   _,xy=project(source.positions[record['triangles']].reshape(-1,3),c)
   if len(np.unique(xy,axis=0))<3:continue
   hull=ConvexHull(xy);polygon=xy[hull.vertices]
   if hull.volume<180 or np.ptp(polygon,axis=0).min()<8:continue
   candidates.append((hull.volume*(3 if record['normal'][1]>.5 else 1)*record['observedAreaFraction']**2,record,polygon))
  candidates.sort(key=lambda row:row[0],reverse=True)
  for index,(area,record,polygon) in enumerate(candidates[:16]):
   key=f"{view['name']}-{index:02d}";minimum=np.floor(polygon.min(0)-14).astype(int).clip(0,c['size']);maximum=np.ceil(polygon.max(0)+14).astype(int).clip(0,c['size']);bounds=[int(v) for v in [*minimum,*maximum]];extent=maximum-minimum;zoom=min(5,500/max(extent));panel_size=np.ceil(extent*zoom).astype(int);sheet=Image.new('RGB',(int(panel_size[0]*2),int(panel_size[1]+42)),(240,240,232));draw=ImageDraw.Draw(sheet)
   for column,key_name in enumerate(['source','paint']):
    image=Image.open(out/view[key_name]).convert('RGB').resize((c['size'],c['size']),Image.Resampling.NEAREST).crop(tuple(bounds)).resize(tuple(panel_size),Image.Resampling.NEAREST);sheet.paste(image,(int(column*panel_size[0]),42));draw.text((int(column*panel_size[0])+5,5),f"{key}: {key_name}",fill='black')
    coordinates=(polygon-minimum)*zoom+[column*panel_size[0],42];draw.line([tuple(p) for p in np.vstack([coordinates,coordinates[0]])],fill='#e92b73',width=1)
    for vertex,p in enumerate(coordinates):draw.ellipse((p[0]-3,p[1]-3,p[0]+3,p[1]+3),fill='#ff0060');draw.text(tuple(p+[5,2]),str(vertex),fill='#ff0060')
   sheet.save(folder/(key+'.png'));observations.append({'planeId':key,**record,'sourcePolygon':polygon.tolist(),'cropBounds':bounds,'displayZoom':zoom,'displayPanelSize':panel_size.tolist(),'drawnPolygon':None,'judgement':'unreviewed; pink marks show source geometry, not accepted drawing correspondence'})
 m.save_json(folder/'observations.json',{'authorship':'Written by AI on 2026-10-25 by model GPT-6','sourceSha256':plan['sourceSha256'],'coordinateFrame':'source and drawn coordinates both use original 1600px source camera; drawn native image scaled nearest to this frame','planes':observations})

def observed_plane_transforms(plan,out):
 """Bind explicitly observed architectural corners with one straight-plane map."""
 observations=json.loads((out/'plane-correspondences/accepted.json').read_text());assert observations['sourceSha256']==plan['sourceSha256'];transforms={}
 for observation in observations['planes']:
  original=np.array(observation['sourceAnchors'],dtype=float);drawn=np.array(observation['drawnAnchors'],dtype=float);assert original.shape==drawn.shape and len(original)>=4
  equations=[];targets=[]
  for (x,y),(u,v) in zip(original,drawn):
   equations.extend([[x,y,1,0,0,0,-u*x,-u*y],[0,0,0,x,y,1,-v*x,-v*y]]);targets.extend([u,v])
  homography=np.r_[np.linalg.lstsq(equations,targets,rcond=None)[0],1].reshape(3,3)
  for face in observation['triangles']:transforms[face]=(observation['view'],homography)
 return transforms,observations

def prepare_facade_support(source,observation_path,out):
 """Expose visible connected source faces; opening inventory rectangles are seeds only."""
 from PIL import ImageDraw
 observations=json.loads(observation_path.read_text());plan=json.loads(Path(observations['views']).read_text());view=next(v for v in plan['views'] if v['name']==observations['view']);c=view['camera'];size=c['size'];out.mkdir(parents=True,exist_ok=True)
 depth=np.full((size,size),-np.inf);face_image=np.full((size,size),-1,np.int32)
 for face,triangle in enumerate(source.triangles):
  q,xy=project(triangle['positions'],c)
  for x0,y0,x1,y1,weights,inside in m.raster_triangle(xy,size,size):
   z=weights@q[:,2];visible=inside&(z>depth[y0:y1+1,x0:x1+1]);depth[y0:y1+1,x0:x1+1][visible]=z[visible];face_image[y0:y1+1,x0:x1+1][visible]=face
 groups=m.Source.surfaces(source,normal_cosine=math.cos(math.radians(5)));face_group=np.full(len(source.triangles),-1,np.int32)
 for index,faces in enumerate(groups):face_group[faces]=index
 group_image=np.full_like(face_image,-1);visible=face_image>=0;group_image[visible]=face_group[face_image[visible]]
 raw=Image.open(observations['sourceImage']).convert('RGB');overlay=raw.copy();draw=ImageDraw.Draw(overlay);records=[]
 for facade in observations['facades']:
  seed=Image.new('1',(size,size));ImageDraw.Draw(seed).polygon([tuple(p) for p in facade['replacementPolygon']],fill=1);indices,counts=np.unique(group_image[np.asarray(seed,dtype=bool)],return_counts=True);candidates=[]
  for group_index,count in sorted(zip(indices,counts),key=lambda row:-row[1]):
   if group_index<0:continue
   faces=groups[group_index];normal=np.average(source.normals[faces],axis=0,weights=source.areas[faces]);normal/=np.linalg.norm(normal)
   if abs(normal[1])>.25 or normal@np.asarray(c['basis'])[:,2]<.4:continue
   mask=group_image==group_index;ys,xs=np.nonzero(mask);bounds=[int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)];key=f'{facade["id"]}-surface-{group_index}';Image.fromarray(mask.astype(np.uint8)*255).save(out/(key+'-visible-mask.png'))
   projected=[project(source.positions[face],c)[1].tolist() for face in faces]
   candidates.append({'surfaceId':key,'bagId':source.triangles[faces[0]]['identity'],'triangles':faces,'normal':normal.tolist(),'seedVisiblePixels':int(count),'visibleBounds':bounds,'projectedTriangles':projected,'visibleMask':key+'-visible-mask.png'})
  records.append({'openingObservation':facade['id'],'candidateSurfaces':candidates,'judgement':'Unreviewed source support; no wall fill or architectural boundary inferred from seed rectangle.'})
  if candidates:
   best=candidates[0];draw.rectangle(best['visibleBounds'],outline='#ed2568');draw.text((best['visibleBounds'][0],best['visibleBounds'][1]-10),facade['id']+':'+best['bagId'][-7:],fill='#ed2568')
 overlay.save(out/'source-facade-support.png');m.save_json(out/'source-facade-support.json',{'authorship':'Written by AI on 2026-10-25 by model GPT-6','sourceSha256':m.digest(source.raw),'openingObservations':str(observation_path.resolve()),'camera':c,'meaning':'Exact connected source geometry and depth-visible masks. Candidate ranking uses seed overlap, not model judgement; projected triangles include occluded portions and masks do not authorize erasing unobserved openings.','facades':records})

def compose_facade_drawing(observation_path):
 """Paint explicit architectural observations within retained visible wall support."""
 from PIL import ImageDraw
 observations=json.loads(observation_path.read_text());folder=observation_path.parent;support=json.loads((folder/observations['sourceSupport']).read_text());size=support['camera']['size'];rgba=np.zeros((size,size,4),np.uint8)
 for region in observations['regions']:
  mask=np.asarray(Image.open(folder/region['visibleMask']))>0;top,bottom=region['sourceVerticalExtent'];mask[:top]=False;mask[bottom:]=False;rgba[mask]=[*region['wallRgb'],255]
 image=Image.fromarray(rgba);drawing=ImageDraw.Draw(image)
 for feature in observations['features']:
  layer=Image.new('1',(size,size));ImageDraw.Draw(layer).polygon([tuple(point) for point in feature['polygon']],fill=1);mask=np.asarray(layer)&(rgba[:,:,3]>0);rgba[mask]=[*observations['palette'][feature['material']],255]
 for exclusion in observations.get('exclusions',[]):
  layer=Image.new('1',(size,size));ImageDraw.Draw(layer).polygon([tuple(point) for point in exclusion['polygon']],fill=1);rgba[np.asarray(layer),3]=0
 Image.fromarray(rgba).save(folder/'facade-substrate.png')

def apply_architectural_patches(source,images,plan,out,observations):
 """Register explicitly corresponding straight architectural parts, not image edges."""
 from PIL import ImageDraw
 for observation in observations:
  view=next(v for v in plan['views'] if v['name']==observation['view']);c=view['camera'];size=c['size'];original=np.asarray(observation['sourceAnchors']);drawn=np.asarray(observation['drawnAnchors']);equations=[];targets=[]
  for (x,y),(u,v) in zip(original,drawn):equations.extend([[x,y,1,0,0,0,-u*x,-u*y],[0,0,0,x,y,1,-v*x,-v*y]]);targets.extend([u,v])
  transform=np.r_[np.linalg.lstsq(equations,targets,rcond=None)[0],1].reshape(3,3);region=Image.new('1',(size,size));ImageDraw.Draw(region).polygon([tuple(p) for p in observation['sourceRegion']],fill=1);region=np.asarray(region);paint=np.asarray(Image.open(out/view['paint']).convert('RGB').resize((size,size),Image.Resampling.NEAREST));depth=np.load(out/view['depth'])
  for index in observation['triangles']:
   triangle=source.triangles[index];image=images[triangle['image']];height,width=image.shape[:2]
   for x0,y0,x1,y1,weights,inside in m.raster_triangle(triangle['uv']*[width,height],width,height):
    q,xy=project(weights@triangle['positions'],c);pixels=np.floor(xy).astype(int);valid=inside&(pixels[:,:,0]>=0)&(pixels[:,:,0]<size)&(pixels[:,:,1]>=0)&(pixels[:,:,1]<size);pixels=pixels.clip(0,size-1);normal=source.normals[index]@np.asarray(c['basis']);delta=(pixels+.5-xy)/c['scale'];expected=q[:,:,2]-(normal[0]*delta[:,:,0]-normal[1]*delta[:,:,1])/normal[2];valid&=(abs(expected-depth[pixels[:,:,1],pixels[:,:,0]])<.12)&region[pixels[:,:,1],pixels[:,:,0]]
    mapped=np.dstack([xy,np.ones(xy.shape[:2])])@transform.T;drawn_pixels=np.floor(mapped[:,:,:2]/mapped[:,:,2,None]).astype(int);valid&=(drawn_pixels[:,:,0]>=0)&(drawn_pixels[:,:,0]<size)&(drawn_pixels[:,:,1]>=0)&(drawn_pixels[:,:,1]<size);drawn_pixels=drawn_pixels.clip(0,size-1);image[y0:y1+1,x0:x1+1][valid]=paint[drawn_pixels[:,:,1][valid],drawn_pixels[:,:,0][valid]]

def align_frontage_field(folder):
 """Map independently observed straight facade parts into their source camera."""
 registration=json.loads((folder/'registration.json').read_text());plan=json.loads((folder/registration['sourceCameraViews']).resolve().read_text());camera=next(v['camera'] for v in plan['views'] if v['name']==registration['sourceCamera']);size=camera['size'];drawing=np.asarray(Image.open(folder/registration.get('drawingImage','paint.png')).convert('RGB'));result=np.zeros((size,size,4),np.uint8);parts=json.loads((folder/'architectural-correspondences.json').read_text())['parts']
 for part in parts:
  x0,x1=part['sourceX'];ys=part['sourceFloorDatums'];vs=part['drawnFloorDatums'];y0,y1=min(ys),max(ys);xx,yy=np.meshgrid(np.arange(x0,x1),np.arange(y0,y1));u=np.interp(xx+.5,part['sourceX'],part['drawnX']);v=np.interp(yy+.5,ys,vs);u=np.floor(u).astype(int).clip(0,drawing.shape[1]-1);v=np.floor(v).astype(int).clip(0,drawing.shape[0]-1);result[y0:y1,x0:x1,:3]=drawing[v,u];result[y0:y1,x0:x1,3]=255
 Image.fromarray(result).save(folder/'aligned-substrate.png')

def apply_source_registered_field(source,images,c,drawing,identities,triangle_indices=None,painted_masks=None):
 """Bind a source-camera RGBA drawing using original geometry, UVs and occlusion."""
 _,depth=render(source,c);size=c['size'];toward=np.asarray(c['basis'])[:,2]
 for index,triangle in enumerate(source.triangles):
  if triangle_indices is not None and index not in triangle_indices:continue
  if triangle['identity'] not in identities or source.normals[index]@toward<.1:continue
  image=images[triangle['image']];height,width=image.shape[:2]
  for x0,y0,x1,y1,weights,inside in m.raster_triangle(triangle['uv']*[width,height],width,height):
   q,xy=project(weights@triangle['positions'],c);pixels=np.floor(xy).astype(int);valid=inside&(pixels[:,:,0]>=0)&(pixels[:,:,0]<size)&(pixels[:,:,1]>=0)&(pixels[:,:,1]<size);pixels=pixels.clip(0,size-1);normal=source.normals[index]@np.asarray(c['basis']);delta=(pixels+.5-xy)/c['scale'];expected=q[:,:,2]-(normal[0]*delta[:,:,0]-normal[1]*delta[:,:,1])/normal[2];valid&=(abs(expected-depth[pixels[:,:,1],pixels[:,:,0]])<.12)&(drawing[pixels[:,:,1],pixels[:,:,0],3]>0);image[y0:y1+1,x0:x1+1][valid]=drawing[pixels[:,:,1][valid],pixels[:,:,0][valid],:3]
   if painted_masks is not None:painted_masks[triangle['image']][y0:y1+1,x0:x1+1]|=valid

def bake_frontage_field(source,folder):
 """Rebuild one registered drawing from retained source, teacher and judgement."""
 registration=json.loads((folder/'registration.json').read_text());align_frontage_field(folder);plan=json.loads((folder/registration['sourceCameraViews']).resolve().read_text());c=next(v['camera'] for v in plan['views'] if v['name']==registration['sourceCamera']);packed=np.load(folder/registration['baseAtlases']);source.images=[packed[f'image_{i}'].copy() for i in range(len(source.images))];apply_source_registered_field(source,source.images,c,np.asarray(Image.open(folder/'aligned-substrate.png')),set(registration['bagIds']));rgb,_=render(source,c);Image.fromarray(rgb).save(folder/'actual-no-plants-substrate-bake.png');source.export_handoff(source.images,{t['identity'] for t in source.triangles},folder/registration['handoffDirectory'])

def bake_block_fields(source,folder):
 """Continue an existing drawing with explicitly source-registered block fields."""
 definition=json.loads((folder/'block-drawing.json').read_text());plan=json.loads((folder/'views.json').read_text());base=(folder/definition['baseHandoff']).resolve()
 for leaf,(first,last) in zip(source.sources,source.source_image_ranges):
  leaf_base=(folder/definition.get('baseOverrides',{}).get(leaf.path.stem,str(base))).resolve()
  for local,image_index in enumerate(range(first,last)):source.images[image_index]=np.asarray(Image.open(leaf_base/leaf.path.stem/f'painted-atlas-{local}.png').convert('RGB')).copy()
 painted_masks=[np.zeros(a.shape[:2],bool) for a in source.images]
 for field in definition['fields']:
  view=next(v for v in plan['views'] if v['name']==field['view']);c=view['camera'];bounds=view['contextCropBounds'];drawing=Image.open(folder/field['drawing']).convert('RGBA').resize((bounds[2]-bounds[0],bounds[3]-bounds[1]),Image.Resampling.NEAREST);registered=Image.new('RGBA',(c['size'],c['size']));registered.paste(drawing,bounds[:2]);apply_source_registered_field(source,source.images,c,np.asarray(registered),set(field['bagIds']),set(field['triangleIndices']) if 'triangleIndices' in field else None,painted_masks)
 pad_painted_uv_charts(source,source.images,painted_masks)
 for view in plan['views']:
  rgb,_=render(source,view['camera']);Image.fromarray(rgb).save(folder/(view['name']+'-actual-bake.png'))
 source.export_handoff(source.images,{t['identity'] for t in source.triangles},folder/definition['handoffDirectory'])

def pad_painted_uv_charts(source,images,painted_masks):
 """Supply sampling gutters outside UV charts, never inside unseen surfaces."""
 for image_index,image in enumerate(images):
  if not painted_masks[image_index].any():continue
  height,width=image.shape[:2];covered=np.zeros((height,width),dtype=bool)
  for triangle in source.triangles:
   if triangle['image']!=image_index:continue
   for x0,y0,x1,y1,weights,inside in m.raster_triangle(triangle['uv']*[width,height],width,height):covered[y0:y1+1,x0:x1+1]|=inside
  distance,nearest=m.ndimage.distance_transform_edt(~painted_masks[image_index],return_indices=True);gutter=(~covered)&(distance<=2)
  image[gutter]=image[nearest[0][gutter],nearest[1][gutter]]

def bake(source,out,coherent_planes=False,observed_planes=False,uv_gutters=False):
 plan=json.loads((out/'views.json').read_text());assert plan['sourceSha256']==m.digest(source.raw);images=[a.copy() for a in source.images];scores=[np.full(a.shape[:2],-np.inf) for a in images]
 chosen,records=coherent_surface_views(source,plan,out) if coherent_planes else ({},[])
 observed,observations=observed_plane_transforms(plan,out) if observed_planes else ({},None)
 for face,(view_name,homography) in observed.items():chosen[face]=next(i for i,v in enumerate(plan['views']) if v['name']==view_name)
 for view_index,view in enumerate(plan['views']):
  path=out/view['paint']
  if not path.exists():continue
  included_identities=set(view['includeBagIds']) if view.get('includeBagIds') else None
  c=view['camera'];size=c['size'];drawing=Image.open(path).convert('RGB');pixel_size=plan.get('drawingPixelSize')
  if plan.get('drawingPixelsPerMetre'):pixel_size=round(size*plan['drawingPixelsPerMetre']/c['scale'])
  if pixel_size:drawing=drawing.resize((pixel_size,pixel_size),Image.Resampling.BOX)
  paint=np.asarray(drawing.resize((size,size),Image.Resampling.NEAREST));depth=np.load(out/view['depth']);toward=np.array(c['basis'])[:,2]
  for index,t in enumerate(source.triangles):
   if coherent_planes and chosen.get(index)!=view_index:continue
   if included_identities is not None and t['identity'] not in included_identities:continue
   facing=float(source.normals[index]@toward)
   if facing<(0 if coherent_planes else .4):continue
   score=facing*view.get('drawingConfidence',1)
   tex=images[t['image']];h,w=tex.shape[:2]
   for x0,y0,x1,y1,weights,inside in m.raster_triangle(t['uv']*[w,h],w,h):
    q,xy=project(weights@t['positions'],c);px=np.floor(xy).astype(int);valid=inside&(px[:,:,0]>=0)&(px[:,:,0]<size)&(px[:,:,1]>=0)&(px[:,:,1]<size);px[:,:,0]=px[:,:,0].clip(0,size-1);px[:,:,1]=px[:,:,1].clip(0,size-1)
    view_normal=source.normals[index]@np.array(c['basis']);sample_delta=(px+.5-xy)/c['scale'];sample_plane_depth=q[:,:,2]-(view_normal[0]*sample_delta[:,:,0]-view_normal[1]*sample_delta[:,:,1])/view_normal[2]
    valid&=abs(sample_plane_depth-depth[px[:,:,1],px[:,:,0]])<.12;valid&=score>scores[t['image']][y0:y1+1,x0:x1+1]
    if index in observed:
     _,homography=observed[index];mapped=np.dstack([xy,np.ones(xy.shape[:2])])@homography.T;drawn_px=np.floor(mapped[:,:,:2]/mapped[:,:,2,None]).astype(int);valid&=(drawn_px[:,:,0]>=0)&(drawn_px[:,:,0]<size)&(drawn_px[:,:,1]>=0)&(drawn_px[:,:,1]<size);px=drawn_px.clip(0,size-1)
    tex[y0:y1+1,x0:x1+1][valid]=paint[px[:,:,1][valid],px[:,:,0][valid]];scores[t['image']][y0:y1+1,x0:x1+1][valid]=score
 if uv_gutters:pad_painted_uv_charts(source,images,[np.isfinite(score) for score in scores])
 if not isinstance(source,SourceCollection):source.export(images,out/'model-drawn-block.glb')
 suffix='-uv-gutters' if uv_gutters else '-observed-planes' if observed_planes else '-coherent-planes' if coherent_planes else '';source.export_handoff(images,{t['identity'] for t in source.triangles},out/(plan.get('handoffDirectory','bound-model-drawn-block')+suffix));np.savez_compressed(out/f'painted-atlases{suffix}.npz',**{f'image_{i}':a for i,a in enumerate(images)})
 m.save_json(out/f'baked{suffix}.json',{'sourceSha256':m.digest(source.raw),'paintedViews':[v['paint'] for v in plan['views'] if (out/v['paint']).exists()],'identities':sorted({t['identity'] for t in source.triangles}),'status':'Whole model drawing field candidate; source aperture and opposing view inspection required, no fidelity acceptance inferred from geometry',**({'connectedSurfaceObservations':records} if coherent_planes else {}),**({'architecturalCorrespondences':observations} if observed_planes else {})})

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('operation',choices=['prepare','prepare-block','prepare-overlaps','prepare-correspondences','bake','bake-coherent','bake-observed','bake-gutters','bake-frontage','bake-block']);p.add_argument('source',type=Path);p.add_argument('output',type=Path);a=p.parse_args();s=load_source(a.source)
 if a.operation=='prepare':prepare(s,a.output)
 elif a.operation=='prepare-block':prepare_focused_block(s,a.output)
 elif a.operation=='prepare-overlaps':prepare_overlapping_context(s,a.output)
 elif a.operation=='prepare-correspondences':prepare_plane_correspondences(s,a.output)
 elif a.operation=='bake-frontage':bake_frontage_field(s,a.output)
 elif a.operation=='bake-block':bake_block_fields(s,a.output)
 else:bake(s,a.output,coherent_planes=a.operation in ['bake-coherent','bake-observed','bake-gutters'],observed_planes=a.operation=='bake-observed',uv_gutters=a.operation=='bake-gutters')
