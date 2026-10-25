"""Municipal BGT ground conversion. Written by AI on 2026-10-25 by model GPT-6.1 Sol.

3D Rotterdam's local Y values already contain NAP heights (e.g. Rivier -0.66,
quay top +3.1), but its RTC centre is at ellipsoid height zero. Therefore
applying a geoid correction to the embedded heights would subtract ~43 m twice.
Horizontal coordinates use the actual node/RTC ECEF transform and RDTRANS2018;
vertical coordinates retain the municipality's local NAP values explicitly.
No invented flat ground fills holes. In this bounded ground-only extract, source
features with Y below -10 m are excluded wholesale: observed spikes are nodata
interpolations near -50/-100 m, not measured ground. This is a dataset-specific
defect rule, not a universal elevation constraint. Real quay faces are retained.
"""
import concurrent.futures
import json
import struct
from urllib.parse import urljoin
import numpy as np
import pyproj
from PIL import Image, ImageDraw
from archive import fetch, ROOT, DATE

BASE = 'https://www.3drotterdam.nl/datasource-data/0025cb58-e0f5-4169-bb4c-5339a3bc2a7e/'
TRANSFORM_DESCRIPTION = 'Node matrix; glTF Y-up to 3D Tiles Z-up; RTC ECEF; RDTRANS2018 horizontal grid; source local NAP Y retained because RTC origin has ellipsoid height 0'
_TRIANGLES = None
_SOURCE_CLASSES = None
_SOURCE_STATS = None
_EXCLUDED_TRIANGLES = None

# Municipal feature semantics are also kept in code, including vertical faces.
MUNICIPAL_CLASSES = {
 'Kademuur':13, 'Muurvlak':13, 'Kunstwerk':13,
 'Rijbaan':1, 'Rijwielpad':2, 'Voetpad':3, 'Voetpad op Trap':3,
 'Parkeerplaats':4, 'OV Baan':5, 'Gras':6, 'Berm':6,
 'Groenvoorziening':7, 'Cultuur Rozen':7, 'Heesters':7, 'Plantenperken':7,
 'Rivier':8, 'Waterloop':8, 'Water':8, 'Meer':8,
 'Onbebouwd':9, 'Gesloten Verharding':10, 'Overige Verharding':10,
 'Bedrijfsterrein':10, 'Valdempende Ondergrond Kunstgras':10,
 'Hoofdgebouw':11, 'Bijgebouw':11, 'Luifel':11, 'Overkapping':11,
 'Verkeerseiland':15,
 'Lage Trafo':13, 'Pijler Overbrugging':13, 'Sloof':13, 'Rooster':13, 'Sluis':13,
 'Bosplantsoen':7, 'Struik':7, 'Haag':7, 'Berm Groenvoorziening':6,
 'Greppel':9, 'Onverhard':9, 'Half Verhard':9, 'Zand':9,
 'Oever Slootkant':6, 'Toegangstrap':3, 'Bassin':8,
}

