#!/usr/bin/env python3
"""Rebuild a bounded, source-retained building-appearance review candidate.
Acquisition is explicit (--acquire); ordinary runs require retained source bytes.
Geometry, UVs, source transforms and BAG identity survive the material conversion.
"""
import argparse, copy, datetime, gzip, hashlib, io, json, math, struct, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'source-data/building-appearance'
OUTPUT=ROOT/'public/data/building-appearance'
BASE='https://www.3drotterdam.nl/datasource-data/a6aee273-9406-41c4-a504-de2a59f7d514/'
# Explicit bounded review windows, not claims of citywide appearance coverage.
AREAS={'delfshaven':[4.446,51.9085,4.450,51.911], 'centre':[4.483,51.9055,4.490,51.909]}
STYLE='miniature'
DTYPES={5120:'i1',5121:'u1',5122:'<i2',5123:'<u2',5125:'<u4',5126:'<f4'}
SIZES={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}

def digest(b):return hashlib.sha256(b).hexdigest()
def packed_json(obj):return json.dumps(obj,separators=(',',':')).encode()
def pad(b,n=4,fill=b'\0'):return b+fill*((-len(b))%n)

def source_path(url):return SOURCE/'raw'/((url.removeprefix(BASE)).replace('/','_')+'.gz')
def fetch(url,acquire):
    path=source_path(url)
    provenance=SOURCE/'provenance.json'
    evidence=json.loads(provenance.read_text()).get('sourceEvidence',[]) if provenance.exists() else []
    expected=next((entry['sha256'] for entry in evidence if entry['url']==url),None)
    if path.exists():
        raw=gzip.decompress(path.read_bytes())
        if expected and digest(raw)!=expected:raise ValueError(f'Retained source hash mismatch: {url}')
        return raw
    if not acquire:raise RuntimeError(f'Missing retained source {path}; use --acquire')
    req=urllib.request.Request(url,headers={'User-Agent':'010 Rotterdam miniature appearance research','Accept-Encoding':'gzip'})
    with urllib.request.urlopen(req,timeout=60) as response:
        b=response.read();b=gzip.decompress(b) if b[:2]==b'\x1f\x8b' else b
        if expected and digest(b)!=expected:raise ValueError(f'Upstream source changed from pinned edition: {url}')
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(gzip.compress(b,mtime=0))
        path.with_suffix('.json').write_text(json.dumps({'url':url,'acquiredAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sha256':digest(b),'decodedBytes':len(b),'lastModified':response.headers.get('Last-Modified')},indent=2)+'\n')
        return b

def overlaps(region,box):
    r=[v*180/math.pi for v in region[:4]]
    return r[0]<=box[2] and r[2]>=box[0] and r[1]<=box[3] and r[3]>=box[1]

def select_tiles(acquire):
    tiles=[]
    def walk(node,base,ancestry):
        region=node['boundingVolume'].get('region')
        areas=[name for name,box in AREAS.items() if region and overlaps(region,box)]
        if not areas:return
        # These source indexes use regional bounds and no node transforms.
        # Fail instead of silently flattening a future transformed edition.
        if node.get('transform'):raise ValueError('Source node transform requires explicit composition')
        content=node.get('content',{});uri=content.get('uri',content.get('url',''))
        if uri.endswith('.json'):
            u=urljoin(base,uri);walk(json.loads(fetch(u,acquire))['root'],u,ancestry+[u])
        elif not node.get('children') and uri:
            tiles.append({'url':urljoin(base,uri),'boundingVolume':node['boundingVolume'],'areas':areas})
        for c in node.get('children',[]):walk(c,base,ancestry)
    url=BASE+'tileset.json';walk(json.loads(fetch(url,acquire))['root'],url,[])
    return tiles

