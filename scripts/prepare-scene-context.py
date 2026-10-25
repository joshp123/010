#!/usr/bin/env python3
"""Place original authored context triangles in the existing tile coordinate frame.
Written by AI on 2026-10-25 by model GPT-6.
"""
import argparse, copy, gzip, importlib.util, json, shutil, struct
from pathlib import Path
import numpy as np

spec=importlib.util.spec_from_file_location('appearance',Path(__file__).with_name('prepare-building-appearance.py'))
appearance=importlib.util.module_from_spec(spec);spec.loader.exec_module(appearance)

def prepare(source,output):
    metadata=json.loads((source/'context-identities.json').read_text())
    raw=(source/metadata['geometryAsset']).read_bytes()
    assert appearance.digest(raw)==metadata['geometrySha256']
    json_size=struct.unpack_from("<I",raw,12)[0]
    document=json.loads(raw[20:20+json_size]);binary=raw[28+json_size:]
    assert document['nodes'][0]['matrix']==metadata['rootMatrixColumnMajor']
    assert document['extensions']['CESIUM_RTC']['center']==metadata['rtcECEF']
    yz=np.array([[1,0,0],[0,0,-1],[0,1,0]])
    rotation=yz@np.array(metadata['rootMatrixColumnMajor']).reshape(4,4,order='F')[:3,:3]
    native_ground=Path(__file__).resolve().parents[1]/'source-data/public-space-pilot/33577-6934.b3dm.gz'
    _,_,batch,_=next(appearance.b3dm_parts(gzip.decompress(native_ground.read_bytes())))
    attributes={str(identity):batch['attributes'][index] for index,identity in enumerate(batch['id'])}
    for kind in ('ground','tree'):
        folder=output/kind;folder.mkdir(parents=True,exist_ok=True)
        doc=copy.deepcopy(document);nodes=[];points=[];identities=[]
        for index in doc['nodes'][0]['children']:
            node=doc['nodes'][index];mesh=doc['meshes'][node['mesh']]
            if mesh['primitives'][0]['extras']['contextKind']!=kind:continue
            nodes.append(index)
            for primitive in mesh['primitives']:
                primitive['extras']['authoredSceneContext']=True
                if kind=='ground':primitive['extras']['sourceAttributes']=attributes[primitive['extras']['sourceFeatureId']]
                mesh['extras']=copy.deepcopy(primitive['extras'])
                identities.append(primitive['extras']['sourceIdentity'])
                positions=appearance.accessor(doc,binary,primitive['attributes']['POSITION'])
                points.extend(positions@rotation.T)
        doc['nodes'][0]['children']=nodes
        doc['extensions'].pop('CESIUM_RTC')
        doc['extensionsUsed']=[extension for extension in doc.get('extensionsUsed',[]) if extension!='CESIUM_RTC']
        points=np.array(points);centre=(points.min(0)+points.max(0))/2
        radius=float(np.linalg.norm(points-centre,axis=1).max())+.01
        rtc=metadata['rtcECEF'];world=centre+rtc
        (folder/'model.glb').write_bytes(appearance.pack_glb(doc,binary))
        for image in doc['images']:
            if 'uri' in image:shutil.copy2(source/image['uri'],folder/image['uri'])
        tile={'asset':{'version':'1.0','gltfUpAxis':'Y'},'geometricError':0,'root':{'boundingVolume':{'sphere':[*world,radius]},'geometricError':0,'refine':'REPLACE','children':[{'boundingVolume':{'sphere':[*centre,radius]},'transform':[1,0,0,0,0,1,0,0,0,0,1,0,*rtc,1],'geometricError':0,'content':{'uri':'model.glb'},'extras':{'sourceIdentities':identities}}]}}
        (folder/'tileset.json').write_text(json.dumps(tile,indent=2)+'\n')
    shutil.copy2(source/'context-identities.json',output/'context-identities.json')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();prepare(args.source,args.output)
