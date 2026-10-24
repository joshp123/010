#!/usr/bin/env python3
"""Supplement native lamp coverage with surveyed BGT light-mast points.
Written by AI on 2026-10-24 by model GPT-6.1 Sol.
Run with the project's devenv Python; --acquire refreshes the retained snapshot.
"""
import argparse, concurrent.futures, gzip, hashlib, json, math, struct
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
import numpy as np
from pyproj import Transformer
from scipy.spatial import cKDTree
from shapely.geometry import shape
from PIL import Image
from shapely.ops import transform, unary_union

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'work/data-cache/supplementary-lamps'
SOURCE = ROOT / 'source-data/supplementary-lamps.geojson.gz'
OUTPUT = ROOT / 'public/data/supplementary-lamps'
SNAPSHOT = '2026-10-24T00:00:00Z'
API = 'https://api.pdok.nl/kadaster/bgt/ogc/v1/collections/paal/items'
ORIGIN = (4.49, 51.915, 0)
GEOCENTRIC = Transformer.from_crs(4979, 4978, always_xy=True)
latitude, longitude = map(math.radians, [ORIGIN[1], ORIGIN[0]])
east = [-math.sin(longitude), math.cos(longitude), 0]
up = [math.cos(latitude)*math.cos(longitude), math.cos(latitude)*math.sin(longitude), math.sin(latitude)]
south = [math.sin(latitude)*math.cos(longitude), math.sin(latitude)*math.sin(longitude), -math.cos(latitude)]
ROTATION = np.array([east, up, south])
EARTH_ORIGIN = np.array(GEOCENTRIC.transform(*ORIGIN))

def packed(value):
    return (json.dumps(value, separators=(',', ':'), ensure_ascii=False)+'\n').encode()

def acquire_strip(bounds):
    url = API + '?' + urlencode({'bbox': ','.join(map(str,bounds)), 'plus_type':'lichtmast', 'datetime':SNAPSHOT,'limit':1000,'f':'json'})
    features, inventory = [], []
    while url:
        path = CACHE/(hashlib.sha256(url.encode()).hexdigest()+'.json')
        if not path.exists():
            with urlopen(url, timeout=90) as response: data = response.read()
            json.loads(data)
            path.write_bytes(data)
        data = path.read_bytes(); page = json.loads(data)
        features.extend(page['features'])
        inventory.append({'url':url,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'acquiredAt':datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat()})
        print(f'{bounds[0]:.3f}: {len(features)} records', flush=True)
        url = next((link['href'] for link in page['links'] if link['rel']=='next'), None)
    return features, inventory

def native_bases():
    positions=[]
    for path in sorted((ROOT/'public/data/lamps').glob('*.glb')):
        content=path.read_bytes(); json_size=struct.unpack_from('<I',content,12)[0]
        document=json.loads(content[20:20+json_size]); binary=content[28+json_size:]
        accessor=document['accessors'][0]; view=document['bufferViews'][accessor['bufferView']]
        matrix_node=document['nodes'][0]
        for index in range(0,accessor['count'],2):
            q=struct.unpack_from('<HHH',binary,view.get('byteOffset',0)+index*view['byteStride'])
            positions.append([matrix_node['translation'][axis]+q[axis]*matrix_node['scale'][axis] for axis in range(3)])
    return np.array(positions)

def box(vertices):
    low=vertices.min(axis=0); high=vertices.max(axis=0); centre=(low+high)/2; half=(high-low)/2
    return [centre[0],-centre[2],centre[1],max(half[0],.1),0,0,0,max(half[2],.1),0,0,0,max(half[1],.1)]

def encode(records):
    # Float32 relative positions preserve surveyed plan coordinates to <1 mm.
    points=np.array([p for record in records for p in record['points']]); centre=points.mean(axis=0)
    positions=(points-centre).astype('<f4'); count=len(records)
    binary=positions.tobytes()
    accessors=[{'bufferView':0,'componentType':5126,'count':len(points),'type':'VEC3','min':positions.min(axis=0).tolist(),'max':positions.max(axis=0).tolist()}]
    views=[{'buffer':0,'byteOffset':0,'byteLength':len(binary),'target':34962}]
    meshes=[]; nodes=[]
    for kind,indices,mode in [('lampShafts',list(range(count*2)),1),('lampHeads',list(range(1,count*2,2)),0),('lampPools',[i*2 for i,r in enumerate(records) if r['pool']],0)]:
        if not indices: continue
        values=np.array(indices,dtype='<u4').tobytes(); offset=len(binary);binary+=values
        views.append({'buffer':0,'byteOffset':offset,'byteLength':len(values),'target':34963})
        accessors.append({'bufferView':len(views)-1,'componentType':5125,'count':len(indices),'type':'SCALAR'})
        meshes.append({'name':kind,'extras':{'objectKind':kind,'illustratedPole':True,'sourceIds':[r['id'] for r in records],'placement':'BGT 2D surveyed point; height and emitted light are illustrative'},'primitives':[{'attributes':{'POSITION':0},'indices':len(accessors)-1,'mode':mode}]})
        nodes.append({'mesh':len(meshes)-1,'translation':centre.tolist()})
    document={'asset':{'version':'2.0','generator':'010 supplementary BGT lamps'},'scene':0,'scenes':[{'nodes':list(range(len(nodes)))}],'nodes':nodes,'meshes':meshes,'accessors':accessors,'bufferViews':views,'buffers':[{'byteLength':len(binary)}]}
    js=packed(document);js+=b' '*((-len(js))%4);binary+=b'\0'*((-len(binary))%4)
    return struct.pack('<4sII',b'glTF',2,28+len(js)+len(binary))+struct.pack('<II',len(js),0x4e4f534a)+js+struct.pack('<II',len(binary),0x004e4942)+binary, points

