#!/usr/bin/env python3
"""Verify compact geometry directly against retained municipal source archives.
No git history, network, asset rewriting or appearance-converter invocation.
"""
import copy, importlib.util, io, json, struct
from pathlib import Path
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('appearance',ROOT/'scripts/prepare-building-appearance.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
import sys
if '--current' in sys.argv:
    m.SOURCE=ROOT/'source-data/current-building-appearance';m.OUTPUT=ROOT/'public/data/current-building-appearance';m.BASE='https://www.3drotterdam.nl/datasource-data/3adbe5af-d05c-475a-b34c-59e69ba8dadc/'
OUT=m.OUTPUT
manifest=json.loads((OUT/'manifest.json').read_text())
tiles=json.loads((OUT/'tileset.json').read_text())
# Native reference assets remain offline; runtime roots now replace with BAG leaves.
children={entry['output']:root for entry,root in zip(manifest['entries'],tiles['root']['children'])}
assert set(children)=={e['output'] for e in manifest['entries']}
assert tiles['asset']['gltfUpAxis']=='Y'
def read(raw):
    assert struct.unpack_from('<4sII',raw)==(b'glTF',2,len(raw))
    size=struct.unpack_from('<I',raw,12)[0]
    return json.loads(raw[20:20+size]),raw[28+size:]
def image_bytes(doc,binary,image):
    view=doc['bufferViews'][image['bufferView']];start=view.get('byteOffset',0)
    return binary[start:start+view['byteLength']]
def accessor_size(doc,index):
    a=doc['accessors'][index]
    return a['count']*m.SIZES[a['type']]*np.dtype(m.DTYPES[a['componentType']]).itemsize
old_geometry=new_geometry=triangles=0;all_ids=set();image_checks=0
for entry in manifest['entries']:
    path=OUT/entry['output'];raw=path.read_bytes()
    assert m.digest(raw)==entry['sha256'] and len(raw)==entry['bytes'],path
    part=int(path.stem.rsplit('-',1)[1])
    a,ab,batch,feature=list(m.b3dm_parts(m.fetch(entry['url'],False)))[part]
    b,bb=read(raw);tile=children[path.name]
    rtc=a.get('extensions',{}).get('CESIUM_RTC',{}).get('center',feature.get('RTC_CENTER'))
    assert tile['transform']==[1,0,0,0,0,1,0,0,0,0,1,0,*rtc,1]
    assert tile['boundingVolume']==entry['boundingVolume']
    ids=[str(attrs.get('gebouwnummer') or attrs.get('GEBOUWNUMMER') or batch.get('id',[''])[i]).removeprefix('ID_').removeprefix('BAG_') for i,attrs in enumerate(batch['attributes'])]
    materials=copy.deepcopy(a['materials']);textured=set()
    for i,material in enumerate(materials):
        if 'pbrMetallicRoughness' in material and 'KHR_techniques_webgl' not in material.get('extensions',{}):
            if 'baseColorTexture' in material['pbrMetallicRoughness']:textured.add(i)
            continue
        values=material.pop('extensions',{}).get('KHR_techniques_webgl',{}).get('values',{})
        pbr={'baseColorFactor':values.get('u_diffuse_mat',[.65,.65,.62,1]),'roughnessFactor':1,'metallicFactor':0}
        if 'u_diffuse_tex' in values:pbr['baseColorTexture']=values['u_diffuse_tex'];textured.add(i)
        material['pbrMetallicRoughness']=pbr
    assert b['materials']==materials,path
    assert b['samplers']==[{'magFilter':9728,'minFilter':9984,'wrapS':33071,'wrapT':33071}]
    textures=copy.deepcopy(a.get('textures',[]))
    for texture in textures:texture['sampler']=0
    assert b.get('textures',[])==textures
    selected=set()
    for mesh in a['meshes']:
        for p in mesh['primitives']:
            if p.get('material') in textured:selected.update(int(x) for x in np.unique(m.accessor(a,ab,p['attributes']['_BATCHID'])))
    expected_ids=[ids[i] for i in sorted(selected)]
    assert entry['bagIds']==tile['extras']['bagIds']==b['extras']['bagIds']==expected_ids
    all_ids.update(expected_ids)
    mesh_mapping={};output_index=0
    for mi,mesh in enumerate(a['meshes']):
        expected={}
        for p in mesh['primitives']:
            if p.get('mode',4)!=4:continue
            bids=m.accessor(a,ab,p['attributes']['_BATCHID'])[:,0]
            index=m.accessor(a,ab,p['indices'])[:,0] if 'indices' in p else np.arange(len(bids))
            faces=index.reshape(-1,3)
            assert np.all(bids[faces]==bids[faces[:,0],None])
            for bid in selected:
                chosen=faces[bids[faces[:,0]]==bid].reshape(-1)
                if len(chosen):expected.setdefault(bid,[]).append((p,chosen))
        mesh_mapping[mi]=[]
        for bid,primitives in expected.items():
            bm=b['meshes'][output_index];mesh_mapping[mi].append(output_index);output_index+=1
            assert bm['extras']['bagId']==ids[bid] and bm['name']=='BAG_'+ids[bid]
            assert len(bm['primitives'])==len(primitives)
            for (ap,chosen),bp in zip(primitives,bm['primitives']):
                assert {k:v for k,v in ap.items() if k not in ('attributes','indices')}=={k:v for k,v in bp.items() if k not in ('attributes','indices')}
                bi=m.accessor(b,bb,bp['indices'])[:,0];assert len(chosen)==len(bi)
                triangles+=len(bi)//3
                semantics=set(ap['attributes'])-{'_BATCHID'}
                assert set(bp['attributes'])==semantics
                assert 'POSITION' in semantics
                if ap.get('material') in textured:assert 'TEXCOORD_0' in semantics
                for semantic in semantics:
                    ai=ap['attributes'][semantic];oi=bp['attributes'][semantic]
                    av=m.accessor(a,ab,ai)[chosen];bv=m.accessor(b,bb,oi)[bi]
                    assert av.dtype==bv.dtype and np.array_equal(av,bv),(path,ids[bid],semantic)
                    assert a['accessors'][ai].get('normalized')==b['accessors'][oi].get('normalized')
                    assert b['accessors'][oi]['count']==len(np.unique(chosen))
                    old_geometry+=accessor_size(a,ai);new_geometry+=accessor_size(b,oi)
                old_geometry+=len(chosen)*4;new_geometry+=accessor_size(b,bp['indices'])
    assert output_index==len(b['meshes'])
    # Original node hierarchy/transforms survive; appended BAG nodes are identity transforms.
    nodes=copy.deepcopy(a['nodes'])
    for node in list(nodes):
        if 'matrix' in node:
            for key in ('translation','rotation','scale'):node.pop(key,None)
        if 'mesh' not in node:continue
        mi=node.pop('mesh');kids=node.setdefault('children',[])
        for index in mesh_mapping[mi]:
            bag=b['meshes'][index]['extras']['bagId'];kids.append(len(nodes))
            nodes.append({'mesh':index,'name':'BAG_'+bag,'extras':{'bagId':bag}})
    assert nodes==b['nodes'] and a['scenes']==b['scenes'] and a.get('scene')==b.get('scene')
    assert len(a.get('images',[]))==len(b.get('images',[]))==entry['atlases']
    if manifest['style']=='source':
        for ai,bi in zip(a['images'],b['images']):
            original=np.asarray(Image.open(io.BytesIO(image_bytes(a,ab,ai))).convert('RGB'))
            output=np.asarray(Image.open(io.BytesIO(image_bytes(b,bb,bi))).convert('RGB'))
            assert np.array_equal(original,output),path
            image_checks+=1
assert len(all_ids)==manifest['buildings'] and len(manifest['entries'])==manifest['outputTiles']
assert new_geometry<old_geometry
print(json.dumps({'tiles':len(manifest['entries']),'buildings':len(all_ids),'triangles_exact':triangles,'expanded_source_array_accounting_bytes':old_geometry,'compact_geometry_accounting_bytes':new_geometry,'style':manifest['style'],'source_image_pixel_equality_checks':image_checks,'image_note':'Source pixel equality applies only to --style source; styled images intentionally differ.'},indent=2))