def _accessor(document, binary, index):
    accessor = document['accessors'][index]
    view = document['bufferViews'][accessor['bufferView']]
    dtype = {5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'}[accessor['componentType']]
    width = {'VEC3':3,'VEC2':2,'VEC4':4,'SCALAR':1}[accessor['type']]
    itemsize = np.dtype(dtype).itemsize
    return np.ndarray((accessor['count'], width), dtype=dtype, buffer=binary,
       offset=view.get('byteOffset',0)+accessor.get('byteOffset',0),
       strides=(view.get('byteStride',width*itemsize),itemsize)).copy()

def _decode_ground(uri, transformer):
    body = fetch('ground3d',uri,urljoin(BASE,uri))
    header = struct.unpack_from('<7I',body)
    feature_table = json.loads(body[28:28+header[3]])
    batch_start = 28+header[3]+header[4]
    batch_table = json.loads(body[batch_start:batch_start+header[5]])
    glb_start = 28+sum(header[3:7])
    json_size = struct.unpack_from('<I',body,glb_start+12)[0]
    document = json.loads(body[glb_start+20:glb_start+20+json_size])
    binary = body[glb_start+28+json_size:]
    triangles, classes, excluded_triangles = [], [], []
    missing = 0
    # Defects often affect whole survey features: remove the feature, not merely
    # the lowest vertex's triangle, and archive the exact rejected metadata.
    minimum_heights=np.full(len(batch_table['attributes']),np.inf)
    maximum_heights=np.full(len(batch_table['attributes']),-np.inf)
    for mesh in document['meshes']:
        for primitive in mesh['primitives']:
            positions=_accessor(document,binary,primitive['attributes']['POSITION'])
            batch_ids=_accessor(document,binary,primitive['attributes']['_BATCHID']).ravel().astype(int)
            np.minimum.at(minimum_heights,batch_ids,positions[:,1])
            np.maximum.at(maximum_heights,batch_ids,positions[:,1])
    invalid_features=minimum_heights < -10
    rejected=[{'batch_index':int(i),'source_height_min_m':float(minimum_heights[i]),'source_height_max_m':float(maximum_heights[i]),**batch_table['attributes'][i]} for i in np.flatnonzero(invalid_features)]
    metadata = batch_table['attributes']
    node_matrices = {}
    def visit_node(index, parent_matrix):
        node = document['nodes'][index]
        local_matrix = np.array(node.get('matrix',np.eye(4).T.ravel())).reshape(4,4).T
        node_matrices[index] = parent_matrix @ local_matrix
        for child in node.get('children',[]):visit_node(child,node_matrices[index])
    for index in document['scenes'][document.get('scene',0)]['nodes']:
        visit_node(index,np.eye(4))
    for index,matrix in node_matrices.items():
        node=document['nodes'][index]
        if 'mesh' not in node: continue
        for primitive in document['meshes'][node['mesh']]['primitives']:
            position = _accessor(document,binary,primitive['attributes']['POSITION']).astype('float64')
            batch = _accessor(document,binary,primitive['attributes']['_BATCHID']).ravel().astype(int)
            indices = _accessor(document,binary,primitive['indices']).ravel().reshape(-1,3)
            rotated = position @ matrix[:3,:3].T + matrix[:3,3]
            ecef = rotated[:,[0,2,1]] * [1,-1,1] + feature_table['RTC_CENTER']
            rd = np.array(transformer.transform(*ecef.T)).T
            rd[:,2] = position[:,1]
            valid = ~invalid_features[batch[indices[:,0]]]
            missing += int((~valid).sum())
            excluded_triangles.append(rd[indices[~valid]])
            indices = indices[valid]
            source_classes = np.array([MUNICIPAL_CLASSES.get(m['KLASSE'],0) for m in metadata],dtype=np.uint8)
            triangles.append(rd[indices])
            classes.append(source_classes[batch[indices[:,0]]])
    dates = [str(m.get('INWIN','')) for m in metadata if m.get('INWIN')]
    return np.concatenate(triangles),np.concatenate(classes),{'uri':uri,'triangles_missing_height':missing,'rejected_features':rejected,
       'excluded_projected_triangle_area_m2_sum':float(sum(np.abs((t[:,1,0]-t[:,0,0])*(t[:,2,1]-t[:,0,1])-(t[:,1,1]-t[:,0,1])*(t[:,2,0]-t[:,0,0])).sum()/2 for t in excluded_triangles)),'survey_date_min':min(dates,default=None),'survey_date_max':max(dates,default=None),'unmapped_classes':sorted({m['KLASSE'] for m in metadata if m['KLASSE'] not in MUNICIPAL_CLASSES})},np.concatenate(excluded_triangles)

def prepare_geometry(bounds):
    """Archive intersecting source tiles and hold their RD/NAP triangles in memory."""
    global _TRIANGLES,_SOURCE_CLASSES,_SOURCE_STATS,_EXCLUDED_TRIANGLES
    for name in ['nl_nsgi_nlgeo2018.tif','nl_nsgi_rdtrans2018.tif']:
        fetch('proj-grids',name,'https://cdn.proj.org/'+name)
    pyproj.network.set_network_enabled(False)
    pyproj.datadir.append_data_dir(str(ROOT/'sources/proj-grids'/DATE))
    # Explicit pipeline avoids dynamic network grid selection and ballpark fallback.
    transformer = pyproj.Transformer.from_pipeline('proj=pipeline step inv proj=cart ellps=GRS80 step inv proj=vgridshift grids=nl_nsgi_nlgeo2018.tif multiplier=1 step inv proj=hgridshift grids=nl_nsgi_rdtrans2018.tif step proj=sterea lat_0=52.1561605555556 lon_0=5.38763888888889 k=0.9999079 x_0=155000 y_0=463000 ellps=bessel')
    geographic = pyproj.Transformer.from_crs(4326,28992,always_xy=True)
    tileset = json.loads(fetch('ground3d','tileset.json',BASE+'tileset.json'))
    uris = []
    def walk(node):
        region = node['boundingVolume']['region']
        east,north = geographic.transform(np.rad2deg([region[0],region[2]]),np.rad2deg([region[1],region[3]]))
        if max(east)<bounds[0]-5 or min(east)>bounds[2]+5 or max(north)<bounds[1]-5 or min(north)>bounds[3]+5:return
        if 'content' in node:uris.append(node['content']['uri'])
        for child in node.get('children',[]):walk(child)
    walk(tileset['root'])
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(lambda uri:_decode_ground(uri,transformer),uris))
    _TRIANGLES = np.concatenate([r[0] for r in results])
    _SOURCE_CLASSES = np.concatenate([r[1] for r in results])
    _EXCLUDED_TRIANGLES = np.concatenate([r[3] for r in results])
    _SOURCE_STATS = {'transform':TRANSFORM_DESCRIPTION,'transform_pipeline':transformer.definition,
       'municipal_class_mapping':MUNICIPAL_CLASSES,
       'height_datum_evidence':{'rtc_ellipsoid_height_m':0,'representative_source_water_nap_m':[-0.71,-0.66],'literal_ecef_to_nap_water_m':[-44.33,-44.28],
         'interpretation':'Municipal source stores NAP as local up against zero-ellipsoid RTC; preserving local up prevents double geoid subtraction. Local tangent plane introduces centimetre curvature uncertainty.'},
       'height_defect_policy':'Discard entire source features containing local Y below -10m in this bounded ground extract: observed nodata interpolation near -50/-100m. Leave holes; no replacement heights.',
       'tiles':[r[2] for r in results]}
    return _SOURCE_STATS

