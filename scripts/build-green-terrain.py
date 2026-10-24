#!/usr/bin/env python3
"""Written by AI on 2026-10-24 by model GPT-6.
Prepare measured semantic terrain for middle-distance views. Requires project numpy,
pyproj and shapely. Original source geometry stays in an ignored compressed cache.
"""
import concurrent.futures
import gzip
import hashlib
import json
import math
import struct
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path

import numpy as np
from pyproj import Transformer
from shapely import contains_xy
from shapely.geometry import box, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

PROJECT = Path(__file__).resolve().parent.parent
CACHE = PROJECT / 'work/data-cache/green-terrain'
OUTPUT = PROJECT / 'public/data/green-terrain'
BASE = 'https://www.3drotterdam.nl/datasource-data/0025cb58-e0f5-4169-bb4c-5339a3bc2a7e/'
CACHE.mkdir(parents=True, exist_ok=True)
OUTPUT.mkdir(parents=True, exist_ok=True)
fetch_data = SourceFileLoader('map_source_fetch', str(PROJECT/'scripts/fetch-data.py')).load_module()
municipality = shape(json.loads((PROJECT/'public/data/municipality.json').read_bytes())['features'][0]['geometry'])


def acquire(url):
    path = CACHE/(hashlib.sha256(url.encode()).hexdigest()+'.bin.gz')
    metadata_path = path.with_suffix('.json')
    if not path.exists():
        with urllib.request.urlopen(url, timeout=120) as response:
            raw = response.read()
            headers = dict(response.headers)
        decoded = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
        path.write_bytes(gzip.compress(decoded, mtime=0))
        metadata_path.write_text(json.dumps({'url':url, 'sha256':hashlib.sha256(decoded).hexdigest(), 'decodedBytes':len(decoded), 'acquiredAt':datetime.now(timezone.utc).isoformat(), 'headers':headers})+'\n')
    return gzip.decompress(path.read_bytes()), json.loads(metadata_path.read_text())


def selected_tiles():
    inventory_bytes, inventory = acquire(BASE+'tileset.json')
    native = json.loads(inventory_bytes)
    source_features = fetch_data.read_collection('terrein_vlak', municipality.bounds)
    green, dune = [], []
    for feature in source_features:
        usage = feature['properties'].get('typelandgebruik', '').lower()
        if any(word in usage for word in ['bos', 'gras', 'heide', 'duin', 'zand']):
            geometry = shape(feature['geometry']).intersection(municipality)
            if not geometry.is_empty:
                green.append(geometry)
                if 'duin' in usage:
                    dune.append(geometry)
    tree = STRtree(green)
    dune_geometry = unary_union(dune)
    tiles = []
    def visit(tile):
        if 'content' in tile:
            content = tile['content']
            region = content.get('boundingVolume', tile['boundingVolume'])['region']
            bounds = box(*(value*180/math.pi for value in region[:4]))
            municipal_area = bounds.intersection(municipality).area
            if region[5] > -90 and municipal_area:
                green_fraction = min(1, sum(bounds.intersection(green[index]).area for index in tree.query(bounds))/municipal_area)
                dune_fraction = bounds.intersection(dune_geometry).area/municipal_area
                if green_fraction >= .4 or dune_fraction >= .005:
                    tiles.append({'uri':content['uri'], 'region':region, 'greenFraction':green_fraction, 'duneFraction':dune_fraction})
        for child in tile.get('children', []):
            visit(child)
    visit(native['root'])
    tiles.sort(key=lambda tile:(-bool(tile['duneFraction']>=.005), -tile['greenFraction']))
    return tiles, inventory


latitude, longitude = np.deg2rad([51.915,4.49])
east = np.array([-np.sin(longitude), np.cos(longitude), 0])
up = np.array([np.cos(latitude)*np.cos(longitude), np.cos(latitude)*np.sin(longitude), np.sin(latitude)])
north = np.cross(up, east)
south = -north
geo_to_earth = Transformer.from_crs(4979, 4978, always_xy=True)
earth_to_geo = Transformer.from_crs(4978, 4979, always_xy=True)
origin = np.array(geo_to_earth.transform(4.49,51.915,0))


