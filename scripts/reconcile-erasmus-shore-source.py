#!/usr/bin/env python3
"""Remove only the shore BAG's duplicate road contribution above the native bridge.
Written by AI on 2026-10-25 by model GPT-6 Astra.
Both raw sources remain unchanged. Surviving source faces/UVs are interpolated exactly.
"""
import copy,importlib.util,json
from pathlib import Path
import numpy as np
from pyproj import Transformer
from shapely import constrained_delaunay_triangles
from shapely.geometry import Polygon
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
bridge=load('bridge',ROOT/'scripts/build-bridge-surfaces.py');painter=load('painter',Path('/Users/josh/code/010-rescue-art/scripts/source-bound-painter.py'))
review=next(r for r in bridge.reviews['reviews'] if r['name']=='erasmus');deck=bridge.load_native_triangles(review['sha256'])[review['deckTriangles']];deck_polygons=[Polygon(t[:,:2]) for t in deck]
source=painter.Source(ROOT/'source-data/erasmus-structure-drawing/18_268672_55471.b3dm');rotation=np.array(source.doc['nodes'][0]['matrix']).reshape(4,4,order='F')[:3,:3];rtc=np.array(source.feature['RTC_CENTER']);gltf_to_earth=np.array([[1.,0.,0.],[0.,0.,-1.],[0.,1.,0.]])
to_rd=Transformer.from_crs(4978,28992,always_xy=True);to_geo=Transformer.from_crs(4978,4979,always_xy=True)
def rd_points(local):
 earth=(local@rotation.T)@gltf_to_earth.T+rtc;x,y,_=to_rd.transform(*earth.T);_,_,height=to_geo.transform(*earth.T);return np.c_[x,y,height]
def plane_height(t,xy):
 return t[0,2]+(xy-t[0,:2])@np.linalg.inv(np.column_stack((t[1,:2]-t[0,:2],t[2,:2]-t[0,:2]))).T@(t[1:,2]-t[0,2])
def clip_height(polygon,source_triangle,deck_triangle,threshold,greater):
 vertices=list(polygon.exterior.coords)[:-1];result=[]
 if not vertices:return polygon
 def value(point):return float(plane_height(source_triangle,np.array(point))-plane_height(deck_triangle,np.array(point))-threshold)*(1 if greater else -1)
 previous=np.array(vertices[-1]);previous_value=value(previous)
 for vertex in vertices:
  current=np.array(vertex);current_value=value(current)
  if (current_value>=0)!=(previous_value>=0):result.append((previous+previous_value/(previous_value-current_value)*(current-previous)).tolist())
  if current_value>=0:result.append(current.tolist())
  previous=current;previous_value=current_value
 return Polygon(result) if len(result)>=3 else Polygon()
records=[];removed_area=0;changed=0;changed_source_indices=set()
for original_index,record in enumerate(source.triangles):
 record={**record,'originalIndex':original_index}
 if record['identity']!='0599100000750049':continue
 local=record['positions'];t=rd_points(local);normal=np.cross(t[1]-t[0],t[2]-t[0]);normal/=max(np.linalg.norm(normal),1e-12);remaining=Polygon(t[:,:2]);original_area=remaining.area
 if abs(normal[2])>.7 and remaining.is_valid:
  for native,footprint in zip(deck,deck_polygons):
   if not remaining.intersects(footprint):continue
   intersection=Polygon(t[:,:2]).intersection(footprint)
   parts=list(intersection.geoms) if hasattr(intersection,'geoms') else [intersection]
   for part in parts:
    if part.geom_type!='Polygon' or part.area<1e-8:continue
    part=clip_height(part,t,native,.25,True)
    if part.is_empty:continue
    part=clip_height(part,t,native,2.5,False)
    if not part.is_empty:remaining=remaining.difference(part)
  removed=original_area-remaining.area
  if removed>1e-6:changed+=1;removed_area+=removed;changed_source_indices.add(original_index)
  if removed>1e-6:
   inverse=np.linalg.inv(np.vstack([t[:,:2].T,np.ones(3)]))
   for piece in constrained_delaunay_triangles(remaining).geoms:
    if not remaining.covers(piece) or piece.area<1e-9:continue
    xy=np.array(piece.exterior.coords)[:3];weights=np.c_[xy,np.ones(3)]@inverse.T
    points=weights@local
    if np.cross(points[1]-points[0],points[2]-points[0])@np.cross(local[1]-local[0],local[2]-local[0])<0:weights=weights[[0,2,1]]
    records.append({**record,'positions':weights@local,'uv':weights@record['uv']})
   continue
 records.append(record)
# Road-edge skins belong to the same duplicate roadway, but their lower walls
# remain part of the folded shore. Clip only the connected upper overlap volume.
edges={}
for index,record in enumerate(source.triangles):
 if record['identity']!='0599100000750049':continue
 keys=[tuple(v) for v in np.round(record['positions'],3)]
 for a,b in [(0,1),(1,2),(2,0)]:edges.setdefault(tuple(sorted((keys[a],keys[b]))),set()).add(index)
