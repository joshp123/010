#!/usr/bin/env python3
"""Bind sequential complete-scene drawings to retained source surfaces.
Written by AI on 2026-10-25 by model GPT-6.
"""
import argparse, importlib.util, json
from pathlib import Path
import numpy as np
from PIL import Image

spec=importlib.util.spec_from_file_location('composition',Path(__file__).with_name('compose-neighbourhood-source.py'))
composition=importlib.util.module_from_spec(spec);spec.loader.exec_module(composition)
painter=composition.painter


def restore_observed_road_paint(source,runtime):
    previous=np.asarray(Image.open(runtime/'public/data/ground-artwork-neighbourhood-v3/neighbourhood-ground.png').convert('RGBA'))
    eligible=previous[:,:,3]>0
    paint=np.all(previous[:,:,:3]==[222,219,200],axis=2)&eligible
    source.images[source.context['groundImage']][paint]=[222,219,200]


def bind(source,folder,runtime,angle,drawing_path,previous_state=None,pixels_per_metre=6,views_path=None,revise_visible=False,tree_drawing_path=None):
    views=json.loads((views_path or folder/'views.json').read_text())['views']
    view=next(v for v in views if v['camera']['angle']==angle);camera=view['camera']
    painted=[np.zeros(image.shape[:2],bool) for image in source.images]
    if previous_state:
        saved=np.load(previous_state)
        for index in range(len(source.images)):
            source.images[index]=saved[f'image_{index}'].copy();painted[index]=saved[f'painted_{index}'].copy()
    drawing=Image.open(drawing_path).convert('RGBA')
    authored_side=round(camera['size']/camera['scale']*pixels_per_metre)
    drawing=drawing.resize((authored_side,authored_side),Image.Resampling.BOX).resize((camera['size'],camera['size']),Image.Resampling.NEAREST)
    if tree_drawing_path:
        tree_drawing=Image.open(tree_drawing_path).convert('RGBA').resize((authored_side,authored_side),Image.Resampling.BOX).resize((camera['size'],camera['size']),Image.Resampling.NEAREST)
        tree_image_indices={triangle['image'] for triangle in source.triangles if triangle.get('contextKind')=='tree'}
        original_images=source.images
        source.images=[np.full_like(image,255 if index in tree_image_indices else 0) for index,image in enumerate(original_images)]
        support,_=painter.render(source,camera);source.images=original_images
        registered=np.asarray(drawing).copy();visible_tree=np.all(support==255,axis=2);registered[visible_tree]=np.asarray(tree_drawing)[visible_tree];drawing=Image.fromarray(registered)
    drawing.save(folder/f'scene-{angle}-registered.png')
    identities={triangle['identity'] for triangle in source.triangles}
    painter.apply_source_registered_field(source,source.images,camera,np.asarray(drawing),identities,painted_masks=painted,preserve_painted=previous_state is not None and not revise_visible)
    restore_observed_road_paint(source,runtime)
    painter.pad_painted_uv_charts(source,source.images,painted)
    state=folder/f'scene-{angle}-bound-state.npz'
    np.savez(state,**{f'image_{i}':image for i,image in enumerate(source.images)},**{f'painted_{i}':mask for i,mask in enumerate(painted)})
    originals=source.images
    for target in views:
        target_angle=target['camera']['angle']
        rgb,_=painter.render(source,target['camera']);Image.fromarray(rgb).save(folder/f'scene-{angle}-bound-view-{target_angle}.png')
        source.images=[np.repeat((mask.astype(np.uint8)*255)[:,:,None],3,axis=2) for mask in painted]
        labels,_=painter.render(source,target['camera'])
        supported=np.all(labels==255,axis=2)
        Image.fromarray(np.repeat((supported.astype(np.uint8)*255)[:,:,None],3,axis=2)).save(folder/f'scene-{angle}-authored-support-view-{target_angle}.png')
        source.images=originals
    painter.m.save_json(folder/f'scene-{angle}-binding.json',{'authorship':'Written by AI on 2026-10-25 by model GPT-6','status':'Actual original-geometry complete-scene bake; not art acceptance','drawing':str(drawing_path.resolve()),'drawingSha256':painter.m.digest(drawing_path.read_bytes()),'camera':camera,'drawingPixelsPerMetre':pixels_per_metre,'previousState':str(previous_state) if previous_state else None,'alreadyAuthoredTexels':'Visible surfaces revised coherently; occluded prior artwork retained' if revise_visible else ('Preserved unchanged' if previous_state else 'First authored view'),'unseenSurfaces':'Original source material or retained previous drawing; not claimed newly illustrated','context':source.context})
    print(state,flush=True)


