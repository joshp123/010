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
    if style=='source':
        out=io.BytesIO();original.save(out,format='PNG',optimize=True)
        return out.getvalue(),original,original
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
    source_doc=copy.deepcopy(doc)
    old_views=source_doc['bufferViews']
    doc['bufferViews']=[];doc['accessors']=[]
    views=doc['bufferViews'];new_binary=bytearray()
    def append_view(raw,target=None):
        new_binary.extend(b'\0'*((-len(new_binary))%4))
        view={'buffer':0,'byteOffset':len(new_binary),'byteLength':len(raw)}
        if target is not None:view['target']=target
        views.append(view);new_binary.extend(raw)
        return len(views)-1
    def append_accessor(values,template,target):
        a={k:copy.deepcopy(v) for k,v in template.items() if k not in ('bufferView','byteOffset','count','min','max','sparse')}
        a.update(bufferView=append_view(values.tobytes(),target),count=len(values))
        if 'min' in template:a['min']=values.min(axis=0).tolist()
        if 'max' in template:a['max']=values.max(axis=0).tolist()
        doc['accessors'].append(a)
        return len(doc['accessors'])-1
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
    image_views={}
    for im in doc.get('images',[]):
        old_index=im['bufferView']
        if old_index not in image_views:image_views[old_index]=append_view(image_data[old_index])
        im['bufferView']=image_views[old_index]
    original_meshes=doc['meshes'];doc['meshes']=[]
    mesh_map={}
    for mi,mesh in enumerate(original_meshes):
        split={}
        for p in mesh['primitives']:
            if p.get('mode',4)!=4:continue
            batch_ids=accessor(source_doc,binary,p['attributes']['_BATCHID'])[:,0]
            indices=accessor(source_doc,binary,p['indices'])[:,0] if 'indices' in p else np.arange(len(batch_ids),dtype=np.uint32)
            triangles=indices.reshape(-1,3)
            if not np.all(batch_ids[triangles]==batch_ids[triangles[:,0],None]):raise ValueError('Triangle spans multiple BAG IDs')
            for bid in selected:
                chosen=triangles[batch_ids[triangles[:,0]]==bid].reshape(-1)
                if not len(chosen):continue
                # Remap only referenced vertices. Keeping tile-wide accessors here
                # makes each BAG geometry charge the full tile to the shared cache.
                vertices,remapped=np.unique(chosen,return_inverse=True)
                cp=copy.deepcopy(p);cp['attributes']={}
                for semantic,source_ai in p['attributes'].items():
                    if semantic=='_BATCHID':continue
                    values=np.ascontiguousarray(accessor(source_doc,binary,source_ai)[vertices])
                    cp['attributes'][semantic]=append_accessor(values,source_doc['accessors'][source_ai],34962)
                index_type=5123 if len(vertices)<=65535 else 5125
                values=remapped.astype(DTYPES[index_type]).reshape(-1,1)
                cp['indices']=append_accessor(values,{'componentType':index_type,'type':'SCALAR','min':[0],'max':[len(vertices)-1]},34963)
                split.setdefault(bid,[]).append(cp)
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

def read_glb(raw):
    size=struct.unpack_from('<I',raw,12)[0]
    return json.loads(raw[20:20+size]),raw[28+size:]