def b3dm_parts(b):
    if b[:4]==b'cmpt':
        p=16
        while p<len(b):
            size=struct.unpack_from('<I',b,p+8)[0]
            yield from b3dm_parts(b[p:p+size]);p+=size
    elif b[:4]==b'b3dm':
        h=struct.unpack_from('<4s6I',b);p=28
        feature=json.loads(b[p:p+h[3]]);p+=h[3]+h[4]
        batch=json.loads(b[p:p+h[5]]);p+=h[5]+h[6]
        glb=b[p:h[2]];jl=struct.unpack_from('<I',glb,12)[0]
        doc=json.loads(glb[20:20+jl]);p=20+jl
        binary=glb[p+8:p+8+struct.unpack_from('<I',glb,p)[0]]
        yield doc,binary,batch,feature

def accessor(doc,binary,index):
    a=doc['accessors'][index];v=doc['bufferViews'][a['bufferView']]
    dtype=np.dtype(DTYPES[a['componentType']]);components=SIZES[a['type']]
    offset=v.get('byteOffset',0)+a.get('byteOffset',0)
    return np.ndarray((a['count'],components),dtype=dtype,buffer=binary,offset=offset,strides=(v.get('byteStride',components*dtype.itemsize),dtype.itemsize))

def stylise(raw,style=None):
    style=style or STYLE
    original=Image.open(io.BytesIO(raw)).convert('RGB')
    # Edge-preserving median removes photographic noise, not semantic details.
    # No hue randomisation, super-resolution, hallucinated windows or equipment.
    image=original.filter(ImageFilter.MedianFilter(3))
    image=ImageEnhance.Color(image).enhance(0.82)
    image=image.quantize(colors=48 if style=='baseline' else 24,method=Image.Quantize.MEDIANCUT,dither=Image.Dither.NONE)
    # Palette-index mode filtering merges isolated photographic speckles into
    # existing adjacent regions without creating intermediate blurry colours.
    if style=='miniature':image=image.filter(ImageFilter.ModeFilter(3))
    image=image.convert('RGB')
    out=io.BytesIO();image.save(out,format='PNG',optimize=True)
    return out.getvalue(),original,image