def _clip_triangle(triangle, xmin,ymin,xmax,ymax):
    polygon = list(triangle)
    for axis,edge,sign in [(0,xmin,1),(0,xmax,-1),(1,ymin,1),(1,ymax,-1)]:
        clipped=[]
        for start,end in zip(polygon,polygon[1:]+polygon[:1]):
            start_inside=(start[axis]-edge)*sign>=0
            end_inside=(end[axis]-edge)*sign>=0
            if start_inside:clipped.append(start)
            if start_inside != end_inside:
                fraction=(edge-start[axis])/(end[axis]-start[axis])
                clipped.append(start+fraction*(end-start))
        polygon=clipped
        if len(polygon)<3:return []
    return [np.array([polygon[0],polygon[i],polygon[i+1]]) for i in range(1,len(polygon)-1)]

def _write_glb(path, triangles, classes, extras):
    vertices = triangles.reshape(-1,3).astype('<f4')
    normals=np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])
    normals /= np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-20)
    normals=np.repeat(normals,3,axis=0).astype('<f4')
    vertex_classes=np.repeat(classes,3).astype('u1')
    buffers=[vertices.tobytes(),normals.tobytes(),vertex_classes.tobytes()]
    binary=b'';views=[]
    for data in buffers:
        views.append({'buffer':0,'byteOffset':len(binary),'byteLength':len(data),'target':34962})
        binary+=data+b'\0'*((-len(data))%4)
    document={'asset':{'version':'2.0','generator':'010 municipal ground pipeline'},'scene':0,'scenes':[{'nodes':[0]}],'nodes':[{'mesh':0}],
      'meshes':[{'primitives':[{'attributes':{'POSITION':0,'NORMAL':1,'_CLASS':2},'material':0,'mode':4}]}],
      'materials':[{'name':'data-classified ground','doubleSided':True,'pbrMetallicRoughness':{'baseColorFactor':[1,1,1,1],'metallicFactor':0,'roughnessFactor':1}}],
      'buffers':[{'byteLength':len(binary)}],'bufferViews':views,
      'accessors':[{'bufferView':0,'componentType':5126,'count':len(vertices),'type':'VEC3','min':vertices.min(0).tolist(),'max':vertices.max(0).tolist()},
      {'bufferView':1,'componentType':5126,'count':len(vertices),'type':'VEC3'},
      {'bufferView':2,'componentType':5121,'count':len(vertices),'type':'SCALAR'}],'extras':extras}
    json_bytes=json.dumps(document,separators=(',',':')).encode();json_bytes+=b' '*((-len(json_bytes))%4)
    result=struct.pack('<4sII',b'glTF',2,28+len(json_bytes)+len(binary))+struct.pack('<I4s',len(json_bytes),b'JSON')+json_bytes+struct.pack('<I4s',len(binary),b'BIN\0')+binary
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(result)

