#!/usr/bin/env python3
"""Written by AI, GPT-6 Astra, 2026-10-25.
Exact BGT bridge surfaces and track axes on the reviewed native deck triangles.
"""
import collections, hashlib, importlib.util, json, struct
from pathlib import Path
import numpy as np
from pyproj import Transformer
from shapely import constrained_delaunay_triangles, make_valid
from shapely.geometry import Polygon, LineString, shape
from shapely.ops import transform, unary_union

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('bridge_surfaces',ROOT/'scripts/build-bridge-surfaces.py')
bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
source=ROOT/'source-data/erasmus-public-space'
output=ROOT/'public/data/bridge-surfaces'
review=next(r for r in bridge.reviews['reviews'] if r['name']=='erasmus')
triangles=bridge.load_native_triangles(review['sha256'])[review['deckTriangles']]
polygons=[Polygon(t[:,:2]) for t in triangles]
footprint=unary_union(polygons)
to_rd=Transformer.from_crs(4326,28992,always_xy=True).transform
to_geo=Transformer.from_crs(28992,4326,always_xy=True).transform
to_ecef=Transformer.from_crs(4979,4978,always_xy=True).transform
lat,lon=np.deg2rad([51.915,4.49]);east=np.array([-np.sin(lon),np.cos(lon),0]);up=np.array([np.cos(lat)*np.cos(lon),np.cos(lat)*np.sin(lon),np.sin(lat)]);south=np.array([np.sin(lat)*np.cos(lon),np.sin(lat)*np.sin(lon),-np.cos(lat)]);origin=np.array(to_ecef(4.49,51.915,0))
vertices=collections.defaultdict(list);records=[];cycle_surfaces=[];carriageways=[]

def emit(geometry,kind,identifier):
    geometry=make_valid(geometry).intersection(footprint)
    area=0
    for triangle,polygon in zip(triangles,polygons):
        if not geometry.intersects(polygon):continue
        overlap=geometry.intersection(polygon)
        if overlap.area<1e-6:continue
        inverse=np.linalg.inv(np.column_stack((triangle[1,:2]-triangle[0,:2],triangle[2,:2]-triangle[0,:2])))
        for piece in constrained_delaunay_triangles(overlap).geoms:
            if not overlap.covers(piece):continue
            points=list(piece.exterior.coords)[:3]
            if not piece.exterior.is_ccw:points.reverse()
            for x,y in points:
                weights=inverse@([x,y]-triangle[0,:2]);height=triangle[0,2]+weights@(triangle[1:,2]-triangle[0,2])
                longitude,latitude=to_geo(x,y);earth=np.array(to_ecef(longitude,latitude,height))-origin
                vertices[kind].extend([float(earth@east),float(earth@up),float(earth@south)])
            area+=piece.area
    if area:records.append(dict(sourceId=identifier,surfaceKind=kind,areaSquareMetres=area))

for collection in ['wegdeel','ondersteunendwegdeel']:
    for feature in json.loads((source/(collection+'.json')).read_text())['features']:
        p=feature['properties']
        # Lower shore/under-bridge surfaces overlap in XY and must stay below.
        if p['status']!='bestaand' or p.get('termination_date') or p['relatieve_hoogteligging']!=3:continue
        g=transform(to_rd,shape(feature['geometry']))
        if not g.intersects(footprint):continue
        kind={'fietspad':'cycleway','voetpad':'bridge-footway','OV-baan':'bridge-track-bed','berm':'bridge-divider'}.get(p['functie'],'road')
        if p['functie']=='fietspad':cycle_surfaces.append(g)
        if kind=='road':carriageways.append((g,p['lokaal_id']))
        emit(g,kind,p['lokaal_id'])

# The retained 2026 aerial shows a continuous white motor-road edge beside
# each red cycle lane. Derive that observed boundary from its exact BGT regions;
# do not add guessed centre dashes, arrows or bicycle pictograms.
cycles=unary_union(cycle_surfaces)
_,_,deck_axes=np.linalg.svd(triangles[:,:,:2].reshape(-1,2)-triangles[:,:,:2].reshape(-1,2).mean(axis=0),full_matrices=False)
deck_axis=deck_axes[0]
for road,identifier in carriageways:
    edge=road.buffer(-.22).boundary.intersection(cycles.buffer(3))
    parts=list(edge.geoms) if hasattr(edge,'geoms') else [edge]
    longitudinal=[]
    for part in parts:
        if part.geom_type!='LineString':continue
        for a,b in zip(list(part.coords),list(part.coords)[1:]):
            delta=np.array(b)-a
            if np.linalg.norm(delta)>1e-6 and abs(delta@deck_axis)/np.linalg.norm(delta)>.7:longitudinal.append(LineString([a,b]))
    emit(unary_union(longitudinal).buffer(.075,cap_style='flat',join_style='mitre'),'bridge-edge-paint',identifier)