def main(acquire):
    municipality=shape(json.loads((ROOT/'public/data/municipality.geojson').read_bytes())['features'][0]['geometry'])
    if acquire:
        CACHE.mkdir(parents=True,exist_ok=True)
        west,south_bound,east_bound,north=municipality.bounds
        edges=np.linspace(west,east_bound,9)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as workers:
            responses=list(workers.map(acquire_strip,[(edges[i],south_bound,edges[i+1],north) for i in range(8)]))
        selected={}
        for features,_ in responses:
            for feature in features:
                prop=feature['properties']
                if prop['status']=='bestaand' and not prop.get('termination_date') and not prop.get('eind_registratie') and municipality.covers(shape(feature['geometry'])):
                    selected[feature['id']]=feature
        source={'type':'FeatureCollection','writtenBy':'AI, GPT-6, 2026-10-24','publisher':'Kadaster / PDOK / BGT source holders','license':'CC0-1.0','licenseUrl':'https://creativecommons.org/publicdomain/zero/1.0/','snapshot':SNAPSHOT,'inventory':[item for _,inventory in responses for item in inventory],'features':sorted(selected.values(),key=lambda f:f['id'])}
        SOURCE.write_bytes(gzip.compress(packed(source),mtime=0))
    source=json.loads(gzip.decompress(SOURCE.read_bytes()))
    fixtures=source['features']; coords=np.array([f['geometry']['coordinates'] for f in fixtures])
    x,y,z=GEOCENTRIC.transform(coords[:,0],coords[:,1],np.zeros(len(coords)))
    bases=(np.array([x,y,z]).T-EARTH_ORIGIN)@ROTATION.T
    native=native_bases(); distances,nearest=cKDTree(native[:,[0,2]]).query(bases[:,[0,2]])
    print('Nearest-native histogram:',np.histogram(distances,bins=[0,.1,.25,.5,1,2,5,10,50,100,1e9])[0].tolist(),flush=True)
    # Native/BGT surveyed bases overwhelmingly coincide within 10 cm. This
    # exceeds prepared quantization error while preserving nearby distinct poles.
    # BRT water polygons retained by the existing lamp build; reuse exact sources.
    lamp_manifest=json.loads((ROOT/'public/data/lamps/manifest.json').read_bytes())
    water_features=[]
    for item in lamp_manifest['pools']['surveyInventory']:
        path=ROOT/'work/data-cache'/(hashlib.sha256(item['url'].encode()).hexdigest()+'.json')
        water_features.extend(json.loads(path.read_bytes())['features'])
    to_rd=Transformer.from_crs(4326,28992,always_xy=True).transform
    land=transform(to_rd,municipality).difference(unary_union([transform(to_rd,shape(f['geometry'])) for f in water_features])).buffer(-9.1)
    # Ground uses the same free AHN DTM edition/height convention as structures.
    ahn_index=json.loads((ROOT/'work/data-cache/industrial-structures/ahn6-copc-index.json').read_bytes())
    ahn_tiles={tuple(map(lambda value:math.floor(value/1000),shape(f['geometry']).bounds[:2])):f for f in ahn_index['features']}
    ground_groups={}; excluded=0; elevated=[]
    for feature,base,distance in zip(fixtures,bases,distances):
        if distance <= .1: excluded+=1;continue
        if feature['properties'].get('relatieve_hoogteligging')!=0:
            elevated.append(feature['id']);continue
        rd=to_rd(*feature['geometry']['coordinates']);key=(math.floor(rd[0]/1000),math.floor(rd[1]/1000))
        ground_groups.setdefault(key,[]).append((feature,base,rd))
    buckets={}; ground_inventory=[];unresolved=[]
    for key,entries in sorted(ground_groups.items()):
        tile=ahn_tiles.get(key)
        if not tile:
            unresolved.extend(f['id'] for f,_,_ in entries);continue
        name=Path(tile['properties']['file']).name.replace('_C_','_M_').replace('.COPC.LAZ','.TIF')
        url='https://fsn1.your-objectstorage.com/hwh-ahn/AHN6/02a_DTM_50cm/'+name
        path=ROOT/'work/data-cache/industrial-structures'/name
        if not path.exists():
            with urlopen(url,timeout=120) as response:data=response.read()
            path.write_bytes(data)
        raw=path.read_bytes()
        ground_inventory.append({'url':url,'cache':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'acquiredAt':datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat()})
        with Image.open(path) as image:
            ground=np.asarray(image);left,top=image.tag_v2[33922][3:5];cell=image.tag_v2[33550][0]
            for feature,base,rd in entries:
                row=int(math.floor((top-rd[1])/cell));column=int(math.floor((rd[0]-left)/cell))
                # A pole footprint may be a no-data cell. Find nearest valid
                # terrain within 2m; record omission when there is no measurement.
                window=ground[max(0,row-4):row+5,max(0,column-4):column+5]
                valid=window[(window!=-9999)&np.isfinite(window)]
                if not len(valid):unresolved.append(feature['id']);continue
                height=float(ground[row,column])
                if height==-9999 or not math.isfinite(height):height=float(np.median(valid))
                bottom=base.copy();bottom[1]+=height+.08
                top_point=bottom.copy();top_point[1]+=10
                pool=land.covers(transform(to_rd,shape(feature['geometry'])))
                bucket_key=f'{math.floor(base[0]/2000)}_{math.floor(base[2]/2000)}'
                buckets.setdefault(bucket_key,[]).append({'id':feature['id'],'points':[bottom.tolist(),top_point.tolist()],'pool':pool})
        print(f'ground {name}: {len(entries)} fixtures',flush=True)
    OUTPUT.mkdir(parents=True,exist_ok=True)
    children=[];all_points=[];total=0;tiles=[]
    for key,records in sorted(buckets.items()):
        glb,points=encode(records);(OUTPUT/f'{key}.glb').write_bytes(glb);all_points.extend(points.tolist());total+=len(glb)
        children.append({'boundingVolume':{'box':box(points)},'geometricError':0,'content':{'uri':f'{key}.glb'}})
        tiles.append({'uri':f'{key}.glb','fixtures':len(records),'pools':sum(r['pool'] for r in records),'bytes':len(glb)})
    transform_values=[*east,0,*[-v for v in south],0,*up,0,*EARTH_ORIGIN.tolist(),1]
    tileset={'asset':{'version':'1.0','gltfUpAxis':'Y'},'geometricError':1000000,'root':{'transform':transform_values,'boundingVolume':{'box':box(np.array(all_points))},'geometricError':1000000,'refine':'REPLACE','children':children}}
    (OUTPUT/'tileset.json').write_bytes(packed(tileset))
    manifest={'writtenBy':'AI, GPT-6, 2026-10-24','source':'../../../source-data/supplementary-lamps.geojson.gz','sourceSha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'publisher':source['publisher'],'license':source['license'],'licenseUrl':source['licenseUrl'],'snapshot':SNAPSHOT,'sourceFixtures':len(fixtures),'excludedMatchingNativeBases':excluded,'includedFixtures':sum(len(records) for records in buckets.values()),'unresolvedGroundFixtureIds':unresolved,'omittedElevatedFixtureIds':elevated,'groundLicense':'CC BY 4.0','groundAttribution':'Actueel Hoogtebestand Nederland (AHN)' ,'groundSources':ground_inventory,'groundIndexSha256':hashlib.sha256((ROOT/'work/data-cache/industrial-structures/ahn6-copc-index.json').read_bytes()).hexdigest(),'nativeLampManifestSha256':hashlib.sha256((ROOT/'public/data/lamps/manifest.json').read_bytes()).hexdigest(),'bucketMetres':2000,'bytes':total,'tiles':tiles,'interpretation':{'positions':'BGT paal plus_type=lichtmast 2D coordinates, existing status, exact municipality clip','coverage':'Exclude only surveyed plan points within 0.1m of a native prepared pole base. This bound exceeds <=2cm/axis native-output quantization error; the observed nearest-neighbour distribution is retained below. Distinct nearby points are preserved beyond this match bound.','height':'Ground is sampled from retained AHN6 0.5m DTM, nearest-cell height or median valid cell within 2m for no-data. No valid ground means omission. Same NAP numeric/Earth-curvature convention as other model layers. Head height is illustrative 10m above measured ground; BGT does not survey mast heights.','light':'Warm head glow and 9m light pools use existing lamp materials; pools only if full footprint lies inside municipality and outside unsimplified BRT water polygons. Pole heads/pools are illustration, not live operational status.','nearestNativeHistogram':np.histogram(distances,bins=[0,.1,.25,.5,1,2,5,10,50,100,1e9])[0].tolist(),'nearestNativeBinsMetres':[0,.1,.25,.5,1,2,5,10,50,100,1e9]}}
    (OUTPUT/'manifest.json').write_bytes(packed(manifest));print(json.dumps({k:v for k,v in manifest.items() if k not in ['tiles','interpretation']},indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--acquire',action='store_true');main(parser.parse_args().acquire)