def convert(doc,binary,batch,feature,label):
    doc=copy.deepcopy(doc)
    ids=[str(a.get('gebouwnummer') or a.get('GEBOUWNUMMER') or batch.get('id',[''])[i]).removeprefix('ID_').removeprefix('BAG_') for i,a in enumerate(batch.get('attributes',[]))]
    if not ids:raise ValueError('No source BAG identity')
    textured_materials=set()
    for i,m in enumerate(doc.get('materials',[])):
        values=m.pop('extensions',{}).get('KHR_techniques_webgl',{}).get('values',{})
        pbr={'baseColorFactor':values.get('u_diffuse_mat',[0.65,0.65,0.62,1]),'roughnessFactor':1,'metallicFactor':0}
        if 'u_diffuse_tex' in values:
            pbr['baseColorTexture']=values['u_diffuse_tex'];textured_materials.add(i)
        m['pbrMetallicRoughness']=pbr
    if not textured_materials:return None
    selected=set()
    for mesh in doc['meshes']:
        for p in mesh['primitives']:
            if p.get('material') in textured_materials:
                selected.update(int(x) for x in np.unique(accessor(doc,binary,p['attributes']['_BATCHID'])))
    if not selected:return None
    # Repack misaligned legacy bufferViews into valid 4-byte aligned GLB storage.
    views=doc['bufferViews'];new_binary=bytearray()
    old_views=copy.deepcopy(views)
    image_data={}
    for i,im in enumerate(doc.get('images',[])):
        v=old_views[im['bufferView']];raw=binary[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']]
        cooked,original,styled=stylise(raw);image_data[im['bufferView']]=cooked;im['mimeType']='image/png'
        # Retain an inspectable atlas comparison for the first source tile only.
        if label=='sample':
            original.thumbnail((1024,1024));styled.thumbnail((1024,1024))
            pair=Image.new('RGB',(original.width*2,original.height));pair.paste(original,(0,0));pair.paste(styled,(original.width,0));pair.save(OUTPUT/f'atlas-comparison-{i}.jpg',quality=92)
            if i==0:
                _,full_source,baseline=stylise(raw,'baseline');_,_,miniature=stylise(raw,'miniature')
                for name,box in [('facade',(380,290,760,650)),('roof',(0,0,450,360))]:
                    comparison=Image.new('RGB',(1140,405),'#e6e4dc');draw=ImageDraw.Draw(comparison)
                    for column,(title,im) in enumerate([('SOURCE',full_source),('BASELINE: 48 COLOURS',baseline),('MINIATURE: 24 + REGION MODE',miniature)]):
                        crop=im.crop(box);crop.thumbnail((376,360),Image.Resampling.NEAREST);comparison.paste(crop,(column*380,35));draw.text((column*380+6,10),title,fill='#222222')
                    comparison.save(OUTPUT/f'{name}-presets.jpg',quality=94)
    for i,v in enumerate(views):
        old=old_views[i];raw=image_data.get(i,binary[old.get('byteOffset',0):old.get('byteOffset',0)+old['byteLength']])
        new_binary.extend(b'\0'*((-len(new_binary))%4));v['byteOffset']=len(new_binary);v['byteLength']=len(raw);v['buffer']=0
        if v.get('byteStride',4)<4:v.pop('byteStride',None)
        new_binary.extend(raw)
    original_meshes=doc['meshes'];doc['meshes']=[]
    mesh_map={}
    for mi,mesh in enumerate(original_meshes):
        split={}
        for p in mesh['primitives']:
            if p.get('mode',4)!=4:continue
            batch_ids=accessor({'accessors':doc['accessors'],'bufferViews':old_views},binary,p['attributes']['_BATCHID'])[:,0]
            indices=accessor({'accessors':doc['accessors'],'bufferViews':old_views},binary,p['indices'])[:,0] if 'indices' in p else np.arange(len(batch_ids),dtype=np.uint32)
            triangles=indices.reshape(-1,3)
            if not np.all(batch_ids[triangles]==batch_ids[triangles[:,0],None]):raise ValueError('Triangle spans multiple BAG IDs')
            for bid in selected:
                chosen=triangles[batch_ids[triangles[:,0]]==bid].reshape(-1)
                if not len(chosen):continue
                new_binary.extend(b'\0'*((-len(new_binary))%4));offset=len(new_binary);raw=chosen.astype('<u4').tobytes();new_binary.extend(raw)
                vi=len(views);views.append({'buffer':0,'byteOffset':offset,'byteLength':len(raw),'target':34963})
                ai=len(doc['accessors']);doc['accessors'].append({'bufferView':vi,'componentType':5125,'count':len(chosen),'type':'SCALAR','min':[int(chosen.min())],'max':[int(chosen.max())]})
                cp=copy.deepcopy(p);cp['indices']=ai;cp['attributes'].pop('_BATCHID',None);split.setdefault(bid,[]).append(cp)
        mesh_map[mi]=[]
        for bid,primitives in split.items():
            mesh_map[mi].append(len(doc['meshes']))
            doc['meshes'].append({'name':f'BAG_{ids[bid]}','primitives':primitives,'extras':{'bagId':ids[bid],'sourceEdition':'2019 municipal textured mesh','appearance':f'source atlas, {STYLE} preset'}})
    for node in list(doc['nodes']):
        # Legacy exporter wrote both matrix and bogus TRS. glTF permits one only.
        if 'matrix' in node:
            for k in ('translation','rotation','scale'):node.pop(k,None)
        if 'mesh' not in node:continue
        mi=node.pop('mesh');children=node.setdefault('children',[])
        for new_mi in mesh_map[mi]:
            children.append(len(doc['nodes']));bag=doc['meshes'][new_mi]['extras']['bagId']
            doc['nodes'].append({'mesh':new_mi,'name':f'BAG_{bag}','extras':{'bagId':bag}})
    rtc=doc.get('extensions',{}).get('CESIUM_RTC',{}).get('center',feature.get('RTC_CENTER'))
    if not rtc:raise ValueError('Expected source RTC origin')
    doc.pop('extensions',None);doc.pop('extensionsUsed',None);doc.pop('extensionsRequired',None)
    doc['buffers']=[{'byteLength':len(new_binary)}]
    doc['extras']={'bagIds':[ids[i] for i in sorted(selected)],'source':'Gemeente Rotterdam / Rotterdam 3D','sourceLicense':'Public domain; see docs/data-sources.md','interpretation':'Bounded older-source appearance review candidate, not contemporary surveyed facades'}
    for key in ('animations','cameras','skins'):
        if not doc.get(key):doc.pop(key,None)
    doc.pop('samplerRepeat',None)
    doc['samplers']=[{'magFilter':9728,'minFilter':9984,'wrapS':33071,'wrapT':33071}]
    for texture in doc.get('textures',[]):texture['sampler']=0
    jb=pad(packed_json(doc),fill=b' ');bb=pad(bytes(new_binary))
    glb=struct.pack('<4sII',b'glTF',2,12+8+len(jb)+8+len(bb))+struct.pack('<I4s',len(jb),b'JSON')+jb+struct.pack('<I4s',len(bb),b'BIN\0')+bb
    transform=[1,0,0,0,0,1,0,0,0,0,1,0,*rtc,1]
    return glb,transform,doc['extras']['bagIds'],len(doc.get('images',[]))

def main():
    global STYLE
    ap=argparse.ArgumentParser();ap.add_argument('--acquire',action='store_true');ap.add_argument('--style',choices=['baseline','miniature'],default='miniature');args=ap.parse_args();STYLE=args.style
    SOURCE.mkdir(parents=True,exist_ok=True);OUTPUT.mkdir(parents=True,exist_ok=True)
    selected=select_tiles(args.acquire)
    print(f'Selected {len(selected)} source tiles',flush=True)
    with ThreadPoolExecutor(max_workers=5) as pool:list(pool.map(lambda t:fetch(t['url'],args.acquire),selected))
    children=[];entries=[];all_ids=set()
    for t in selected:
        for part,(doc,binary,batch,feature) in enumerate(b3dm_parts(fetch(t['url'],False))):
            result=convert(doc,binary,batch,feature,'sample' if not entries else '')
            if not result:continue
            glb,transform,ids,image_count=result
            name=t['url'].removeprefix(BASE).replace('/','-').replace('.cmpt','').replace('.b3dm','')+f'-{part}.glb'
            (OUTPUT/name).write_bytes(glb)
            child={'boundingVolume':t['boundingVolume'],'geometricError':0,'transform':transform,'content':{'uri':name},'extras':{'bagIds':ids}}
            children.append(child);all_ids.update(ids)
            entries.append({**t,'output':name,'sha256':digest(glb),'bytes':len(glb),'bagIds':ids,'atlases':image_count})
            print(f'{name}: {len(ids)} buildings, {len(glb)} bytes',flush=True)
    regions=[c['boundingVolume']['region'] for c in children]
    region=[min(r[0] for r in regions),min(r[1] for r in regions),max(r[2] for r in regions),max(r[3] for r in regions),min(r[4] for r in regions),max(r[5] for r in regions)]
    tileset={'asset':{'version':'1.0','gltfUpAxis':'Y'},'geometricError':0,'root':{'boundingVolume':{'region':region},'geometricError':0,'refine':'ADD','children':children}}
    (OUTPUT/'tileset.json').write_bytes(packed_json(tileset)+b'\n')
    manifest={'sourceRoot':BASE+'tileset.json','areas':AREAS,'pipeline':'Original textured source mesh + UV retained; legacy PBR conversion; 3x3 median, saturation 0.82, selected palette preset with no dithering; explicit ECEF RTC origin; split by source BAG ID','license':'Gemeente Rotterdam public-domain model, attribution retained separately from MIT code','scope':'Review candidate only: older source geometry replaces matching BAG features, never overlays current geometry; no contemporary accuracy claim','style':STYLE,'sourceTiles':len(selected),'outputTiles':len(entries),'buildings':len(all_ids),'entries':entries}
    (OUTPUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    provenance={k:v for k,v in manifest.items() if k!='entries'}
    provenance['sourceEvidence']=[json.loads(p.read_text()) for p in sorted((SOURCE/'raw').glob('*.json'))]
    (SOURCE/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print(json.dumps({k:manifest[k] for k in ('sourceTiles','outputTiles','buildings')}))
if __name__=='__main__':main()
