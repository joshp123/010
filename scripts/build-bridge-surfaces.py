#!/usr/bin/env python3
"""Written by AI on 2026-10-24 by model GPT-6.
Reconcile retained BRT bridge surface footprints with reviewed native deck triangles.
Needs the existing project Python environment with numpy, pyproj and shapely.
Native bytes are cached by hash; changes require a new explicit deck review.
"""
import collections, gzip, hashlib, json, struct, urllib.request
from pathlib import Path
import numpy as np
from shapely.geometry import shape, Polygon
from shapely.ops import transform, unary_union
from shapely import constrained_delaunay_triangles
from pyproj import Transformer

project = Path(__file__).resolve().parent.parent
ROOT = project / 'work/data-cache/bridge-surfaces'
ROOT.mkdir(parents=True, exist_ok=True)
output = project / 'public/data/bridge-surfaces'
output.mkdir(parents=True, exist_ok=True)
reviews = json.loads((project/'source-data/bridge-decks.json').read_text())
earth_to_geographic = Transformer.from_crs(4978, 4979, always_xy=True)
geographic_to_rd = Transformer.from_crs(4979, 28992, always_xy=True)
gltf_y_up_to_earth_z_up = np.array([[1,0,0,0], [0,0,-1,0], [0,1,0,0], [0,0,0,1]], dtype=float)

def load_native_triangles(source_hash):
    raw = (ROOT / (source_hash + '.b3dm')).read_bytes()
    _, _, _, feature_json_length, feature_binary_length, batch_json_length, batch_binary_length = struct.unpack_from('<4s6I', raw)
    feature_table = json.loads(raw[28:28 + feature_json_length])
    glb_offset = 28 + feature_json_length + feature_binary_length + batch_json_length + batch_binary_length
    glb = raw[glb_offset:]
    json_length = struct.unpack_from('<I', glb, 12)[0]
    document = json.loads(glb[20:20 + json_length])
    binary = glb[28 + json_length:]
    rtc_centre = feature_table.get('RTC_CENTER') or document.get('extensions', {}).get('CESIUM_RTC', {}).get('center') or [0, 0, 0]

    def accessor_values(accessor_index):
        accessor = document['accessors'][accessor_index]
        view = document['bufferViews'][accessor['bufferView']]
        data_type = {5126:'<f4', 5125:'<u4', 5123:'<u2', 5121:'u1', 5122:'<i2'}[accessor['componentType']]
        components = {'SCALAR':1, 'VEC2':2, 'VEC3':3, 'VEC4':4}[accessor['type']]
        item_size = np.dtype(data_type).itemsize
        return np.ndarray((accessor['count'], components), dtype=data_type, buffer=binary,
            offset=view.get('byteOffset', 0) + accessor.get('byteOffset', 0),
            strides=(view.get('byteStride', item_size * components), item_size)).copy()

    triangles = []
    def visit(node_index, parent_matrix):
        node = document['nodes'][node_index]
        matrix = np.array(node.get('matrix', np.eye(4).flatten(order='F'))).reshape((4, 4), order='F')
        world_matrix = parent_matrix @ matrix
        if 'mesh' in node:
            for primitive in document['meshes'][node['mesh']]['primitives']:
                if primitive.get('mode', 4) != 4:
                    continue
                positions = accessor_values(primitive['attributes']['POSITION'])
                earth_positions = (np.c_[positions, np.ones(len(positions))] @ world_matrix.T)[:, :3] + rtc_centre
                longitude, latitude, height = earth_to_geographic.transform(*earth_positions.T)
                x, y = geographic_to_rd.transform(longitude, latitude)
                rd_positions = np.c_[x, y, height]
                indices = accessor_values(primitive['indices']).flatten().astype(int) if 'indices' in primitive else np.arange(len(rd_positions))
                triangles.append(rd_positions[indices.reshape((-1, 3))])
        for child_index in node.get('children', []):
            visit(child_index, world_matrix)
    for root_index in document['scenes'][document.get('scene', 0)]['nodes']:
        visit(root_index, gltf_y_up_to_earth_z_up)
    return np.concatenate(triangles)

