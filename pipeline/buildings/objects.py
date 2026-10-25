"""Municipal tree/lamp instance extraction. Written by AI, GPT-6, 2026-10-25."""
import argparse, collections, datetime, gzip, hashlib, json, math, struct
from pathlib import Path
from urllib.parse import urljoin
import numpy as np
import requests
from pyproj import Transformer

ROOT = Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
DATASETS = {'trees': 'b9294d5b-79e0-4744-ac88-b61e3e90d5bc', 'lamps': '2602863a-3d22-44c2-8c95-bbf88a20bf37'}
CORE = (89750,435750,90750,436750)
M0 = (89750,435250,92000,436750)

def decoded(raw):
    return gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw

class Archive:
    def __init__(self, dataset):
        self.directory = ROOT/'sources'/dataset/datetime.date.today().isoformat()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.files = {}
        manifest = self.directory/'manifest.json'
        if manifest.exists():
            self.files = {f['path']:f for f in json.loads(manifest.read_text())['files']}
        self.base = 'https://www.3drotterdam.nl/datasource-data/'+DATASETS[dataset]+'/'
        self.dataset=dataset
    def get(self, url):
        relative = url.removeprefix(self.base)
        if relative.startswith('http') or '..' in Path(relative).parts:
            relative='external/'+hashlib.sha256(url.encode()).hexdigest()+Path(url).suffix
        path=self.directory/relative
        if not path.exists():
            response=requests.get(url, timeout=120); response.raise_for_status()
            path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(response.content)
            self.files[relative]={'path':relative,'url':url,'sha256':hashlib.sha256(response.content).hexdigest(),'bytes':len(response.content),'fetched_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
            self.save()
        return decoded(path.read_bytes())
    def save(self):
        (self.directory/'manifest.json').write_text(json.dumps({'dataset':self.dataset,'licence':'Public domain','credit':'Gemeente Rotterdam','source':'https://www.rotterdam.nl/rotterdam-in-3d','files':sorted(self.files.values(),key=lambda x:x['path'])},indent=2)+'\n')

def select_contents(tileset,bounds):
    to_ll=Transformer.from_crs(28992,4326,always_xy=True)
    xs,ys=to_ll.transform([bounds[0],bounds[0],bounds[2],bounds[2]],[bounds[1],bounds[3],bounds[1],bounds[3]])
    area=(math.radians(min(xs)), math.radians(min(ys)),math.radians(max(xs)),math.radians(max(ys)))
    def visit(node, matrix):
        if 'transform' in node: matrix=matrix@np.array(node['transform']).reshape(4,4,order='F')
        r=node['boundingVolume'].get('region')
        if r and (r[2]<area[0] or r[0]>area[2] or r[3]<area[1] or r[1]>area[3]): return
        children=node.get('children',[])
        if children:
            # ADD nodes contain additional distinct objects; REPLACE parents are coarser versions.
            if node.get('refine','REPLACE')=='ADD' and 'content' in node: yield node['content']['uri'],matrix
            for child in children: yield from visit(child,matrix)
        elif 'content' in node: yield node['content']['uri'],matrix
    return list(visit(tileset['root'],np.eye(4)))

def parts(data):
    if data[:4]==b'cmpt':
        at=16
        for _ in range(struct.unpack_from('<I',data,12)[0]):
            size=struct.unpack_from('<I',data,at+8)[0]
            yield from parts(data[at:at+size]);at+=size
    else: yield data

def read_instances(data):
    """Read 3D Tiles 1.0 instance positions and property rows, without mesh inference."""
    header=struct.unpack_from('<8I',data)
    feature_table=json.loads(data[32:32+header[3]])
    binary=data[32+header[3]:32+header[3]+header[4]]
    at=32+header[3]+header[4]
    batch_table=json.loads(data[at:at+header[5]])
    at+=header[5]+header[6]
    count=feature_table['INSTANCES_LENGTH']
    if 'POSITION_QUANTIZED' in feature_table:
        positions=np.frombuffer(binary,dtype='<u2',count=count*3,offset=feature_table['POSITION_QUANTIZED']['byteOffset']).reshape(-1,3).astype(float)
        positions=positions/65535*np.array(feature_table['QUANTIZED_VOLUME_SCALE'])+np.array(feature_table['QUANTIZED_VOLUME_OFFSET'])
    else:
        positions=np.frombuffer(binary,dtype='<f4',count=count*3,offset=feature_table['POSITION']['byteOffset']).reshape(-1,3).astype(float)
    positions+=np.array(feature_table.get('RTC_CENTER',[0,0,0]))
    if 'BATCH_ID' in feature_table:
        property_spec=feature_table['BATCH_ID']
        dtype={'UNSIGNED_BYTE':'u1','UNSIGNED_SHORT':'<u2','UNSIGNED_INT':'<u4'}[property_spec.get('componentType','UNSIGNED_SHORT')]
        batches=np.frombuffer(binary,dtype=dtype,count=count,offset=property_spec['byteOffset'])
    else: batches=np.arange(count)
    model=data[at:].decode().strip(' \0') if header[7]==0 else None
    rows=[(positions[i],str(batch_table['id'][int(batches[i])]),batch_table['attributes'][int(batches[i])]) for i in range(count)]
    return rows,model

def build(area='core'):
    from transform import ecef_to_rdnap
    transform=ecef_to_rdnap(preserve_source_height=False)
    geodetic=Transformer.from_crs(4978,4979,always_xy=True)
    bounds=CORE if area=='core' else M0
    tiles={f'x{x}_y{y}':{'trees':[],'lamps':[]} for x in range(bounds[0],bounds[2],250) for y in range(bounds[1],bounds[3],250)}
    summary={'area':area,'bounds_rd':bounds,'datasets':{},'method':{
        'trees':'One record per Boom_id from tree_part=stam. height_m=height and crown_m=crownDiameter, municipal attributes, not mesh estimates.',
        'lamps':'One mast per Beheerobject and source base position within 0.05m (source quantization), maximum Montagehoogte across fixtures. height_m is source mounting height, not surveyed highest hardware extent.',
        'positions':'i3dm POSITION_QUANTIZED decoded in ECEF, inherited tile transform, horizontal RD New via real NSGI grids. Source ECEF encodes NAP as ellipsoid height: retain decoded geodetic h as NAP z. Verified on 2640 core trunk records against explicit Hoogte: max discrepancy 0.0091m. No guessed dimensions.'}}
    for dataset in DATASETS:
        archive=Archive(dataset)
        selected=select_contents(json.loads(archive.get(archive.base+'tileset.json')),bounds)
        unique={}; lamp_groups=collections.defaultdict(list); duplicate_count=0; ignored_parts=0; missing_dimensions=[]; zero_dimensions=[]; height_diagnostic=[]
        for uri,matrix in selected:
            url=archive.base+uri
            for part_index,part in enumerate(parts(archive.get(url))):
                if part[:4] != b'i3dm': raise ValueError(f'Unexpected object tile format {part[:4]}: {uri}')
                rows,model=read_instances(part)
                if model: archive.get(urljoin(url,model))
                positions=np.array([r[0] for r in rows]); positions=(matrix@np.column_stack([positions,np.ones(len(positions))]).T).T[:,:3]
                rd=np.array(transform.transform(positions[:,0],positions[:,1],positions[:,2])).T
                geodetic_height=geodetic.transform(positions[:,0],positions[:,1],positions[:,2])[2]
                if len(height_diagnostic)<5:
                    height_diagnostic.append({'source_tile':uri,'source_id':rows[0][1],'ecef':positions[0].tolist(),'encoded_geodetic_h_m':float(geodetic_height[0]),'unadjusted_geoid_conversion_z_m':float(rd[0,2]),'source_Hoogte':rows[0][2].get('Hoogte')})
                rd[:,2]=geodetic_height
                for i,((_,source_id,attributes),point) in enumerate(zip(rows,rd)):
                    x,y,z=map(float,point)
                    if not (bounds[0]<=x<bounds[2] and bounds[1]<=y<bounds[3]): continue
                    if dataset=='trees' and attributes.get('tree_part')!='stam':
                        ignored_parts+=1;continue
                    height=attributes.get('height' if dataset=='trees' else 'Montagehoogte')
                    crown=attributes.get('crownDiameter')
                    if height is None or (dataset=='trees' and crown is None):
                        missing_dimensions.append(source_id);continue
                    if float(height)<=0 or (dataset=='trees' and float(crown)<=0):zero_dimensions.append(source_id)
                    record={'x':round(x,4),'y':round(y,4),'z':round(z,4),'height_m':float(height),'source_id':source_id,'source':{'dataset':dataset,'tile':uri,'part':part_index,'instance':i,'creation_date':attributes.get('creationDate')}}
                    if dataset=='trees':
                        record['crown_m']=float(crown); key=str(attributes['Boom_id'])
                    else:
                        record['source']['mounting_height_m']=float(height)
                        record['source']['beheerobject']=attributes.get('Beheerobject')
                        # Fixtures on a shared mast use the same source base. Distinct mast origins stay distinct.
                        mast_id=attributes.get('Beheerobject',source_id)
                        key=next((candidate for candidate in lamp_groups[mast_id] if math.hypot(x-unique[candidate]['x'],y-unique[candidate]['y'])<0.05),None)
                        if key is None:
                            key=(mast_id,len(lamp_groups[mast_id]));lamp_groups[mast_id].append(key)
                    if key in unique:
                        duplicate_count+=1
                        if dataset=='lamps' and record['height_m']>unique[key]['height_m']: unique[key]=record
                    else: unique[key]=record
        for record in unique.values():
            tile=f"x{math.floor(record['x']/250)*250}_y{math.floor(record['y']/250)*250}"
            tiles[tile][dataset].append(record)
        archive.save()
        manifest_bytes=(archive.directory/'manifest.json').read_bytes()
        manifest_hash=hashlib.sha256(manifest_bytes).hexdigest()
        manifest_snapshot=archive.directory/f'manifest-{manifest_hash}.json'
        if not manifest_snapshot.exists():manifest_snapshot.write_bytes(manifest_bytes)
        summary['datasets'][dataset]={'count':len(unique),'source_tiles':len(selected),'height_diagnostic':height_diagnostic,'duplicate_parts_collapsed':duplicate_count,'crown_parts_ignored':ignored_parts,'missing_dimensions_skipped':missing_dimensions,'nonpositive_source_dimensions_retained':zero_dimensions,'source_manifest':str(manifest_snapshot),'source_manifest_sha256':manifest_hash}
        print(dataset, {key: value for key,value in summary['datasets'][dataset].items() if key!='height_diagnostic'},flush=True)
    for tile,objects in tiles.items():
        directory=ROOT/'scene/v1/tiles'/tile;directory.mkdir(parents=True,exist_ok=True)
        for values in objects.values(): values.sort(key=lambda x:x['source_id'])
        (directory/'objects.json').write_text(json.dumps(objects,indent=2)+'\n')
    summary['tiles']={tile:{k:len(v) for k,v in objects.items()} for tile,objects in tiles.items()}
    (ROOT/'scene/v1'/f'objects-{area}-report.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--area',choices=['core','m0'],default='core')
    arguments=parser.parse_args()
    build(arguments.area)