def build_tile_geometry(x,y,class_map):
    """Write one ground.glb. class_map is the 2500-square R-channel ndarray."""
    if _TRIANGLES is None:raise RuntimeError('Call prepare_geometry first')
    bounds=(x,y,x+250,y+250)
    minimum=_TRIANGLES[:,:,:2].min(1);maximum=_TRIANGLES[:,:,:2].max(1)
    intersects=(maximum[:,0]>=x)&(minimum[:,0]<=x+250)&(maximum[:,1]>=y)&(minimum[:,1]<=y+250)
    candidates=_TRIANGLES[intersects];candidate_classes=_SOURCE_CLASSES[intersects]
    inside=(candidates[:,:,0]>=x).all(1)&(candidates[:,:,0]<=x+250).all(1)&(candidates[:,:,1]>=y).all(1)&(candidates[:,:,1]<=y+250).all(1)
    triangles=list(candidates[inside]);classes=list(candidate_classes[inside])
    for triangle,source_class in zip(candidates[~inside],candidate_classes[~inside]):
        clipped=_clip_triangle(triangle,*bounds);triangles.extend(clipped);classes.extend([source_class]*len(clipped))
    triangles=np.array(triangles);classes=np.array(classes,dtype=np.uint8)
    areas=np.linalg.norm(np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]),axis=1)
    valid=areas>1e-8;triangles=triangles[valid];classes=classes[valid]
    centroids=triangles.mean(1)
    columns=np.clip(((centroids[:,0]-x)*10).astype(int),0,2499)
    rows=np.clip(((y+250-centroids[:,1])*10).astype(int),0,2499)
    sampled=np.asarray(class_map)[rows,columns]
    # Keep municipal civil/wall semantics; classify remaining surfaces from current BGT.
    override=(sampled!=0)&(classes!=13)
    classes[override]=sampled[override]
    local=triangles.copy();local[:,:,0]-=x;local[:,:,1]=triangles[:,:,2];local[:,:,2]=-(triangles[:,:,1]-y)
    stats={'ground_triangles':len(local),'ground_nap_range_m':[float(triangles[:,:,2].min()),float(triangles[:,:,2].max())],
       'ground_vertical_faces':int((np.abs(np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0])[:,2])<areas[valid]*0.1).sum()),
       'ground_class_triangle_counts':{str(k):int(v) for k,v in zip(*np.unique(classes,return_counts=True))}}
    excluded_minimum=_EXCLUDED_TRIANGLES[:,:,:2].min(1);excluded_maximum=_EXCLUDED_TRIANGLES[:,:,:2].max(1)
    excluded_intersects=(excluded_maximum[:,0]>=x)&(excluded_minimum[:,0]<=x+250)&(excluded_maximum[:,1]>=y)&(excluded_minimum[:,1]<=y+250)
    excluded_clipped=[]
    for triangle in _EXCLUDED_TRIANGLES[excluded_intersects]:excluded_clipped.extend(_clip_triangle(triangle,*bounds))
    if excluded_clipped:
        excluded_clipped=np.array(excluded_clipped)
        projected=excluded_clipped[:,:,:2]
        difference_a=projected[:,1]-projected[:,0];difference_b=projected[:,2]-projected[:,0]
        excluded_area=float(np.abs(difference_a[:,0]*difference_b[:,1]-difference_a[:,1]*difference_b[:,0]).sum()/2)
    else:excluded_area=0.0
    stats['ground_excluded_projected_triangle_area_m2_sum']=excluded_area
    coverage_image=Image.new('1',(2500,2500),0)
    coverage_draw=ImageDraw.Draw(coverage_image)
    for triangle in triangles:
        first=triangle[1,:2]-triangle[0,:2];second=triangle[2,:2]-triangle[0,:2]
        if abs(first[0]*second[1]-first[1]*second[0])<=1e-8:continue
        coverage_draw.polygon([((vertex[0]-x)*10,(y+250-vertex[1])*10) for vertex in triangle],fill=1)
    coverage=np.asarray(coverage_image,dtype=bool)
    nonbuilding=np.asarray(class_map)!=11
    uncovered_nonbuilding=(~coverage)&nonbuilding
    stats['ground_coverage_fraction']=float(coverage.mean())
    stats['ground_uncovered_nonbuilding_pixels']=int(uncovered_nonbuilding.sum())
    stats['ground_uncovered_nonbuilding_fraction']=float(uncovered_nonbuilding.sum()/max(nonbuilding.sum(),1))
    stats['ground_uncovered_nonbuilding_area_m2']=float(uncovered_nonbuilding.sum()/100)

    path=ROOT/f'scene/v1/tiles/x{x}_y{y}/ground.glb'
    _write_glb(path,local,classes,{'source':'Rotterdam BGT 3D','coordinate_system':'RD New + source NAP','transform':TRANSFORM_DESCRIPTION,**stats})
    return stats