# BGT explicitly records the centre between a track's two rails, not the rails.
# Rotterdam standard gauge is 1.435m (CROW vehicle characteristics, retained URL).
for feature in json.loads((source/'spoor.json').read_text())['features']:
    p=feature['properties']
    if p['status']!='bestaand' or p.get('termination_date') or p['functie']!='tram' or p['relatieve_hoogteligging']!=3:continue
    line=transform(to_rd,shape(feature['geometry']))
    for side in [-1,1]:
        rail=line.offset_curve(side*1.435/2,join_style='mitre')
        emit(rail.buffer(.11,cap_style='flat',join_style='mitre'),'rail-groove',p['lokaal_id'])
        emit(rail.buffer(.045,cap_style='flat',join_style='mitre'),'rail-steel',p['lokaal_id'])

# Keep source surfaces in an explicit order so the thin steel stroke is on its
# actual groove; runtime polygon offset avoids flicker without changing height.
doc={'asset':{'version':'2.0','generator':'010 exact Erasmus BGT detail'},'scene':0,'scenes':[{'nodes':[]}],'nodes':[],'meshes':[],'accessors':[],'bufferViews':[],'buffers':[{'byteLength':0}]};chunks=[];offset=0
for kind,values in vertices.items():
    a=np.asarray(values,dtype='<f4').reshape(-1,3)
    chunks.append(a.tobytes());doc['bufferViews'].append(dict(buffer=0,byteOffset=offset,byteLength=a.nbytes,target=34962));doc['accessors'].append(dict(bufferView=len(doc['bufferViews'])-1,componentType=5126,count=len(a),type='VEC3',min=a.min(axis=0).tolist(),max=a.max(axis=0).tolist()));doc['meshes'].append(dict(name=kind,extras=dict(surfaceKind=kind,sourceStage='Exact BGT level3 polygons and tram axes; native surveyed deck height'),primitives=[dict(attributes=dict(POSITION=len(doc['accessors'])-1),mode=4)]));doc['nodes'].append(dict(mesh=len(doc['meshes'])-1));doc['scenes'][0]['nodes'].append(len(doc['nodes'])-1);offset+=a.nbytes
binary=b''.join(chunks);doc['buffers'][0]['byteLength']=len(binary);metadata=json.dumps(doc,separators=(',',':')).encode();metadata+=b' '*(-len(metadata)%4);glb=struct.pack('<4sII',b'glTF',2,28+len(metadata)+len(binary))+struct.pack('<I4s',len(metadata),b'JSON')+metadata+struct.pack('<I4s',len(binary),b'BIN\0')+binary
(output/'erasmus.glb').write_bytes(glb)
manifest=json.loads((output/'manifest.json').read_text());model=next(m for m in manifest['models'] if m['name']=='erasmus');model.update(features=records,triangles=sum(len(v)//9 for v in vertices.values()),bytes=len(glb),surfaceSource='Exact retained BGT level3 features',sourceHashes={n:hashlib.sha256((source/(n+'.json')).read_bytes()).hexdigest() for n in ['wegdeel','spoor','ondersteunendwegdeel']},trackInterpretation=dict(axisSource='BGT spoor: centre between the two steel rails',gaugeMetres=1.435,grooveDrawingWidthMetres=.22,steelDrawingWidthMetres=.09,gaugeReference='https://kennisbank.crow.nl/public/gastgebruiker/VMGT/Karakteristieken_van_voertuigen_en_mensen/Tram/15023',limitation='Rail head/groove stroke widths are drawing, not surveyed sections; no invented sleepers, poles or barriers.'))
model['roadEdgePaintInterpretation']=dict(evidence='Retained 2026 official aerial: continuous white boundary between motor carriageway and cycle corridor',placement='22cm inside corresponding BGT motor carriageway boundary beside cycle footprints',drawingWidthMetres=.15,limitation='Illustrated edge stroke; no inferred dashed lanes, arrows, crossings or symbols')
manifest['interpretation']='Erasmus: exact BGT level3 road/walk/cycle/divider footprints and individual tram axes on original surveyed native deck. Other bridges retain reviewed BRT interpretation.'
(output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(dict(triangles=model['triangles'],bytes=len(glb),kinds=list(vertices))))
