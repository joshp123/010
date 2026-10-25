#!/usr/bin/env python3
"""Join retained municipal buildings, surveyed ground and inventory tree instances.
Written by AI on 2026-10-25 by model GPT-6.
"""
import argparse, gzip, hashlib, importlib.util, json, struct, urllib.request
from pathlib import Path
import numpy as np
from PIL import Image
from pyproj import Transformer

spec=importlib.util.spec_from_file_location('painter',Path(__file__).with_name('source-view-painter.py'))
painter=importlib.util.module_from_spec(spec);spec.loader.exec_module(painter)


def runtime_camera(source,latitude,longitude,vertical_span,bearing,aspect=1,size=2304,runtime_origin=(51.915,4.49)):
    """Observe exact map focus/direction; square context contains its viewport."""
    origin_latitude,origin_longitude=np.radians(runtime_origin)
    east=np.array([-np.sin(origin_longitude),np.cos(origin_longitude),0])
    up=np.array([np.cos(origin_latitude)*np.cos(origin_longitude),np.cos(origin_latitude)*np.sin(origin_longitude),np.sin(origin_latitude)])
    south=np.array([np.sin(origin_latitude)*np.cos(origin_longitude),np.sin(origin_latitude)*np.sin(origin_longitude),-np.cos(origin_latitude)])
    earth_to_gltf=np.array([[1.,0.,0.],[0.,0.,1.],[0.,-1.,0.]])
    local_from_earth=source.anchor_rotation.T@earth_to_gltf
    map_to_source=local_from_earth@np.stack([east,up,south],axis=1)
    radians=np.radians(bearing);toward=map_to_source@np.array([np.sin(radians),1/np.sqrt(2),np.cos(radians)]);toward/=np.linalg.norm(toward)
    right=map_to_source@np.array([np.cos(radians),0,-np.sin(radians)]);image_up=np.cross(toward,right)
    focus=np.array(Transformer.from_crs(4979,4978,always_xy=True).transform(longitude,latitude,0))
    span=vertical_span*max(1,aspect);scale=size/span;viewport=np.array([vertical_span*aspect,vertical_span])*scale
    return {'centre':(local_from_earth@(focus-source.anchor_centre)).tolist(),'basis':np.stack([right,image_up,toward],axis=1).tolist(),'scale':scale,'mid':[0,0],'size':size,'angle':bearing,'elevation':float(np.degrees(np.arctan(1/np.sqrt(2)))),'runtimeFocus':{'lat':latitude,'lon':longitude,'height':0},'runtimeVerticalSpan':vertical_span,'runtimeAspect':aspect,'runtimeOrigin':list(runtime_origin),'runtimeCropBounds':np.r_[((size-viewport)/2),((size+viewport)/2)].tolist()}