def export_context(source,painted,folder):
    """Export original context triangles with exact feature/instance ownership."""
    folder.mkdir(parents=True,exist_ok=True)
    from collections import defaultdict
    groups=defaultdict(list)
    for index,triangle in enumerate(source.triangles):
        if triangle.get('contextKind'):groups[(triangle['contextKind'],triangle['identity'],triangle['image'])].append(index)
    document={'asset':{'version':'2.0','generator':'Source-bound complete scene compiler'},'scene':0,'scenes':[{'nodes':[0]}],'nodes':[],'meshes':[],'materials':[],'textures':[],'images':[],'samplers':[{'magFilter':9728,'minFilter':9987,'wrapS':33071,'wrapT':33071}],'bufferViews':[],'accessors':[],'extensionsUsed':['CESIUM_RTC'],'extensions':{'CESIUM_RTC':{'center':source.anchor_centre.tolist()}}}
    matrix=np.eye(4);matrix[:3,:3]=source.anchor_rotation;document['nodes'].append({'matrix':matrix.T.ravel().tolist(),'children':[]})
    binary=bytearray();image_map={};ownership=[]
    def accessor(values,kind,components):
        binary.extend(b'\0'*((-len(binary))%4));start=len(binary);data=values.astype('<f4').tobytes();binary.extend(data)
        document['bufferViews'].append({'buffer':0,'byteOffset':start,'byteLength':len(data),'target':34962})
        item={'bufferView':len(document['bufferViews'])-1,'componentType':5126,'count':len(values),'type':kind}
        if kind=='VEC3':item.update(min=values.min(0).tolist(),max=values.max(0).tolist())
        document['accessors'].append(item);return len(document['accessors'])-1
    for (kind,identity,image_index),faces in groups.items():
        if not painted[image_index].any():continue
        if image_index not in image_map:
            uri=f'context-image-{image_index}.png';Image.fromarray(source.images[image_index]).save(folder/uri)
            image_map[image_index]=len(document['images']);document['images'].append({'uri':uri});document['textures'].append({'source':image_map[image_index],'sampler':0})
            document['materials'].append({'doubleSided':True,'pbrMetallicRoughness':{'baseColorTexture':{'index':image_map[image_index]},'metallicFactor':0,'roughnessFactor':1}})
        positions=source.positions[faces].reshape(-1,3);uv=np.array([source.triangles[i]['uv'] for i in faces]).reshape(-1,2)
        primitive={'attributes':{'POSITION':accessor(positions,'VEC3',3),'TEXCOORD_0':accessor(uv,'VEC2',2)},'material':image_map[image_index],'extras':{'sourceIdentity':identity,'contextKind':kind,'sourceTriangleIndices':faces,('sourceFeatureId' if kind=='ground' else 'sourceTreeId'):identity.removeprefix('BGT_') if kind=='ground' else identity}}
        mesh=len(document['meshes']);document['meshes'].append({'name':identity,'primitives':[primitive]});node=len(document['nodes']);document['nodes'].append({'mesh':mesh,'name':identity});document['nodes'][0]['children'].append(node)
        ownership.append({'identity':identity,'kind':kind,'mesh':mesh,'primitive':0,'sourceTriangleIndices':faces,'image':image_index})
    document['buffers']=[{'byteLength':len(binary)}]
    asset=folder/'source-bound-context.glb';asset.write_bytes(painter.m.appearance.pack_glb(document,binary))
    painter.m.save_json(folder/'context-identities.json',{'authorship':'Written by AI on 2026-10-25 by model GPT-6','geometry':'Original retained feature/prototype triangles and original instance transforms, new UV charts only for trees','geometryAsset':asset.name,'geometrySha256':painter.m.digest(asset.read_bytes()),'rootMatrixColumnMajor':matrix.T.ravel().tolist(),'rtcECEF':source.anchor_centre.tolist(),'features':ownership,'sourceContext':source.context})


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('buildings',type=Path);parser.add_argument('runtime',type=Path);parser.add_argument('folder',type=Path);parser.add_argument('angle',type=int);parser.add_argument('drawing',type=Path);parser.add_argument('--previous-state',type=Path);parser.add_argument('--views',type=Path);parser.add_argument('--export',action='store_true');args=parser.parse_args()
    source=composition.compose(args.buildings,args.runtime,args.folder)
    bind(source,args.folder,args.runtime,args.angle,args.drawing,args.previous_state,views_path=args.views)
    if args.export:
        saved=np.load(args.folder/f'scene-{args.angle}-bound-state.npz');painted=[saved[f'painted_{i}'] for i in range(len(source.images))]
        source.export_handoff(source.images,{t['identity'] for t in source.triangles},args.folder/'bound-complete-scene-buildings')
        export_context(source,painted,args.folder/'bound-complete-scene-context')
