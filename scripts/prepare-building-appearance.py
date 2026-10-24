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
EDITION='legacy'
REQUESTED_TILES=[]
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
        if REQUESTED_TILES:areas=['explicit source tiles']
        if not areas:return
        # These source indexes use regional bounds and no node transforms.
        # Fail instead of silently flattening a future transformed edition.
        if node.get('transform'):raise ValueError('Source node transform requires explicit composition')
        content=node.get('content',{});uri=content.get('uri',content.get('url',''))
        if uri.endswith('.json'):
            u=urljoin(base,uri)
            if REQUESTED_TILES and u!=BASE+'tileset.json':
                parts=u.removeprefix(BASE).removesuffix('.json').split('/')
                if len(parts)==3 and all(v.isdigit() for v in parts):
                    level,x,y=map(int,parts)
                    if not any(int(t.split('/')[1])//2**(int(t.split('/')[0])-level)==x and int(t.split('/')[2].split('.')[0])//2**(int(t.split('/')[0])-level)==y for t in REQUESTED_TILES):return
            walk(json.loads(fetch(u,acquire))['root'],u,ancestry+[u])
        elif not node.get('children') and uri:
            u=urljoin(base,uri)
            if not REQUESTED_TILES or u.removeprefix(BASE) in REQUESTED_TILES:tiles.append({'url':u,'boundingVolume':node['boundingVolume'],'areas':areas})
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
        legacy=m.get('extensions',{}).get('KHR_techniques_webgl')
        if legacy is None and 'pbrMetallicRoughness' in m:
            if 'baseColorTexture' in m['pbrMetallicRoughness']:textured_materials.add(i)
            continue
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
            doc['meshes'].append({'name':f'BAG_{ids[bid]}','primitives':primitives,'extras':{'bagId':ids[bid],'sourceEdition':('current municipal textured mesh (3adbe5af)' if EDITION=='current' else '2019 municipal textured mesh'),'appearance':f'source atlas, {STYLE} preset'}})
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
    for key in ('extensionsUsed','extensionsRequired'):
        doc[key]=[x for x in doc.get(key,[]) if x not in ('CESIUM_RTC','KHR_techniques_webgl')]
        if not doc[key]:doc.pop(key)
    for key in ('CESIUM_RTC','KHR_techniques_webgl'):doc.get('extensions',{}).pop(key,None)
    if not doc.get('extensions'):doc.pop('extensions',None)
    doc['buffers']=[{'byteLength':len(new_binary)}]
    doc['extras']={'bagIds':[ids[i] for i in sorted(selected)],'source':'Gemeente Rotterdam / Rotterdam 3D','sourceLicense':('CC BY 4.0; Gemeente Rotterdam — 3D Rotterdam' if EDITION=='current' else 'Public domain; see docs/data-sources.md'),'interpretation':'Bounded source appearance review candidate; photographic capture date not established'}
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

def rgba_mip_bytes(width,height):
    total=0
    while True:
        total+=width*height*4
        if width==height==1:return total
        width=max(1,width//2);height=max(1,height//2)

def uv_islands(indices,uv):
    """Connected triangle components in UV space, preserving original seams."""
    parents=list(range(len(indices)));edges={}
    def root(i):
        while parents[i]!=i:parents[i]=parents[parents[i]];i=parents[i]
        return i
    for ti,triangle in enumerate(indices):
        keys=[tuple(uv[v].tolist()) for v in triangle]
        for a,b in ((0,1),(1,2),(2,0)):
            edge=tuple(sorted((keys[a],keys[b])))
            if edge in edges:parents[root(ti)]=root(edges[edge])
            else:edges[edge]=ti
    groups={}
    for i in range(len(indices)):groups.setdefault(root(i),[]).append(i)
    return list(groups.values())

def pack_rectangles(rectangles):
    """Deterministic shelf pack, no rotation or resampling of source rectangles."""
    if not rectangles:return 1,1
    order=sorted(range(len(rectangles)),key=lambda i:(-rectangles[i]['height'],-rectangles[i]['width'],i))
    area=sum(r['width']*r['height'] for r in rectangles)
    minimum=max(r['width'] for r in rectangles)
    candidates=sorted(set([minimum,*[max(minimum,int(np.sqrt(area)*f)) for f in (.65,.85,1,1.25,1.5,2)]]))
    best=None
    for width in candidates:
        x=y=row=used_width=0;placements=[]
        for i in order:
            r=rectangles[i]
            if x+r['width']>width:x=0;y+=row;row=0
            placements.append((i,x,y));x+=r['width'];row=max(row,r['height']);used_width=max(used_width,x)
        height=y+row
        score=used_width*height
        if EDITION=='current' and max(used_width,height)>8192:score=float('inf')
        if best is None or score<best[0]:best=(score,used_width,height,placements)
    # MaxRects complements shelf packing for mixed long facade/roof patches.
    # Rectangles may overlap in the free list, never in occupied source patches.
    area_order=sorted(range(len(rectangles)),key=lambda i:(-rectangles[i]['width']*rectangles[i]['height'],i))
    for width in candidates:
        for factor in (1.02,1.1,1.25,1.5):
            height=max(max(r['height'] for r in rectangles),int(np.ceil(area/width*factor)))
            if width*height>=best[0]*1.5 or (EDITION=='current' and max(width,height)>8192):continue
            free=[(0,0,width,height)];placements=[];used_w=used_h=0
            for i in area_order:
                rw,rh=rectangles[i]['width'],rectangles[i]['height']
                fits=[(min(fw-rw,fh-rh),max(fw-rw,fh-rh),y,x) for x,y,fw,fh in free if fw>=rw and fh>=rh]
                if not fits:break
                _,_,y,x=min(fits);placements.append((i,x,y));used_w=max(used_w,x+rw);used_h=max(used_h,y+rh)
                split=[]
                for fx,fy,fw,fh in free:
                    if x>=fx+fw or x+rw<=fx or y>=fy+fh or y+rh<=fy:split.append((fx,fy,fw,fh));continue
                    if x>fx:split.append((fx,fy,x-fx,fh))
                    if x+rw<fx+fw:split.append((x+rw,fy,fx+fw-x-rw,fh))
                    if y>fy:split.append((fx,fy,fw,y-fy))
                    if y+rh<fy+fh:split.append((fx,y+rh,fw,fy+fh-y-rh))
                unique=list(dict.fromkeys(split))
                free=[r for j,r in enumerate(unique) if not any(k!=j and r[0]>=q[0] and r[1]>=q[1] and r[0]+r[2]<=q[0]+q[2] and r[1]+r[3]<=q[1]+q[3] for k,q in enumerate(unique))]
            if len(placements)==len(rectangles):
                if used_w*used_h<best[0]:best=(used_w*used_h,used_w,used_h,placements)
                break
    if not np.isfinite(best[0]):raise ValueError('Native atlas requires multiple atlases to fit8192 edge without resampling')
    for i,x,y in best[3]:rectangles[i]['packedOrigin']=[x,y]
    return best[1],best[2]

def spatial_buildings(glb,label):
    """Per-BAG native texels packed by connected UV island, with tight local boxes."""
    src,binary=read_glb(glb);worlds={}
    def walk(ni,parent):
        node=src['nodes'][ni]
        if any(k in node for k in ('translation','rotation','scale')):raise ValueError('Expected source matrix nodes')
        mat=parent@np.array(node.get('matrix',np.eye(4).flatten(order='F'))).reshape(4,4,order='F')
        if 'mesh' in node:worlds.setdefault(node['mesh'],[]).append(mat)
        for child in node.get('children',[]):walk(child,mat)
    for ni in src['scenes'][src.get('scene',0)]['nodes']:walk(ni,np.eye(4))
    atlases=[]
    for im in src.get('images',[]):
        v=src['bufferViews'][im['bufferView']]
        atlases.append(Image.open(io.BytesIO(binary[v.get('byteOffset',0):v.get('byteOffset',0)+v['byteLength']])).convert('RGB'))
    grouped={}
    for mi,mesh in enumerate(src['meshes']):grouped.setdefault(mesh['extras']['bagId'],[]).append(mi)
    for bag,mesh_ids in grouped.items():
        rectangles=[];plans={};provenance=[]
        for mi in mesh_ids:
            for pi,p in enumerate(src['meshes'][mi]['primitives']):
                tex=src['materials'][p['material']]['pbrMetallicRoughness'].get('baseColorTexture')
                if tex is None:continue
                ii=src['textures'][tex['index']]['source'];image=atlases[ii]
                uv=accessor(src,binary,p['attributes']['TEXCOORD_0']);triangles=accessor(src,binary,p['indices'])[:,0].reshape(-1,3)
                plan=[]
                for rows in uv_islands(triangles,uv):
                    values=uv[triangles[rows].reshape(-1)];pixels=values*image.size
                    lo=np.maximum(0,np.floor(pixels.min(axis=0)).astype(int)-2);hi=np.minimum(image.size,np.ceil(pixels.max(axis=0)).astype(int)+2)
                    if np.any(hi<=lo):raise ValueError('Invalid source UV crop')
                    rect={'sourceImage':ii,'sourceSize':list(image.size),'sourceCrop':[int(lo[0]),int(lo[1]),int(hi[0]),int(hi[1])],'width':int(hi[0]-lo[0]),'height':int(hi[1]-lo[1]),'sourceMesh':mi,'sourcePrimitive':pi,'sourceTriangles':rows}
                    plan.append(len(rectangles));rectangles.append(rect)
                plans[mi,pi]=plan
        width,height=pack_rectangles(rectangles)
        atlas=Image.new('RGB',(width,height))
        for r in rectangles:atlas.paste(atlases[r['sourceImage']].crop(r['sourceCrop']),tuple(r['packedOrigin']))
        doc={'asset':copy.deepcopy(src['asset']),'scene':0,'scenes':[{'nodes':[]}],'nodes':[],'meshes':[],'accessors':[],'bufferViews':[],'buffers':[],'materials':[],'extras':{**src['extras'],'bagIds':[bag],'spatialSource':label}}
        payload=bytearray()
        def view(raw,target=None):
            payload.extend(b'\0'*((-len(payload))%4));v={'buffer':0,'byteOffset':len(payload),'byteLength':len(raw)}
            if target:v['target']=target
            payload.extend(raw);doc['bufferViews'].append(v);return len(doc['bufferViews'])-1
        def attr(values,template,target):
            a={k:copy.deepcopy(v) for k,v in template.items() if k not in ('bufferView','byteOffset','count','min','max','sparse')}
            a.update(bufferView=view(values.tobytes(),target),count=len(values))
            if 'min' in template:a['min']=values.min(axis=0).tolist()
            if 'max' in template:a['max']=values.max(axis=0).tolist()
            doc['accessors'].append(a);return len(doc['accessors'])-1
        if rectangles:
            png=io.BytesIO();atlas.save(png,format='PNG',optimize=True)
            doc['images']=[{'bufferView':view(png.getvalue()),'mimeType':'image/png'}]
            doc['samplers']=copy.deepcopy(src['samplers']);doc['textures']=[{'source':0,'sampler':0}]
        material_map={};bounds=[]
        for mi in mesh_ids:
            mesh=copy.deepcopy(src['meshes'][mi]);mesh['primitives']=[]
            for pi,p in enumerate(src['meshes'][mi]['primitives']):
                if p['material'] not in material_map:
                    material=copy.deepcopy(src['materials'][p['material']]);tex=material['pbrMetallicRoughness'].get('baseColorTexture')
                    if tex is not None:tex['index']=0
                    material_map[p['material']]=len(doc['materials']);doc['materials'].append(material)
                triangles=accessor(src,binary,p['indices'])[:,0].reshape(-1,3)
                vertex_ids=[];new_indices=np.empty_like(triangles);new_uv=[]
                if (mi,pi) in plans:
                    uv=accessor(src,binary,p['attributes']['TEXCOORD_0'])
                    for ri in plans[mi,pi]:
                        r=rectangles[ri];rows=r['sourceTriangles'];used,inv=np.unique(triangles[rows],return_inverse=True)
                        new_indices[rows]=inv.reshape(-1,3)+len(vertex_ids);vertex_ids.extend(used.tolist())
                        mapped=(uv[used].astype(float)*r['sourceSize']-r['sourceCrop'][:2]+r['packedOrigin'])/[width,height]
                        new_uv.extend(mapped.tolist())
                else:
                    used,inv=np.unique(triangles,return_inverse=True);vertex_ids=used.tolist();new_indices=inv.reshape(-1,3)
                cp={**copy.deepcopy(p),'attributes':{},'material':material_map[p['material']]}
                for semantic,ai in p['attributes'].items():
                    values=np.ascontiguousarray(accessor(src,binary,ai)[vertex_ids])
                    if semantic=='TEXCOORD_0' and new_uv:values=np.asarray(new_uv,dtype=values.dtype)
                    cp['attributes'][semantic]=attr(values,src['accessors'][ai],34962)
                    if semantic=='POSITION':
                        for matrix in worlds[mi]:
                            transformed=np.c_[values,np.ones(len(values))]@matrix.T
                            # glTF Y-up -> 3D Tiles Z-up, then inherited RTC translation.
                            bounds.append(transformed[:,:3][:,[0,2,1]]*[1,-1,1])
                it=5123 if len(vertex_ids)<=65535 else 5125
                cp['indices']=attr(new_indices.reshape(-1,1).astype(DTYPES[it]),{'componentType':it,'type':'SCALAR'},34963)
                mesh['primitives'].append(cp)
            new_mi=len(doc['meshes']);doc['meshes'].append(mesh)
            for matrix in worlds[mi]:
                doc['scenes'][0]['nodes'].append(len(doc['nodes']));doc['nodes'].append({'mesh':new_mi,'matrix':matrix.flatten(order='F').tolist(),'extras':{'bagId':bag}})
        points=np.concatenate(bounds)
        up_axis=np.array([[1,0,0],[0,0,-1],[0,1,0]],dtype=float)
        frame=up_axis@worlds[mesh_ids[0]][0][:3,:3]
        if not np.allclose(frame.T@frame,np.eye(3),atol=1e-6):raise ValueError('Expected rigid source frame')
        # Oriented source-frame box avoids inflated ECEF AABBs at oblique views.
        in_frame=points@frame;low=in_frame.min(axis=0);high=in_frame.max(axis=0)
        centre=((low+high)/2)@frame.T;half=(high-low)/2+.001
        box=[*centre,*(frame*half).flatten(order='F')]
        provenance={'bagId':bag,'sourceAsset':label,'sourceAssetSha256':digest(glb),'atlasSize':[width,height],'paddingPixels':2,'mapping':'originalUV = (packedUV * atlasSize - packedOrigin + sourceCrop.xy) / sourceSize','islands':rectangles}
        doc['extras']['texturePacking']=provenance
        doc['buffers']=[{'byteLength':len(payload)}];jb=pad(packed_json(doc),fill=b' ');bb=pad(bytes(payload))
        packed=struct.pack('<4sII',b'glTF',2,28+len(jb)+len(bb))+struct.pack('<I4s',len(jb),b'JSON')+jb+struct.pack('<I4s',len(bb),b'BIN\0')+bb
        yield bag,packed,{'box':box},{'atlasSize':[width,height],'decodedRgbaBytesIncludingMips':rgba_mip_bytes(width,height) if rectangles else 0,'islands':len(rectangles)}

def main():
    global STYLE,EDITION,SOURCE,OUTPUT,BASE,REQUESTED_TILES
    ap=argparse.ArgumentParser();ap.add_argument('--acquire',action='store_true');ap.add_argument('--reuse-native',action='store_true',help='Rebuild residency from existing native files of the selected style');ap.add_argument('--style',choices=['source','baseline','miniature'],default='source');ap.add_argument('--edition',choices=['legacy','current'],default='legacy');ap.add_argument('--tile',action='append',default=[],help='Explicit native leaf path, e.g.18/268620/55473.b3dm');args=ap.parse_args();STYLE=args.style;EDITION=args.edition;REQUESTED_TILES=args.tile
    if EDITION=='current':
        SOURCE=ROOT/'source-data/current-building-appearance';OUTPUT=ROOT/'public/data/current-building-appearance';BASE='https://www.3drotterdam.nl/datasource-data/3adbe5af-d05c-475a-b34c-59e69ba8dadc/'
        if STYLE!='source':raise ValueError('Current edition first review requires unchanged source style')
    SOURCE.mkdir(parents=True,exist_ok=True);OUTPUT.mkdir(parents=True,exist_ok=True)
    if args.reuse_native and json.loads((OUTPUT/'manifest.json').read_text())['style']!=STYLE:raise ValueError('Existing native style differs from --style')
    selected=select_tiles(args.acquire)
    if REQUESTED_TILES and set(REQUESTED_TILES)!={t['url'].removeprefix(BASE) for t in selected}:raise ValueError('Requested source leaf missing from retained hierarchy')
    print(f'Selected {len(selected)} source tiles',flush=True)
    with ThreadPoolExecutor(max_workers=5) as pool:list(pool.map(lambda t:fetch(t['url'],args.acquire),selected))
    children=[];entries=[];all_ids=set()
    for t in selected:
        for part,(doc,binary,batch,feature) in enumerate(b3dm_parts(fetch(t['url'],False))):
            existing_name=t['url'].removeprefix(BASE).replace('/','-').replace('.cmpt','').replace('.b3dm','')+f'-{part}.glb'
            if args.reuse_native and (OUTPUT/existing_name).exists():
                existing=(OUTPUT/existing_name).read_bytes();existing_doc,_=read_glb(existing)
                rtc=doc.get('extensions',{}).get('CESIUM_RTC',{}).get('center',feature.get('RTC_CENTER'))
                result=(existing,[1,0,0,0,0,1,0,0,0,0,1,0,*rtc,1],existing_doc['extras']['bagIds'],len(existing_doc.get('images',[])))
            else:result=convert(doc,binary,batch,feature,'sample' if not entries else '')
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
            spatial=[];spatial_nodes=[]
            for bag,packed,bounds,info in spatial_buildings(glb,name):
                packed_name=name.replace('.glb',f'-bag{bag}.glb');(OUTPUT/packed_name).write_bytes(packed)
                spatial.append({**info,'bagId':bag,'output':packed_name,'sha256':digest(packed),'bytes':len(packed),'boundingVolume':bounds})
                spatial_nodes.append({'boundingVolume':bounds,'geometricError':0,'content':{'uri':packed_name},'extras':{'bagIds':[bag]}})
            child_nodes=spatial_nodes
            for level in reversed(levels[:-1]):
                node={'boundingVolume':t['boundingVolume'],'geometricError':level['geometricError'],'refine':'REPLACE','content':{'uri':level['output']},'extras':{'bagIds':ids},'children':child_nodes}
                child_nodes=[node]
            child=child_nodes[0] if len(child_nodes)==1 else {'boundingVolume':t['boundingVolume'],'geometricError':native_info['samplingMetersPerTexel'],'refine':'REPLACE','children':child_nodes}
            # RTC appears only on the outer tile. Descendants inherit it once.
            child['transform']=transform
            children.append(child);all_ids.update(ids)
            entries.append({**t,'output':name,'sha256':digest(glb),'bytes':len(glb),'bagIds':ids,'atlases':image_count,'textureLevels':levels,'spatialBuildings':spatial})
            print(f'{name}: {len(ids)} buildings, {len(glb)} bytes',flush=True)
    regions=[c['boundingVolume']['region'] for c in children]
    region=[min(r[0] for r in regions),min(r[1] for r in regions),max(r[2] for r in regions),max(r[3] for r in regions),min(r[4] for r in regions),max(r[5] for r in regions)]
    root_error=max(c['geometricError'] for c in children)*2
    tileset={'asset':{'version':'1.0','gltfUpAxis':'Y'},'geometricError':root_error,'root':{'boundingVolume':{'region':region},'geometricError':root_error,'refine':'ADD','children':children}}
    (OUTPUT/'tileset.json').write_bytes(packed_json(tileset)+b'\n')
    manifest={'sourceRoot':BASE+'tileset.json','areas':AREAS,'edition':EDITION,'pipeline':'Original source geometry and UV retained; native PBR preserved or legacy technique converted; explicit ECEF RTC; per-BAG native source-pixel residency; selected style recorded separately','license':('Gemeente Rotterdam — 3D Rotterdam, CC BY 4.0' if EDITION=='current' else 'Gemeente Rotterdam public-domain model'),'scope':'Bounded review candidate; photographic capture date not established','style':STYLE,'sourceTiles':len(selected),'outputTiles':len(entries),'buildings':len(all_ids),'entries':entries}
    (OUTPUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    provenance={k:v for k,v in manifest.items() if k!='entries'}
    provenance['sourceEvidence']=[json.loads(p.read_text()) for p in sorted((SOURCE/'raw').glob('*.json'))]
    (SOURCE/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print(json.dumps({k:manifest[k] for k in ('sourceTiles','outputTiles','buildings')}))
if __name__=='__main__':main()