def texture_lod(glb,limit=None):
    """Repack image views only; geometry values and accessor layout stay exact."""
    doc,binary=read_glb(glb);images={};dimensions=[];source_dimensions=[]
    for im in doc.get('images',[]):
        v=doc['bufferViews'][im['bufferView']];raw=binary[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']]
        image=Image.open(io.BytesIO(raw));source_dimensions.append(image.size)
        if limit and max(image.size)>limit:
            image.thumbnail((limit,limit),Image.Resampling.BOX)
            out=io.BytesIO();image.save(out,format='PNG',optimize=True);raw=out.getvalue()
        images[im['bufferView']]=raw;dimensions.append(image.size)
    # Physical source sampling: median non-degenerate triangle edge metres per
    # texel per material, then the largest material footprint within this tile.
    samples={}
    for mesh in doc['meshes']:
        for p in mesh['primitives']:
            material=doc['materials'][p['material']]['pbrMetallicRoughness']
            if 'baseColorTexture' not in material:continue
            ti=material['baseColorTexture']['index'];ii=doc['textures'][ti]['source']
            idx=accessor(doc,binary,p['indices'])[:,0].reshape(-1,3)
            pos=accessor(doc,binary,p['attributes']['POSITION'])[idx]
            uv=accessor(doc,binary,p['attributes']['TEXCOORD_0'])[idx]*dimensions[ii]
            for a,b in ((0,1),(1,2),(2,0)):
                meters=np.linalg.norm(pos[:,a]-pos[:,b],axis=1);pixels=np.linalg.norm(uv[:,a]-uv[:,b],axis=1)
                ok=(meters>0.1)&(pixels>1)
                samples.setdefault(ii,[]).extend((meters[ok]/pixels[ok]).tolist())
    spacing=max((float(np.median(s)) for s in samples.values() if s),default=0)
    decoded=0
    for w,h in dimensions:
        while True:
            decoded+=w*h*4
            if w==1 and h==1:break
            w=max(1,w//2);h=max(1,h//2)
    info={'maxTextureSize':max(max(d) for d in dimensions),'dimensions':[list(d) for d in dimensions],'decodedRgbaBytesIncludingMips':decoded,'samplingMetersPerTexel':spacing,'geometricError':spacing if limit else 0}
    if not limit:return glb,info
    new=bytearray()
    for i,v in enumerate(doc['bufferViews']):
        raw=images.get(i,binary[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']])
        new.extend(b'\0'*((-len(new))%4));v['byteOffset']=len(new);v['byteLength']=len(raw);new.extend(raw)
    doc['buffers']=[{'byteLength':len(new)}];jb=pad(packed_json(doc),fill=b' ');bb=pad(bytes(new))
    output=struct.pack('<4sII',b'glTF',2,28+len(jb)+len(bb))+struct.pack('<I4s',len(jb),b'JSON')+jb+struct.pack('<I4s',len(bb),b'BIN\0')+bb
    return output,info

def main():
    global STYLE
    ap=argparse.ArgumentParser();ap.add_argument('--acquire',action='store_true');ap.add_argument('--style',choices=['source','baseline','miniature'],default='miniature');args=ap.parse_args();STYLE=args.style
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
            _,native_info=texture_lod(glb)
            levels=[]
            for limit in (512,1024):
                if native_info['maxTextureSize']<=limit:continue
                lod,lod_info=texture_lod(glb,limit)
                lod_name=name.replace('.glb',f'-tex{limit}.glb');(OUTPUT/lod_name).write_bytes(lod)
                levels.append({**lod_info,'output':lod_name,'bytes':len(lod),'sha256':digest(lod)})
            levels.append({**native_info,'output':name,'bytes':len(glb),'sha256':digest(glb)})
            child=None
            for level in reversed(levels):
                node={'boundingVolume':t['boundingVolume'],'geometricError':level['geometricError'],'refine':'REPLACE','content':{'uri':level['output']},'extras':{'bagIds':ids}}
                if child:node['children']=[child]
                child=node
            # RTC appears only on the outer tile. Descendants inherit it once.
            child['transform']=transform
            children.append(child);all_ids.update(ids)
            entries.append({**t,'output':name,'sha256':digest(glb),'bytes':len(glb),'bagIds':ids,'atlases':image_count,'textureLevels':levels})
            print(f'{name}: {len(ids)} buildings, {len(glb)} bytes',flush=True)
    regions=[c['boundingVolume']['region'] for c in children]
    region=[min(r[0] for r in regions),min(r[1] for r in regions),max(r[2] for r in regions),max(r[3] for r in regions),min(r[4] for r in regions),max(r[5] for r in regions)]
    root_error=max(c['geometricError'] for c in children)*2
    tileset={'asset':{'version':'1.0','gltfUpAxis':'Y'},'geometricError':root_error,'root':{'boundingVolume':{'region':region},'geometricError':root_error,'refine':'ADD','children':children}}
    (OUTPUT/'tileset.json').write_bytes(packed_json(tileset)+b'\n')
    manifest={'sourceRoot':BASE+'tileset.json','areas':AREAS,'pipeline':'Original textured source mesh + UV retained; legacy PBR conversion; 3x3 median, saturation 0.82, selected palette preset with no dithering; explicit ECEF RTC origin; split by source BAG ID','license':'Gemeente Rotterdam public-domain model, attribution retained separately from MIT code','scope':'Review candidate only: older source geometry replaces matching BAG features, never overlays current geometry; no contemporary accuracy claim','style':STYLE,'sourceTiles':len(selected),'outputTiles':len(entries),'buildings':len(all_ids),'entries':entries}
    (OUTPUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    provenance={k:v for k,v in manifest.items() if k!='entries'}
    provenance['sourceEvidence']=[json.loads(p.read_text()) for p in sorted((SOURCE/'raw').glob('*.json'))]
    (SOURCE/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print(json.dumps({k:manifest[k] for k in ('sourceTiles','outputTiles','buildings')}))
if __name__=='__main__':main()