def build(review):
    raw_path = ROOT/(review['sha256']+'.b3dm')
    if not raw_path.exists():
        raw = urllib.request.urlopen(review['url']).read()
        if raw[:2] == b'\x1f\x8b': raw = gzip.decompress(raw)
        if hashlib.sha256(raw).hexdigest() != review['sha256']:
            raise ValueError('Native source edition changed; review its deck before regeneration: '+review['name'])
        raw_path.write_bytes(raw)
    if hashlib.sha256(raw_path.read_bytes()).hexdigest() != review['sha256']:
        raise ValueError('Cached native bridge hash mismatch: '+review['name'])
    triangles = load_native_triangles(review['sha256'])
    deck = review['deckTriangles']
    deck_footprint = unary_union([Polygon(triangles[index, :, :2]) for index in deck])
    transport_path = project / 'source-data/transport-network.geojson.gz'
    transport_bytes = gzip.decompress(transport_path.read_bytes())
    transport = json.loads(transport_bytes)
    project_rd = Transformer.from_crs(4326, 28992, always_xy=True).transform
    rd_to_geographic = Transformer.from_crs(28992, 4326, always_xy=True).transform
    geographic_to_earth = Transformer.from_crs(4979, 4978, always_xy=True).transform
    longitude, latitude = np.deg2rad([4.49, 51.915])
    east = np.array([-np.sin(longitude), np.cos(longitude), 0])
    up = np.array([np.cos(latitude)*np.cos(longitude), np.cos(latitude)*np.sin(longitude), np.sin(latitude)])
    south = np.array([np.sin(latitude)*np.cos(longitude), np.sin(latitude)*np.sin(longitude), -np.cos(latitude)])
    origin = np.array(geographic_to_earth(4.49, 51.915, 0))
    vertices_by_kind = collections.defaultdict(list)
    records = []
    for feature in transport['features']:
        properties = feature['properties']
        if 'brug' not in properties.get('fysiekvoorkomen', '') or properties.get('status') != 'in gebruik':
            continue
        geometry = transform(project_rd, shape(feature['geometry']))
        purpose = properties.get('hoofdverkeersgebruik', '')
        kind = 'rail' if properties['kind'] == 'rail' else 'cycleway' if 'fiets' in purpose else 'footway' if 'voetganger' in purpose else 'road'
        width = None
        if geometry.geom_type.endswith('LineString'):
            width = 6 if properties.get('aantalsporen') == 'dubbel' else 3.2
            geometry = geometry.buffer(width / 2, cap_style='flat', join_style='mitre')
        if not geometry.intersects(deck_footprint):
            continue
        emitted_area = 0
        for triangle_index in deck:
            triangle = triangles[triangle_index]
            overlap = geometry.intersection(Polygon(triangle[:, :2]))
            if overlap.area < 1e-6:
                continue
            determinant = np.column_stack((triangle[1, :2]-triangle[0, :2], triangle[2, :2]-triangle[0, :2]))
            for fragment in constrained_delaunay_triangles(overlap).geoms:
                if not overlap.covers(fragment):
                    continue
                emitted_area += fragment.area
                fragment_coordinates = list(fragment.exterior.coords)[:3]
                if not fragment.exterior.is_ccw:
                    fragment_coordinates.reverse()
                for x, y in fragment_coordinates:
                    weights = np.linalg.solve(determinant, np.array([x,y])-triangle[0,:2])
                    height = triangle[0,2] + weights @ (triangle[1:,2]-triangle[0,2])
                    lon, lat = rd_to_geographic(x,y)
                    earth = np.array(geographic_to_earth(lon, lat, height)) - origin
                    vertices_by_kind[kind].extend([float(earth @ east), float(earth @ up), float(earth @ south)])
        if emitted_area:
            records.append({'sourceId': properties.get('lokaal_id'), 'surfaceKind': kind, 'areaSquareMetres': emitted_area, 'physicalForm': properties.get('fysiekvoorkomen'), 'railRibbonWidthMetres': width})
    # Standard glTF geometry carries source classes; presentation assigns materials.
    document = {'asset': {'version':'2.0','generator':'010 bridge-surfaces-probe'},'scene':0,'scenes':[{'nodes':[]}],'nodes':[],'meshes':[],'accessors':[],'bufferViews':[],'buffers':[{'byteLength':0}]}
    chunks = []; offset = 0
    for kind, vertices in vertices_by_kind.items():
        array = np.array(vertices, dtype='<f4').reshape(-1,3)
        chunks.append(array.tobytes())
        document['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':array.nbytes,'target':34962})
        document['accessors'].append({'bufferView':len(document['bufferViews'])-1,'componentType':5126,'count':len(array),'type':'VEC3','min':array.min(axis=0).tolist(),'max':array.max(axis=0).tolist()})
        document['meshes'].append({'name':kind,'extras':{'surfaceKind':kind,'sourceStage':'BRT semantic footprints intersected with native deck'},'primitives':[{'attributes':{'POSITION':len(document['accessors'])-1},'mode':4}]})
        document['nodes'].append({'mesh':len(document['meshes'])-1}); document['scenes'][0]['nodes'].append(len(document['nodes'])-1)
        offset += array.nbytes
    binary = b''.join(chunks); document['buffers'][0]['byteLength'] = len(binary)
    metadata = json.dumps(document,separators=(',',':')).encode();metadata += b' ' * (-len(metadata)%4)
    glb = struct.pack('<4sII',b'glTF',2,28+len(metadata)+len(binary))+struct.pack('<I4s',len(metadata),b'JSON')+metadata+struct.pack('<I4s',len(binary),b'BIN\0')+binary
    (output/(review['name']+'.glb')).write_bytes(glb)
    all_positions=np.concatenate([np.array(vertices,dtype=float).reshape(-1,3) for vertices in vertices_by_kind.values()])
    minimum=all_positions.min(axis=0); maximum=all_positions.max(axis=0); centre=(minimum+maximum)/2; half=(maximum-minimum)/2
    box=[float(centre[0]),float(-centre[2]),float(centre[1]),float(half[0]),0,0,0,float(half[2]),0,0,0,float(half[1])]
    return {'name':review['name'],'nativeSource':review['url'],'nativeSha256':review['sha256'],'transportSha256':hashlib.sha256(transport_bytes).hexdigest(),'features':records,'triangles':sum(len(vertices)//9 for vertices in vertices_by_kind.values()),'bytes':len(glb),'box':box}

def main():
    results=[build(review) for review in reviews['reviews']]
    latitude,longitude=np.deg2rad([51.915,4.49])
    east=np.array([-np.sin(longitude),np.cos(longitude),0])
    up=np.array([np.cos(latitude)*np.cos(longitude),np.cos(latitude)*np.sin(longitude),np.sin(latitude)])
    north=np.cross(up,east)
    origin=np.array(Transformer.from_crs(4979,4978,always_xy=True).transform(4.49,51.915,0))
    matrix=np.eye(4);matrix[:3,0]=east;matrix[:3,1]=north;matrix[:3,2]=up;matrix[:3,3]=origin
    # Root region is geographic/ECEF; children boxes use the ENU root transform.
    children=[{'boundingVolume':{'box':result['box']},'geometricError':0,'content':{'uri':result['name']+'.glb'}} for result in results]
    # Conservative root box encloses the full municipality; empty parent has no coarse content.
    tileset={'asset':{'version':'1.1'},'geometricError':100000,'root':{'transform':matrix.flatten(order='F').tolist(),'boundingVolume':{'box':[-15000,0,30,30000,0,0,0,15000,0,0,0,200]},'geometricError':100000,'refine':'ADD','children':children}}
    (output/'tileset.json').write_text(json.dumps(tileset,separators=(',',':'))+'\n')
    manifest={'writtenBy':'AI, GPT-6, 2026-10-24','coordinateFrame':{'latitude':51.915,'longitude':4.49,'glTF':'X east, Y up, Z south','tiles':'X east, Y north, Z up'},'method':'Intersect surveyed bridge-tagged BRT polygons with explicit hash-pinned native deck triangles; barycentric native height. No structure geometry. No display offset baked in.','interpretation':'Double tram centreline uses existing street stage 6 m ribbon; single track 3.2 m. Unknown deck strips remain native. BRT was simplified 1 m upstream; original API responses remain cached.','license':'BRT CC BY 4.0 Kadaster / PDOK; native geometry public domain, credit Gemeente Rotterdam.', 'sourceReferences':['https://api.pdok.nl/brt/top10nl/ogc/v1/','https://data.overheid.nl/dataset/10230-rotterdam-3d'],'reviews':'source-data/bridge-decks.json','omissions':reviews['omissions'],'models':results}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'models':len(results),'triangles':sum(r['triangles'] for r in results),'bytes':sum(r['bytes'] for r in results),'omitted':len(reviews['omissions'])}))

if __name__ == '__main__':
    main()