road_neighbours=set()
for members in edges.values():
 if members & changed_source_indices:road_neighbours.update(members)
def cross_xy(a,b):return a[0]*b[1]-a[1]*b[0]
def partition(polygon,value):
 inside=[];outside=[]
 previous=polygon[-1];previous_value=value(previous)
 for current in polygon:
  current_value=value(current)
  if (previous_value>=0)!=(current_value>=0):
   intersection=previous+(current-previous)*previous_value/(previous_value-current_value);inside.append(intersection);outside.append(intersection)
  (inside if current_value>=0 else outside).append(current)
  previous=current;previous_value=current_value
 return inside,outside
refined=[];wall_fragments=0
for record in records:
 t=rd_points(record['positions']);normal=np.cross(t[1]-t[0],t[2]-t[0]);normal/=max(np.linalg.norm(normal),1e-12)
 if record['originalIndex'] not in road_neighbours or abs(normal[2])>.7:refined.append(record);continue
 polygons=[list(np.eye(3))]
 for native in deck:
  orientation=np.sign(cross_xy(native[1,:2]-native[0,:2],native[2,:2]-native[0,:2]))
  constraints=[]
  for a,b in [(0,1),(1,2),(2,0)]:
   start=native[a,:2];direction=native[b,:2]-start
   constraints.append(lambda w,start=start,direction=direction,orientation=orientation:orientation*float(cross_xy(direction,(w@t)[:2]-start)))
  constraints.extend([lambda w,native=native:float((w@t)[2]-plane_height(native,(w@t)[:2])-.25),lambda w,native=native:float(2.5-((w@t)[2]-plane_height(native,(w@t)[:2])))])
  remaining=[]
  for polygon in polygons:
   inside=polygon
   for constraint in constraints:
    if len(inside)<3:break
    inside,outside=partition(inside,constraint)
    if len(outside)>=3:remaining.append(outside)
   if len(inside)>=3:wall_fragments+=1
  polygons=remaining
 for polygon in polygons:
  for i in range(1,len(polygon)-1):
   weights=np.array([polygon[0],polygon[i],polygon[i+1]]);points=weights@record['positions']
   if np.linalg.norm(np.cross(points[1]-points[0],points[2]-points[0]))<1e-8:continue
   refined.append({**record,'positions':points,'uv':weights@record['uv']})
records=refined
# Replace only selected source primitives; original images, node transform and RTC stay.
binary=bytearray(source.binary);doc=copy.deepcopy(source.doc)
def append_accessor(values,kind,component=5126):
 values=np.asarray(values,dtype='<f4' if component==5126 else '<u4');binary.extend(b'\0'*(-len(binary)%4));offset=len(binary);binary.extend(values.tobytes());doc['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':values.nbytes});a={'bufferView':len(doc['bufferViews'])-1,'componentType':component,'count':len(values),'type':kind};a.update(min=values.min(0).tolist(),max=values.max(0).tolist());doc['accessors'].append(a);return len(doc['accessors'])-1
for mesh_index,mesh in enumerate(doc['meshes']):
 primitives=[]
 for primitive_index,primitive in enumerate(mesh['primitives']):
  selected=[r for r in records if r['mesh']==mesh_index and r['primitive']==primitive_index]
  if not selected:continue
  positions=np.concatenate([r['positions'] for r in selected]);uv=np.concatenate([r['uv'] for r in selected]);batch=np.full((len(positions),1),selected[0]['batch'],dtype=np.uint32)
  attributes={'POSITION':append_accessor(positions,'VEC3'),'TEXCOORD_0':append_accessor(uv,'VEC2'),'_BATCHID':append_accessor(batch,'SCALAR',5125)}
  updated=copy.deepcopy(primitive);updated['attributes']=attributes;updated['indices']=append_accessor(np.arange(len(positions),dtype=np.uint32).reshape(-1,1),'SCALAR',5125);primitives.append(updated)
 mesh['primitives']=primitives
source.doc=doc;source.binary=bytes(binary);out=ROOT/'source-data/erasmus-structure-drawing/reconciled-shore';source.export_handoff(source.images,{'0599100000750049'},out)
(out/'duplicate-roadway-reconciliation.json').write_text(json.dumps({'authorship':'Written by AI on 2026-10-25 by model GPT-6 Astra','sourceBag':'0599100000750049','nativeBridgeSource':review,'rule':'Only source BAG road-top fragments and edge-connected upper road skins inside the original native deck footprint and 0.25 to 2.5 m above its original height; lower folded walls retained, exact source-plane/UV interpolation','changedSourceTriangles':changed,'removedDuplicateRoadAreaSquareMetres':removed_area,'retainedTriangles':len(records),'connectedRoadSkinOverlapFragments':wall_fragments},indent=2)+'\n')
print(json.dumps({'changedFaces':changed,'removedDuplicateArea':removed_area,'retainedTriangles':len(records)}))