def surface_kind(attributes):
    category = attributes.get('KLASSE_IMG','').lower()
    classification = attributes.get('KLASSE','').lower()
    purpose = attributes.get('FUNCTIE','').lower()
    physical = attributes.get('FYSIEKVK','').lower()
    if any(word in classification for word in ['kade','muur']): return None
    if category == 'begroeid terreindeel': return 'green'
    if 'zand' in physical or classification == 'zand': return 'sand'
    if category == 'wegdeel' and ('voet' in purpose or 'ruiter' in purpose): return 'footway'
    if category == 'wegdeel' and 'fiets' in purpose: return 'cycleway'
    if category == 'wegdeel' and 'rijbaan' in purpose: return 'road'
    return None


def decode_surfaces(raw):
    _, _, _, feature_length, feature_binary, batch_length, batch_binary = struct.unpack_from('<4s6I',raw)
    feature_table = json.loads(raw[28:28+feature_length])
    batch = json.loads(raw[28+feature_length+feature_binary:28+feature_length+feature_binary+batch_length])
    glb = raw[28+feature_length+feature_binary+batch_length+batch_binary:]
    json_length = struct.unpack_from('<I',glb,12)[0]
    document = json.loads(glb[20:20+json_length])
    binary = glb[28+json_length:]
    rtc = feature_table.get('RTC_CENTER') or document.get('extensions',{}).get('CESIUM_RTC',{}).get('center') or [0,0,0]
    def accessor(index):
        description = document['accessors'][index]
        view = document['bufferViews'][description['bufferView']]
        data_type = {5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'}[description['componentType']]
        components = {'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[description['type']]
        size = np.dtype(data_type).itemsize
        return np.ndarray((description['count'],components),dtype=data_type,buffer=binary,offset=view.get('byteOffset',0)+description.get('byteOffset',0),strides=(view.get('byteStride',size*components),size)).copy()
    surfaces = defaultdict(list)
    counts = defaultdict(int)
    dates = set()
    sentinel = 0
    interpolated_invalid = 0
    vertical_skirts = 0
    def visit(index, parent):
        nonlocal sentinel, interpolated_invalid, vertical_skirts
        node = document['nodes'][index]
        matrix = parent @ np.array(node.get('matrix',np.eye(4).flatten(order='F'))).reshape((4,4),order='F')
        if 'mesh' in node:
            for primitive in document['meshes'][node['mesh']]['primitives']:
                if primitive.get('mode',4)!=4: continue
                positions = accessor(primitive['attributes']['POSITION'])
                earth = (np.c_[positions,np.ones(len(positions))] @ matrix.T)[:,:3]+rtc
                lon,lat,height = earth_to_geo.transform(*earth.T)
                local = np.column_stack(((earth-origin)@east,(earth-origin)@up,(earth-origin)@south))
                indices = accessor(primitive['indices']).flatten().astype(int).reshape(-1,3)
                batch_ids = accessor(primitive['attributes']['_BATCHID']).flatten().astype(int)
                inside = contains_xy(municipality,lon,lat)
                source_heights = height[indices]
                missing = np.isclose(source_heights, -99.99, atol=.05, rtol=0).any(axis=1)
                # Reviewed source artifacts contain -99.99 and intermediate
                # -50/-66 m skirt ramps. This is a source repair, not a datum shift.
                invalid = (source_heights < -30).any(axis=1)
                sentinel += int(missing.sum())
                interpolated_invalid += int((invalid & ~missing).sum())
                plan = np.column_stack(((lon-lon[0])*111320*np.cos(np.deg2rad(np.mean(lat))), (lat-lat[0])*111320))[indices]
                edges = np.roll(plan,-1,axis=1)-plan
                longest = np.linalg.norm(edges,axis=2).max(axis=1)
                twice_area = np.abs(edges[:,0,0]*edges[:,1,1]-edges[:,0,1]*edges[:,1,0])
                altitude = twice_area/np.maximum(longest,1e-12)
                skirts = (altitude < .05) & (np.ptp(source_heights,axis=1)>1)
                vertical_skirts += int((skirts & ~invalid).sum())
                valid = ~invalid & ~skirts
                # Partial boundary triangles are omitted rather than stretched across
                # municipal water or adjacent territory. Their original edges survive.
                valid &= inside[indices].all(axis=1)
                for batch_id in np.unique(batch_ids[indices[:,0]]):
                    attributes = batch['attributes'][batch_id]
                    kind = surface_kind(attributes)
                    if not kind: continue
                    selected = indices[valid & (batch_ids[indices[:,0]]==batch_id)]
                    if len(selected):
                        surfaces[kind].append(local[selected])
                        counts[kind] += 1
                        if attributes.get('INWIN'): dates.add(attributes['INWIN'])
        for child in node.get('children',[]): visit(child,matrix)
    y_up_to_z_up = np.array([[1,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1]],dtype=float)
    for index in document['scenes'][document.get('scene',0)]['nodes']: visit(index,y_up_to_z_up)
    return {kind:np.concatenate(parts) for kind,parts in surfaces.items()},dict(counts),sorted(dates),{'sentinel':sentinel,'interpolatedInvalid':interpolated_invalid,'verticalSkirts':vertical_skirts}


def boundary_edges(indices):
    edges = np.sort(np.concatenate([indices[:,[0,1]],indices[:,[1,2]],indices[:,[2,0]]]),axis=1)
    unique,counts = np.unique(edges,axis=0,return_counts=True)
    return unique[counts==1]


def compact_geometry(triangles):
    positions, inverse = np.unique(triangles.reshape(-1,3).astype(np.float32),axis=0,return_inverse=True)
    indices = inverse.reshape(-1,3)
    boundary = boundary_edges(indices)
    locked = np.unique(boundary)
    interior = np.setdiff1d(np.arange(len(positions)),locked,assume_unique=True)
    mapping = np.arange(len(positions))
    if len(interior):
        cells = np.floor(positions[interior]/[2,.25,2]).astype(np.int64)
        _,representatives,groups = np.unique(cells,axis=0,return_index=True,return_inverse=True)
        mapping[interior] = interior[representatives[groups]]
    # Undo only clusters that introduce an open edge or reverse a source face.
    # This leaves useful interior reduction in place while preserving actual holes.
    safe = False
    for attempt in range(12):
        simplified = mapping[indices]
        keep = (simplified[:,0]!=simplified[:,1]) & (simplified[:,1]!=simplified[:,2]) & (simplified[:,2]!=simplified[:,0])
        simplified = simplified[keep]
        original_normals = np.cross(positions[indices[keep,1]]-positions[indices[keep,0]],positions[indices[keep,2]]-positions[indices[keep,0]])[:,1]
        simplified_normals = np.cross(positions[simplified[:,1]]-positions[simplified[:,0]],positions[simplified[:,2]]-positions[simplified[:,0]])[:,1]
        inverted = (original_normals*simplified_normals<0) | ((np.abs(original_normals)>1e-8)&(np.abs(simplified_normals)<1e-8))
        new_boundary = boundary_edges(simplified)
        if np.array_equal(new_boundary,boundary) and not inverted.any():
            safe = True
            break
        boundary_set = {tuple(edge)for edge in boundary}
        added_edges = np.array([edge for edge in new_boundary if tuple(edge)not in boundary_set],dtype=int)
        bad_vertices = np.unique(np.concatenate([added_edges.flatten(),simplified[inverted].flatten()]))
        affected = np.isin(mapping,bad_vertices)
        mapping[affected] = np.flatnonzero(affected)
    if not safe:
        mapping = np.arange(len(positions)); simplified = indices
    displacement = np.abs(positions[mapping]-positions)
    used,remap = np.unique(simplified,return_inverse=True)
    return positions[used],remap.reshape(-1,3),{'sourceTriangles':len(indices),'triangles':len(simplified),'boundaryPreserved':True,'clusterApplied':bool(safe),'maximumHorizontalDisplacement':float(np.linalg.norm(displacement[:,[0,2]],axis=1).max()),'maximumVerticalDisplacement':float(displacement[:,1].max())}


def encode_tile(surfaces):
    document = {'asset':{'version':'2.0','generator':'010 measured green terrain'},'scene':0,'scenes':[{'nodes':[]}],'nodes':[],'meshes':[],'accessors':[],'bufferViews':[],'buffers':[{'byteLength':0}],'extensionsUsed':['KHR_mesh_quantization'],'extensionsRequired':['KHR_mesh_quantization']}
    chunks=[]; length=0; statistics={}; all_positions=[]
    def accessor(array,component_type,kind,target,bounds=None):
        nonlocal length
        padding=(-length)%4
        if padding: chunks.append(bytes(padding)); length+=padding
        raw=array.tobytes()
        stride=None
        if kind=='VEC3' and component_type==5123:
            padded=np.zeros((len(array),4),dtype='<u2');padded[:,:3]=array;raw=padded.tobytes();stride=8
        document['bufferViews'].append({'buffer':0,'byteOffset':length,'byteLength':len(raw),'target':target,**({'byteStride':stride}if stride else {})})
        document['accessors'].append({'bufferView':len(document['bufferViews'])-1,'componentType':component_type,'count':len(array),'type':kind,**(bounds or {})})
        chunks.append(raw);length+=len(raw)
        return len(document['accessors'])-1
    for kind,triangles in surfaces.items():
        positions,indices,statistics[kind]=compact_geometry(triangles)
        minimum=positions.min(axis=0);maximum=positions.max(axis=0);steps=(maximum-minimum)/65535;steps[steps==0]=1/65535
        encoded=np.rint((positions-minimum)/steps).astype('<u2')
        position_accessor=accessor(encoded,5123,'VEC3',34962,{'min':encoded.min(axis=0).tolist(),'max':encoded.max(axis=0).tolist()})
        indices=indices.flatten();indices=indices.astype('<u2' if len(positions)<65536 else '<u4')
        index_accessor=accessor(indices,5123 if indices.dtype.itemsize==2 else 5125,'SCALAR',34963)
        document['meshes'].append({'name':kind,'extras':{'surfaceKind':kind,'sourceStage':'measured municipal BGT terrain'},'primitives':[{'attributes':{'POSITION':position_accessor},'indices':index_accessor,'mode':4}]})
        document['nodes'].append({'mesh':len(document['meshes'])-1,'translation':minimum.tolist(),'scale':steps.tolist()});document['scenes'][0]['nodes'].append(len(document['nodes'])-1)
        statistics[kind]['maximumQuantizationErrorMetres']=float(np.linalg.norm(steps)/2)
        all_positions.append(positions)
    binary=b''.join(chunks);binary+=bytes((-len(binary))%4);document['buffers'][0]['byteLength']=len(binary)
    metadata=json.dumps(document,separators=(',',':')).encode();metadata+=b' '*((-len(metadata))%4)
    glb=struct.pack('<4sII',b'glTF',2,28+len(metadata)+len(binary))+struct.pack('<I4s',len(metadata),b'JSON')+metadata+struct.pack('<I4s',len(binary),b'BIN\0')+binary
    positions=np.concatenate(all_positions);minimum=positions.min(axis=0);maximum=positions.max(axis=0);centre=(minimum+maximum)/2;half=(maximum-minimum)/2
    bounds=[float(centre[0]),float(-centre[2]),float(centre[1]),float(half[0]),0,0,0,float(half[2]),0,0,0,float(half[1])]
    return glb,statistics,bounds


def cache_source(url):
    _, metadata = acquire(url)
    return metadata


def main():
    tiles,inventory=selected_tiles()
    print(f'Selected {len(tiles)} source tiles',flush=True)
    records=[];omissions=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures={tile['uri']:executor.submit(cache_source,BASE+tile['uri']) for tile in tiles}
        for number,tile in enumerate(tiles):
            try:
                source=futures.pop(tile['uri']).result()
                raw,_=acquire(BASE+tile['uri'])
                surfaces,counts,dates,repair_counts=decode_surfaces(raw)
                if not surfaces:
                    omissions.append({'uri':tile['uri'],'reason':'No eligible measured surfaces after invalid-height and municipal-boundary filtering'});continue
                glb,statistics,bounds=encode_tile(surfaces)
                name=tile['uri'].replace('/','_').replace('.b3dm','.glb')
                (OUTPUT/name).write_bytes(glb)
                records.append({'uri':name,'source':source,'selection':tile,'sourceFeatureCounts':counts,'sourceRecordDates':dates,'invalidHeightTrianglesOmitted':repair_counts['sentinel']+repair_counts['interpolatedInvalid'],'sourceSentinelTrianglesOmitted':repair_counts['sentinel'],'invalidHeightInterpolantTrianglesOmitted':repair_counts['interpolatedInvalid'],'verticalSourceSkirtTrianglesOmitted':repair_counts['verticalSkirts'],'geometry':statistics,'bytes':len(glb),'box':bounds})
                print(f'{number+1}/{len(tiles)} {name}: {len(glb):,} bytes',flush=True)
            except Exception as error:
                omissions.append({'uri':tile['uri'],'reason':str(error)});print('OMITTED',tile['uri'],str(error),flush=True)
    current_assets = {record['uri']for record in records}
    obsolete = CACHE/'obsolete-assets'
    for asset in OUTPUT.glob('*.glb'):
        if asset.name not in current_assets:
            obsolete.mkdir(exist_ok=True)
            asset.replace(obsolete/asset.name)
    matrix=np.eye(4);matrix[:3,0]=east;matrix[:3,1]=north;matrix[:3,2]=up;matrix[:3,3]=origin
    children=[{'boundingVolume':{'box':record['box']},'geometricError':0,'content':{'uri':record['uri']}}for record in records]
    tileset={'asset':{'version':'1.1'},'geometricError':100000,'root':{'transform':matrix.flatten(order='F').tolist(),'boundingVolume':{'box':[-15000,0,30,30000,0,0,0,15000,0,0,0,200]},'geometricError':100000,'refine':'ADD','children':children}}
    (OUTPUT/'tileset.json').write_text(json.dumps(tileset,separators=(',',':'))+'\n')
    manifest={'writtenBy':'AI, GPT-6, 2026-10-24','sourceInventory':inventory,'selection':'Surveyed BRT forest/grass/heath/dune/sand covers >=40% of municipal part of source tile OR dunes >=0.5%; source bounds must contain valid elevations. Only native green/sand/footway/cycleway/road surfaces retained.','geometry':'Original measured source heights; source-specific invalid terrain heights below -30 m omitted (exact missing sentinel and interpolated source ramps counted separately). Near-zero-plan-area vertical edge curtains also omitted; actual kade/muur and structural classes are not selected. Interior-only clustering 2 m horizontal / 0.25 m vertical; original boundary edges and face orientation checked, otherwise exact indexed source retained. Standard glTF quantization.','repairCountScope':'All decoded source triangles in emitted tiles, before semantic and municipal selection; sentinel means within 5 cm of -99.99 m after coordinate decoding.', 'sourceRepair':'Model-reviewed interpretation for this source, not a publisher-specified validity contract: 2D green/sand/path/road heights below -30 m are missing-height extrusion artifacts in the examined coast/port records. Near-zero-plan-area faces (minimum horizontal altitude <0.05 m and height range >1 m) are source edge curtains. Original cached bytes are unchanged; ordinary negative terrain is retained.',
        'boundary':'Only triangles whose three vertices are inside exact municipality retained; intersecting boundary triangles omitted, never stretched. Source water holes remain empty.','datesAndLimits':'Upstream ground edition dates observed 2017–2019. Inventory HTTP Last-Modified is a file date, retained in sourceInventory, not a survey date. Individual BGT acquisition dates differ and are recorded per tile; not a current terrain survey. No photographic textures. Native source may contain errors or missing elevations.','license':'Municipal Rotterdam 3D public domain, credit Gemeente Rotterdam; BRT/municipal boundary CC BY 4.0 Kadaster / PDOK.','selectedTiles':len(tiles),'tiles':records,'omissions':omissions}
    (OUTPUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'tiles':len(records),'omissions':len(omissions),'bytes':sum(r['bytes']for r in records),'triangles':sum(g['triangles']for r in records for g in r['geometry'].values()),'sourceTriangles':sum(g['sourceTriangles']for r in records for g in r['geometry'].values())}),flush=True)

if __name__=='__main__':main()