def compose(buildings, runtime, folder):
    source=painter.load_source(buildings)
    building_triangle_count=len(source.triangles)
    earth_to_gltf=np.array([[1.,0.,0.],[0.,0.,1.],[0.,-1.,0.]])
    def from_earth(points):
        return (points-source.anchor_centre)@earth_to_gltf.T@source.anchor_rotation

    ground_directory=runtime/'work/public-space-neighbourhood'
    metadata=json.loads((ground_directory/'source-mask.json').read_text())
    ortho=runtime/'source-data/public-space-neighbourhood/adjoining-neighbourhood-2026.jpg'
    ground_image=len(source.images);source.images.append(np.asarray(Image.open(ortho).convert('RGB')).copy())
    bounds=np.array(metadata['boundsRD']);span=bounds[2:]-bounds[:2]
    native_ground=gzip.decompress((runtime/'source-data/public-space-pilot/33577-6934.b3dm.gz').read_bytes())
    assert hashlib.sha256(native_ground).hexdigest()==metadata['sourceDecodedSha256']
    _,_,ground_batch,_=next(painter.m.appearance.b3dm_parts(native_ground))
    ground_features={i:{'id':identity,'attributes':ground_batch['attributes'][i]} for i,identity in enumerate(ground_batch['id'])}
    to_geographic=Transformer.from_crs(28992,4326,always_xy=True)
    to_earth=Transformer.from_crs(4979,4978,always_xy=True)
    ground_count=0
    for record in json.loads((ground_directory/'source-triangles.json').read_text()):
        feature=ground_features.get(record['batchId'])
        if feature is None:continue
        kind=feature['attributes'].get('KLASSE_IMG','').lower()
        # Include original building-base/partition surfaces as context, too.
        # Their retained footprints/heights are not inferred private-court floors.
        if kind not in {'pand','scheiding','kunstwerkdeel','weginrichtingselement','overbruggingsdeel','wegdeel','ondersteunend wegdeel','begroeid terreindeel','onbegroeid terreindeel','waterdeel','ondersteunend waterdeel'}:continue
        rd=np.asarray(record['rd'])
        if np.any(rd[:,2]<-90):continue  # Native -99.99 missing-height sentinel.
        lon,lat=to_geographic.transform(rd[:,0],rd[:,1]);earth=np.array(to_earth.transform(lon,lat,rd[:,2])).T
        uv=np.c_[(rd[:,0]-bounds[0])/span[0],(bounds[3]-rd[:,1])/span[1]]
        source.triangles.append({'positions':from_earth(earth),'uv':uv,'image':ground_image,'identity':'BGT_'+str(feature['id']),'contextKind':'ground','sourceFeature':feature['id']})
        ground_count+=1

    tree_root='https://www.3drotterdam.nl/datasource-data/b9294d5b-79e0-4744-ac88-b61e3e90d5bc/'
    raw=(folder/'15_33577_6934.cmpt').read_bytes();offset=16;tree_records=[];prototypes={}
    assert hashlib.sha256(raw).hexdigest()==json.loads((folder/'tree-source.json').read_text())['decodedSha256']
    to_rd=Transformer.from_crs(4978,28992,always_xy=True)
    for _ in range(struct.unpack_from('<I',raw,12)[0]):
        child=raw[offset:];length,fj,fb,bj,bb,fmt=struct.unpack_from('<6I',child,8)
        table=json.loads(child[32:32+fj]);binary=child[32+fj:32+fj+fb];batch=json.loads(child[32+fj+fb:32+fj+fb+bj]);uri=child[32+fj+fb+bj+bb:length].decode().strip('\x00 ');offset+=length
        def attribute(name,dtype,components=3):
            return np.frombuffer(binary,dtype,table['INSTANCES_LENGTH']*components,table[name]['byteOffset']).reshape(-1,components)
        positions=attribute('POSITION_QUANTIZED','<u2')/65535*np.array(table['QUANTIZED_VOLUME_SCALE'])+table['QUANTIZED_VOLUME_OFFSET']
        scale=attribute('SCALE_NON_UNIFORM','<f4');up=attribute('NORMAL_UP','<f4');right=attribute('NORMAL_RIGHT','<f4')
        xx,yy,_=to_rd.transform(*positions.T)
        selected=np.flatnonzero((xx>=bounds[0])&(xx<=bounds[2])&(yy>=bounds[1])&(yy<=bounds[3]))
        if not len(selected):continue
        filename=Path(uri).name;path=folder/filename
        if not path.exists():
            data=urllib.request.urlopen(tree_root+filename,timeout=45).read();data=gzip.decompress(data) if data[:2]==b'\x1f\x8b' else data;path.write_bytes(data)
        if filename not in prototypes:
            data=path.read_bytes();size=struct.unpack_from('<I',data,12)[0];doc=json.loads(data[20:20+size]);buf=data[28+size:];faces=[]
            def visit(index,parent):
                node=doc['nodes'][index];matrix=parent@np.array(node.get('matrix',np.eye(4).T.ravel())).reshape(4,4).T
                if 'mesh' in node:
                    for primitive in doc['meshes'][node['mesh']]['primitives']:
                        points=painter.m.appearance.accessor(doc,buf,primitive['attributes']['POSITION']);points=(np.c_[points,np.ones(len(points))]@matrix.T)[:,:3]
                        indices=painter.m.appearance.accessor(doc,buf,primitive['indices'])[:,0].reshape(-1,3) if 'indices' in primitive else np.arange(len(points)).reshape(-1,3)
                        faces.extend(points[indices])
                for child_index in node.get('children',[]):visit(child_index,matrix)
            for index in doc['scenes'][doc.get('scene',0)]['nodes']:visit(index,np.eye(4))
            prototypes[filename]=np.asarray(faces)
        prototype=prototypes[filename];adjust=np.array([[1,0,0],[0,0,-1],[0,1,0]])
        for index in selected:
            rotation=np.column_stack([right[index],up[index],np.cross(right[index],up[index])]);linear=rotation@np.diag(scale[index])@adjust
            world=prototype@linear.T+positions[index];local=from_earth(world)
            part=batch['attributes'][index]['tree_part'];colour=[84,109,61] if part=='kruin' else [104,87,67]
            # New chart coordinates preserve source triangles, not generic painted crowns.
            cells=int(np.ceil(np.sqrt(len(local))));side=cells*16;image=len(source.images);source.images.append(np.full((side,side,3),colour,np.uint8))
            for face_index,points in enumerate(local):
                x=(face_index%cells)*16+1;y=(face_index//cells)*16+1;uv=np.array([[x,y],[x+13,y],[x,y+13]])/side
                source.triangles.append({'positions':points,'uv':uv,'image':image,'identity':str(batch['id'][index]),'contextKind':'tree','treePart':part})
            tree_records.append({'identity':batch['id'][index],'prototype':filename,'part':part,'originalInstance':int(index),'image':image,'sourceTriangles':len(local),'sourceAttributes':batch['attributes'][index],'originalPositionECEF':positions[index].tolist(),'prototypeToECEFLinear':linear.tolist()})
    source.positions=np.array([t['positions'] for t in source.triangles]);source.normals=np.cross(source.positions[:,1]-source.positions[:,0],source.positions[:,2]-source.positions[:,0]);source.areas=np.linalg.norm(source.normals,axis=1)/2;source.normals/=np.maximum(source.areas[:,None]*2,1e-12)
    source.context={'buildingTriangleCount':building_triangle_count,'groundTriangles':ground_count,'groundImage':ground_image,'groundBoundsRD':bounds.tolist(),'groundSourceSha256':metadata['sourceDecodedSha256'],'orthophotoSha256':metadata['orthophotoSha256'],'treeInstances':tree_records,'treeSourceSha256':hashlib.sha256(raw).hexdigest(),'prototypes':{name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in prototypes}}
    return source


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('buildings',type=Path);parser.add_argument('runtime',type=Path);parser.add_argument('folder',type=Path);parser.add_argument('--cameras',required=True,type=Path);args=parser.parse_args()
    source=compose(args.buildings,args.runtime,args.folder);plan=json.loads(args.cameras.read_text());views=[]
    for view in plan['views']:
        if view['name'] not in ['view-120-28','view-300-28']:continue
        camera=view['camera'];rgb,depth=painter.render(source,camera);geometry,_=painter.render(source,camera,True)
        for suffix,data in [('source',rgb),('geometry',geometry)]:Image.fromarray(data).save(args.folder/(view['name']+'-'+suffix+'.png'))
        np.save(args.folder/(view['name']+'-depth.npy'),depth);views.append({**view,'source':view['name']+'-source.png','geometryGuide':view['name']+'-geometry.png','depth':view['name']+'-depth.npy'})
    painter.m.save_json(args.folder/'views.json',{'authorship':'Written by AI on 2026-10-25 by model GPT-6','status':'Complete evidenced source composition; no generated context or art acceptance','views':views,'context':source.context})
    print(json.dumps({'groundTriangles':source.context['groundTriangles'],'treeInstances':len(source.context['treeInstances']),'triangles':len(source.triangles)}))
