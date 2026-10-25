#!/usr/bin/env python3
"""Source-bound surface interpretation and paint compilation.

Written by AI on 2026-10-24 by model GPT-6.
Surface extraction and raster/UV plumbing are reusable. Observations and drawing
choices are separate retained data. No generated image supplies architecture.
"""
import argparse, copy, gzip, hashlib, importlib.util, io, json, math, struct
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('appearance', ROOT/'scripts/prepare-building-appearance.py')
appearance = importlib.util.module_from_spec(spec); spec.loader.exec_module(appearance)

def digest(data): return hashlib.sha256(data).hexdigest()
def save_json(path, value): path.write_text(json.dumps(value, indent=2)+'\n')

class Source:
    def __init__(self, path):
        self.path = path; self.raw = path.read_bytes()
        if self.raw[:2] == b'\x1f\x8b': self.raw = gzip.decompress(self.raw)
        self.batch = None; self.feature = None
        if self.raw[:4] == b'b3dm':
            self.doc, self.binary, self.batch, self.feature = next(appearance.b3dm_parts(self.raw))
        else:
            size = struct.unpack_from('<I', self.raw, 12)[0]
            self.doc = json.loads(self.raw[20:20+size]); self.binary = self.raw[28+size:]
        self.images = []
        for image in self.doc['images']:
            if 'uri' in image: data = (path.parent/image['uri']).read_bytes()
            else:
                view = self.doc['bufferViews'][image['bufferView']]
                start = view.get('byteOffset', 0); data = self.binary[start:start+view['byteLength']]
            self.images.append(np.array(Image.open(io.BytesIO(data)).convert('RGB')))
        self.triangles = []; self.primitives = []
        for mesh_index, mesh in enumerate(self.doc['meshes']):
            for primitive_index, primitive in enumerate(mesh['primitives']):
                attributes = primitive['attributes']
                positions = self.accessor(attributes['POSITION'])
                indices = self.accessor(primitive['indices'])[:,0].reshape(-1,3) if 'indices' in primitive else np.arange(len(positions)).reshape(-1,3)
                batches = self.accessor(attributes['_BATCHID'])[:,0] if '_BATCHID' in attributes else np.zeros(len(positions), int)
                material = self.doc['materials'][primitive.get('material',0)]
                texture = material.get('pbrMetallicRoughness',{}).get('baseColorTexture')
                if texture is None: continue
                image_index = self.doc['textures'][texture['index']]['source']
                uv = self.accessor(attributes['TEXCOORD_0'])
                for face in indices:
                    bid = int(batches[face[0]])
                    identity = str(mesh.get('extras',{}).get('bagId', bid))
                    if self.batch is not None: identity = str(self.batch['id'][bid]).removeprefix('BAG_')
                    self.triangles.append({'positions':positions[face].astype(float), 'uv':uv[face].astype(float), 'image':image_index, 'batch':bid, 'identity':identity, 'mesh':mesh_index, 'primitive':primitive_index})
        self.positions = np.array([t['positions'] for t in self.triangles])
        self.normals = np.cross(self.positions[:,1]-self.positions[:,0], self.positions[:,2]-self.positions[:,0])
        self.areas = np.linalg.norm(self.normals,axis=1)/2
        self.normals /= np.maximum(self.areas[:,None]*2,1e-12)
    def accessor(self, index): return appearance.accessor(self.doc,self.binary,index).copy()

    def surfaces(self,normal_cosine=.9995):
        """Connected coplanar faces, independent of compass direction and size."""
        edge_faces = {}; neighbours = [set() for _ in self.triangles]
        for index, triangle in enumerate(self.triangles):
            corners = [tuple(np.round(p,4)) for p in triangle['positions']]
            for first,second in ((0,1),(1,2),(2,0)):
                key=(triangle['identity'], *sorted([corners[first],corners[second]]))
                for other in edge_faces.get(key,[]):
                    if np.dot(self.normals[index],self.normals[other])>normal_cosine:
                        neighbours[index].add(other); neighbours[other].add(index)
                edge_faces.setdefault(key,[]).append(index)
        remaining = set(range(len(self.triangles))); groups=[]
        while remaining:
            first=min(remaining); group=[]; pending=[first]; remaining.remove(first)
            while pending:
                face=pending.pop();group.append(face)
                for other in neighbours[face] & remaining: remaining.remove(other);pending.append(other)
            if self.areas[group].sum()>0.005:groups.append(sorted(group))
        groups.sort(key=lambda g:(self.triangles[g[0]]['identity'],-self.areas[g].sum(),g[0]))
        return groups

    def panel(self, faces, pixels_per_metre=40, maximum=1400):
        points=self.positions[faces].reshape(-1,3); normal=np.average(self.normals[faces],axis=0,weights=self.areas[faces]);normal/=np.linalg.norm(normal)
        vertical=np.array([0.,1.,0.]); right=np.cross(vertical,normal)
        if np.linalg.norm(right)<.05: right=np.array([1.,0.,0.])
        right/=np.linalg.norm(right);up=np.cross(normal,right)
        centre=(points.min(0)+points.max(0))/2;basis=np.stack([right,up,normal],axis=1)
        projected=(points-centre)@basis; extent=np.ptp(projected[:,:2],axis=0)
        scale=min(pixels_per_metre,(maximum-16)/max(extent.max(),.01))
        width,height=np.maximum(16,np.ceil(extent*scale).astype(int)+16)
        rgb=np.full((height,width,3),235,np.uint8);mask=np.zeros((height,width),bool)
        for index in faces:
            t=self.triangles[index];xy=((t['positions']-centre)@basis)[:,:2]*[scale,-scale]+[width/2,height/2]
            for x0,y0,x1,y1,weights,inside in raster_triangle(xy,width,height):
                image=self.images[t['image']];coords=weights@t['uv'];px=np.floor(coords*[image.shape[1],image.shape[0]]).astype(int);px[:,:,0]=px[:,:,0].clip(0,image.shape[1]-1);px[:,:,1]=px[:,:,1].clip(0,image.shape[0]-1)
                rgb[y0:y1+1,x0:x1+1][inside]=image[px[:,:,1][inside],px[:,:,0][inside]];mask[y0:y1+1,x0:x1+1]|=inside
        return Image.fromarray(rgb),mask,{'centre':centre.tolist(),'basis':basis.tolist(),'pixelsPerMetre':float(scale),'size':[int(width),int(height)],'normal':normal.tolist()}

    def export(self, images, output):
        doc=copy.deepcopy(self.doc);binary=bytearray(self.binary)
        for index,image in enumerate(images):
            stream=io.BytesIO();Image.fromarray(image).save(stream,format='PNG');data=stream.getvalue();binary.extend(b'\0'*((-len(binary))%4));offset=len(binary);binary.extend(data)
            doc['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':len(data)})
            doc['images'][index]={'bufferView':len(doc['bufferViews'])-1,'mimeType':'image/png'}
        if self.feature is not None:
            doc.setdefault('extensions',{})['CESIUM_RTC']={'center':self.feature['RTC_CENTER']}
            doc.setdefault('extensionsUsed',[])
            if 'CESIUM_RTC' not in doc['extensionsUsed']:doc['extensionsUsed'].append('CESIUM_RTC')
        doc.setdefault('extras',{}).update({'sourceBoundInterpretation':True,'sourceSha256':digest(self.raw),'geometryAndUV':'Original accessors and binary prefix retained exactly','appearance':'Review candidate, no acceptance claim'})
        doc['buffers']=[{'byteLength':len(binary)}];output.write_bytes(appearance.pack_glb(doc,binary))


    def export_handoff(self, images, identities, folder):
        """Select complete observed buildings; preserve source vertices, UVs and transforms."""
        folder.mkdir(parents=True, exist_ok=True)
        doc=copy.deepcopy(self.doc);binary=bytearray(self.binary)
        selected_batches={index for index,identity in enumerate(self.batch['id']) if str(identity).removeprefix('BAG_') in identities}
        for mesh in doc['meshes']:
            kept=[]
            for primitive in mesh['primitives']:
                ids=appearance.accessor(self.doc,self.binary,primitive['attributes']['_BATCHID'])[:,0]
                indices=appearance.accessor(self.doc,self.binary,primitive['indices'])[:,0].reshape(-1,3)
                selected=indices[np.isin(ids[indices[:,0]],list(selected_batches))].astype('<u4').ravel()
                if not len(selected):continue
                binary.extend(b'\0'*((-len(binary))%4));offset=len(binary);binary.extend(selected.tobytes())
                doc['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':selected.nbytes,'target':34963})
                doc['accessors'].append({'bufferView':len(doc['bufferViews'])-1,'componentType':5125,'count':len(selected),'type':'SCALAR','min':[int(selected.min())],'max':[int(selected.max())]})
                primitive['indices']=len(doc['accessors'])-1;kept.append(primitive)
            mesh['primitives']=kept
        external=[]
        for index,pixels in enumerate(images):
            uri=f'painted-atlas-{index}.png';Image.fromarray(pixels).save(folder/uri);doc['images'][index]={'uri':uri}
            external.append({'uri':uri,'sha256':digest((folder/uri).read_bytes()),'dimensions':[pixels.shape[1],pixels.shape[0]]})
        rtc=self.feature['RTC_CENTER'];doc.setdefault('extensions',{})['CESIUM_RTC']={'center':rtc}
        doc.setdefault('extensionsUsed',[])
        if 'CESIUM_RTC' not in doc['extensionsUsed']:doc['extensionsUsed'].append('CESIUM_RTC')
        doc['buffers']=[{'byteLength':len(binary)}];asset=folder/'source-bound-row.glb';asset.write_bytes(appearance.pack_glb(doc,binary))
        save_json(folder/'georeference-and-identities.json',{'authorship':'Written by AI on 2026-10-24 by model GPT-6','geometry_asset':asset.name,'geometry_asset_sha256':digest(asset.read_bytes()),'root_node_matrix_column_major':doc['nodes'][0]['matrix'],'rtc_ecef_m':rtc,'identity_namespace':'BAG','batch_identity':[{'batchId':index,'sourceId':'BAG_'+str(self.batch['id'][index]).removeprefix('BAG_')} for index in sorted(selected_batches)],'external_images':external,'triangles':sum(doc['accessors'][p['indices']]['count']//3 for mesh in doc['meshes'] for p in mesh['primitives']),'source_decoded_sha256':digest(self.raw),'source_file':str(self.path.resolve()),'source_attribution':'Gemeente Rotterdam, CC BY 4.0','status':'Source-bound visual candidate; no acceptance claim'})

def raster_triangle(xy,width,height):
    x0,y0=np.maximum(np.floor(xy.min(0)).astype(int),0);x1,y1=np.minimum(np.ceil(xy.max(0)).astype(int),[width-1,height-1]);matrix=np.vstack([xy.T,np.ones(3)])
    if x1<x0 or y1<y0 or abs(np.linalg.det(matrix))<1e-9:return
    yy,xx=np.mgrid[y0:y1+1,x0:x1+1];weights=np.stack([xx+.5,yy+.5,np.ones_like(xx)],-1)@np.linalg.inv(matrix).T
    yield x0,y0,x1,y1,weights,(weights>=-1e-7).all(-1)

def extract(source,folder):
    folder.mkdir(parents=True,exist_ok=True);groups=source.surfaces();records=[];thumbs=[]
    for index,faces in enumerate(groups):
        image,mask,frame=source.panel(faces);stem=f'surface-{index:04d}';image.save(folder/(stem+'.png'));Image.fromarray(mask.astype('uint8')*255).save(folder/(stem+'-mask.png'))
        record={'id':stem,'identity':source.triangles[faces[0]]['identity'],'batchId':source.triangles[faces[0]]['batch'],'triangles':faces,'areaSquareMetres':float(source.areas[faces].sum()),'frame':frame};records.append(record)
        if record['areaSquareMetres']>=4:
            thumb=Image.new('RGB',(300,260),'#e9eae5');small=image.copy();small.thumbnail((284,220));thumb.paste(small,((300-small.width)//2,28));ImageDraw.Draw(thumb).text((6,5),f'{index}: {record["identity"][-6:]} {record["areaSquareMetres"]:.1f}m2',fill='black');thumbs.append(thumb)
    save_json(folder/'surfaces.json',{'source':str(source.path),'sourceSha256':digest(source.raw),'coordinateMeaning':'Planar extraction of existing UV photograph; does not repair distortion within source photography','surfaces':records})
    for start in range(0,len(thumbs),24):
        subset=thumbs[start:start+24];sheet=Image.new('RGB',(1800,260*math.ceil(len(subset)/6)),'white')
        for i,thumb in enumerate(subset):sheet.paste(thumb,((i%6)*300,(i//6)*260))
        sheet.save(folder/f'source-sheet-{start//24:02d}.jpg')
    print(f'{len(records)} connected surfaces, {len(thumbs)} review panels')

def polygon_mask(shape,polygon):
    image=Image.new('L',(shape[1],shape[0]));ImageDraw.Draw(image).polygon([tuple(p) for p in polygon],fill=255);return np.array(image)>0

def paint_region(source,mask,material,scale,materials):
    """Drawing inside source-bound regions. No spatial feature synthesis."""
    spec=materials[material]
    if 'exemplar' in spec:return illustrated_material(mask.shape,spec,scale)
    if 'observedPalette' in spec:
        # Semantic paint uses existing pixel evidence for ALL structural boundaries.
        # The material recipe names source colour observations and illustrated swatches;
        # no model-drawn feature is sampled into this branch.
        smooth=np.array(Image.fromarray(source).filter(ImageFilter.MedianFilter(3)),float)
        prototypes=np.array([entry['sourceColour'] for entry in spec['observedPalette']],float)
        intensity=smooth.mean(2);chroma=smooth-intensity[:,:,None]
        proto_intensity=prototypes.mean(1);proto_chroma=prototypes-proto_intensity[:,None]
        distances=((chroma[:,:,None,:]-proto_chroma[None,None,:,:])**2).sum(3)*2+((intensity[:,:,None]-proto_intensity)**2)
        labels=distances.argmin(2);result=np.zeros_like(source)
        for index,entry in enumerate(spec['observedPalette']):
            chosen=mask&(labels==index)
            component=paint_region(source,chosen,entry['paint'],scale,materials)
            result[chosen]=component[chosen]
        return result
    base=np.array(spec['colour'],float);lum=source.astype(float)@np.array([.2126,.7152,.0722]);smoothed=ndimage.gaussian_filter(lum,.65)
    if mask.any():median=np.median(smoothed[mask])
    else:median=128
    # Material-local tonal planes preserve observed small relief without carrying photographic RGB.
    tone=np.clip(np.round((smoothed-median)/spec.get('toneStep',22)),-2,2)
    amplitude=spec.get('toneAmplitude',6);result=base+tone[:,:,None]*amplitude
    grain=spec.get('grain',0)
    if grain:
        yy,xx=np.indices(mask.shape);noise=np.sin(xx*.41+yy*.17)*np.sin(yy*.57-xx*.13);result+=noise[:,:,None]*grain
    # Fine source-supported edges, clipped inside each observation; never regular window grids.
    if spec.get('sourceLines',True):
        grad=np.hypot(ndimage.sobel(smoothed,0),ndimage.sobel(smoothed,1))/8
        edge=(grad>spec.get('edgeThreshold',20))&ndimage.binary_erosion(mask,iterations=1)
        result[edge]*=spec.get('edgeShade',.82)
    return result.clip(0,255).astype('uint8')

def feature_candidates(image, valid, minimum_width=7):
    """Photographic dark/bright connected regions proposed for model interpretation."""
    rgb=np.asarray(image,float);light=rgb@np.array([.2126,.7152,.0722]);chroma=rgb.max(2)-rgb.min(2)
    dark=(light<82)&(chroma<58)&valid
    dark=ndimage.binary_closing(dark,structure=np.ones((3,3)))
    labels,count=ndimage.label(dark);candidates=[]
    for index,slices in enumerate(ndimage.find_objects(labels)):
        if slices is None:continue
        ys,xs=slices;w=xs.stop-xs.start;h=ys.stop-ys.start;area=(labels[slices]==index+1).sum()
        if w<minimum_width or h<9 or area<45 or area/(w*h)<.20:continue
        if w>image.width*.65 and h>image.height*.4:continue
        candidates.append({'id':f'feature-{len(candidates):03d}','bounds':[xs.start,ys.start,xs.stop,ys.stop],'areaPixels':int(area),'darkLabel':index+1})
    bright=(light>155)&(chroma<45)&valid
    bright=ndimage.binary_closing(bright,structure=np.ones((2,3)))
    return candidates,labels,bright

def propose_features(folder):
    manifest=json.loads((folder/'surfaces.json').read_text());records=[];thumbs=[]
    for record in manifest['surfaces']:
        if record['areaSquareMetres']<4:continue
        image=Image.open(folder/(record['id']+'.png')).convert('RGB');valid=np.array(Image.open(folder/(record['id']+'-mask.png')))>0
        features,labels,bright=feature_candidates(image,valid);annotated=image.copy();draw=ImageDraw.Draw(annotated)
        for feature in features:
            x0,y0,x1,y1=feature['bounds'];draw.rectangle((x0,y0,x1,y1),outline='#ff5a00',width=2);draw.text((x0,y0-10),feature['id'][-3:],fill='#ff3300')
        annotated.save(folder/(record['id']+'-features.png'))
        records.append({'surface':record['id'],'features':features})
        thumb=Image.new('RGB',(360,360),'#e9eae5');annotated.thumbnail((344,328));thumb.paste(annotated,((360-annotated.width)//2,25));ImageDraw.Draw(thumb).text((6,5),record['id'],fill='black');thumbs.append(thumb)
    save_json(folder/'feature-candidates.json',{'authorship':'Written by AI on 2026-10-24 by model GPT-6','meaning':'Source connected-component proposals only. Acceptance and architectural role must be supplied by model observations. No component is automatically an opening.','surfaces':records})
    for start in range(0,len(thumbs),12):
        subset=thumbs[start:start+12];sheet=Image.new('RGB',(1440,360*math.ceil(len(subset)/4)),'white')
        for index,thumb in enumerate(subset):sheet.paste(thumb,((index%4)*360,(index//4)*360))
        sheet.save(folder/f'feature-sheet-{start//12:02d}.jpg')
    print('proposed source connected features for',len(records),'surfaces')

def illustrated_material(shape,spec,scale):
    exemplar=Image.open(ROOT/spec['exemplar']).convert('RGB');crop=spec['crop'];exemplar=exemplar.crop(tuple(crop))
    physical_width=spec.get('exemplarWidthMetres',4);target=max(8,round(physical_width*scale));exemplar=exemplar.resize((target,max(8,round(target*exemplar.height/exemplar.width))),Image.Resampling.LANCZOS)
    texture=np.array(exemplar)
    if 'tintMean' in spec:texture=np.clip(texture.astype(float)-texture.mean(axis=(0,1))+np.array(spec['tintMean']),0,255).astype('uint8')
    yy,xx=np.indices(shape);return texture[yy%texture.shape[0],xx%texture.shape[1]].copy()

def draw_accepted_features(source,output,valid,decision,scale,materials):
    candidates,labels,bright=feature_candidates(Image.fromarray(source),valid);by_id={c['id']:c for c in candidates}
    if 'trim' in decision:
        trim=decision['trim'];rgb=source.astype(float);light=rgb@np.array([.2126,.7152,.0722]);mask=(light>trim['threshold'])&((rgb.max(2)-rgb.min(2))<trim['maximumChroma'])&valid
        components,count=ndimage.label(mask);sizes=np.bincount(components.ravel());mask&=sizes[components]>=trim['minimumArea'];mask=ndimage.binary_closing(mask,structure=np.ones((2,2)))&valid
        paint=illustrated_material(valid.shape,materials['stone-drawn'],scale);output[mask]=paint[mask]
    for feature_decision in decision.get('features',[]):
        members=feature_decision.get('candidates',[feature_decision.get('candidate')]);accepted=[by_id[name] for name in members]
        glass=np.isin(labels,[feature['darkLabel'] for feature in accepted])
        if 'observedEnvelope' in feature_decision:
            glass=polygon_mask(valid.shape,feature_decision['observedEnvelope'])&valid
        else:
            from skimage.morphology import convex_hull_image
            glass=convex_hull_image(glass)&valid
        ys,xs=np.where(glass)
        if not len(xs):continue
        x0,y0,x1,y1=xs.min(),ys.min(),xs.max(),ys.max();pad=feature_decision.get('frameWidthPixels',3)
        border=ndimage.binary_dilation(glass,iterations=pad)&~glass&valid
        frame_paint=illustrated_material(valid.shape,materials['stone-drawn'],scale);output[border]=frame_paint[border]
        exterior_shadow=ndimage.binary_dilation(glass,iterations=pad+1)&~ndimage.binary_dilation(glass,iterations=pad)&valid
        output[exterior_shadow]=[108,100,84]
        colour=np.array(materials[feature_decision.get('material','glass-drawn')]['colour']);yy,xx=np.indices(valid.shape)
        tone=((yy-y0)/max(1,y1-y0)*10).astype(int);paint=np.clip(colour[None,None,:]+tone[:,:,None],0,255).astype('uint8')
        # A few drawn reflection planes inside supported glass do not add openings.
        reflection=((xx-x0)/(max(1,x1-x0))>.68)&((xx-x0)/(max(1,x1-x0))<.79)
        paint[reflection]=np.clip(paint[reflection].astype(int)+[9,13,14],0,255)
        if 'paintExemplar' in feature_decision:
            exemplar=feature_decision['paintExemplar'];donor=Image.open(ROOT/exemplar['path']).convert('RGB').crop(tuple(exemplar['crop']))
            donor=np.array(donor.resize((x1-x0+1,y1-y0+1),Image.Resampling.LANCZOS));paint[y0:y1+1,x0:x1+1]=donor
        output[glass]=paint[glass]
        # Transoms/mullions are retained only where literal pale source bands span the opening.
        source_trim=bright&glass
        for y in range(y0+3,y1-3):
            span=glass[y].sum()
            if span and source_trim[y].sum()/span>.66:output[y,glass[y]]=frame_paint[y,glass[y]]
        for x in range(x0+3,x1-3):
            span=glass[:,x].sum()
            if span and source_trim[:,x].sum()/span>.75:output[glass[:,x],x]=frame_paint[glass[:,x],x]
    return output


def registered_paint_proposal(observation,source,valid):
    """Model-approved feature correspondences bind paint to source architecture."""
    binding=observation['proposalBinding'];proposal=Image.open(ROOT/binding['path']).convert('RGB');result=source.copy()
    if binding.get('independentRegions'):
        background=dict(binding['backgroundExemplar']);background['exemplar']=background.pop('path');result=illustrated_material(valid.shape,background,observation.get('pixelsPerMetre',40))
        for region in binding['independentRegions']:
            x0,y0,x1,y1=region['sourceBounds'];mask=polygon_mask(valid.shape,region.get('sourcePolygon',[[x0,y0],[x1,y0],[x1,y1],[x0,y1]]))&valid
            yy,xx=np.where(mask);inside=(xx>=x0)&(xx<x1)&(yy>=y0)&(yy<y1);xx=xx[inside];yy=yy[inside]
            if region.get('retainSource'):
                result[yy,xx]=source[yy,xx];continue
            if 'material' in region:
                pixels=illustrated_material(valid.shape,region['material'],observation.get('pixelsPerMetre',40));result[yy,xx]=pixels[yy,xx];continue
            px0,py0,px1,py1=region['proposalBounds']
            if 'sourceCore' in region:
                cx0,cy0,cx1,cy1=region['sourceCore'];dx0,dy0,dx1,dy1=region['proposalCore']
                px=np.interp(xx,[x0,cx0,cx1,x1],[px0,dx0,dx1,px1]);py=np.interp(yy,[y0,cy0,cy1,y1],[py0,dy0,dy1,py1])
            else:px=px0+(xx-x0)/(x1-x0)*(px1-px0);py=py0+(yy-y0)/(y1-y0)*(py1-py0)
            donor=np.asarray(Image.open(ROOT/region['paintPath']).convert('RGB')) if 'paintPath' in region else np.asarray(proposal);pixels=np.stack([ndimage.map_coordinates(donor[:,:,channel].astype(float),[py,px],order=1,mode='nearest') for channel in range(3)],axis=1).clip(0,255).astype('uint8')
            if region.get('architecturalFeatureOnly'):
                keep=(pixels.max(1).astype(int)-pixels.min(1).astype(int))<65;xx=xx[keep];yy=yy[keep];pixels=pixels[keep]
            result[yy,xx]=pixels
        result[~valid]=source[~valid];return result
    raise ValueError('A single global warp is rejected: independent source-bound architectural regions required')

def compile_art(source,folder,observations_path,materials_path):
    manifest=json.loads((folder/'surfaces.json').read_text());assert manifest['sourceSha256']==digest(source.raw)
    observations=json.loads(observations_path.read_text());materials=json.loads(materials_path.read_text())['materials'];records={r['id']:r for r in manifest['surfaces']}
    painted=[a.copy() for a in source.images];painted_panels=[]
    for observation in observations['surfaces']:
        record=records[observation['surface']];image=np.array(Image.open(folder/(record['id']+'.png')).convert('RGB'));valid=np.array(Image.open(folder/(record['id']+'-mask.png')))>0;output=image.copy();assigned=np.zeros(valid.shape,bool)
        for region in observation['regions']:
            mask=valid if region.get('wholeSurface') else polygon_mask(valid.shape,region['polygon'])&valid
            if region.get('evidence')=='invalid_projection':
                output[mask]=np.array(materials[region['material']]['colour'],np.uint8)
            else: output[mask]=paint_region(image,mask,region['material'],record['frame']['pixelsPerMetre'],materials)[mask]
            assigned|=mask
        if 'proposalBinding' in observation:output=registered_paint_proposal(observation,image,valid);assigned|=valid
        else:output=draw_accepted_features(image,output,valid,observation,record['frame']['pixelsPerMetre'],materials)
        Image.fromarray(output).save(folder/(record['id']+'-painted.png'));painted_panels.append(record['id'])
        frame=record['frame'];basis=np.array(frame['basis']);centre=np.array(frame['centre']);scale=frame['pixelsPerMetre'];width,height=frame['size']
        for index in record['triangles']:
            triangle=source.triangles[index];tex=painted[triangle['image']];h,w=tex.shape[:2];uv=triangle['uv']*[w,h]
            for x0,y0,x1,y1,weights,inside in raster_triangle(uv,w,h):
                points=weights@triangle['positions'];coords=((points-centre)@basis)[:,:,:2]*[scale,-scale]+[width/2,height/2];px=np.floor(coords).astype(int);px[:,:,0]=px[:,:,0].clip(0,width-1);px[:,:,1]=px[:,:,1].clip(0,height-1);apply=inside&assigned[px[:,:,1],px[:,:,0]]
                tex[y0:y1+1,x0:x1+1][apply]=output[px[:,:,1][apply],px[:,:,0][apply]]
    source.export(painted,folder/'painted.glb');source.export_handoff(painted,{o['identity'] for o in observations['surfaces']},folder/observations.get('handoffDirectory','bound-eight-house-row'));np.savez_compressed(folder/'painted-atlases.npz',**{f'image_{i}':a for i,a in enumerate(painted)})
    save_json(folder/'compiled.json',{'sourceSha256':digest(source.raw),'observationSha256':digest(observations_path.read_bytes()),'materialsSha256':digest(materials_path.read_bytes()),'outputSha256':digest((folder/'painted.glb').read_bytes()),'paintedSurfaces':painted_panels,'totalSurfaces':len(records),'unobservedSurfaces':'Unchanged municipal source','geometry':'Original binary prefix and accessors, original UVs and transforms retained','status':'Actual baked material candidate; requires street/courtyard review'})
    print('baked',len(painted_panels),'surfaces')

def render(source,folder,mode):
    images=source.images
    if mode=='painted':
        z=np.load(folder/'painted-atlases.npz');images=[z[f'image_{i}'] for i in range(len(source.images))]
    points=source.positions.reshape(-1,3);centre=(points.min(0)+points.max(0))/2;size=1400
    for angle in [30,120,210,300]:
        yaw=np.radians(angle);elev=np.radians(28);toward=np.array([np.sin(yaw)*np.cos(elev),np.sin(elev),np.cos(yaw)*np.cos(elev)]);right=np.array([np.cos(yaw),0,-np.sin(yaw)]);up=np.cross(toward,right);basis=np.stack([right,up,toward],axis=1);projected=(points-centre)@basis;scale=(size-64)/max(np.ptp(projected[:,:2],axis=0));mid=(projected[:,:2].max(0)+projected[:,:2].min(0))/2
        rgb=np.full((size,size,3),[232,234,229],np.uint8);depth=np.full((size,size),-np.inf)
        for index,triangle in enumerate(source.triangles):
            q=(triangle['positions']-centre)@basis;xy=(q[:,:2]-mid)*[scale,-scale]+size/2
            for x0,y0,x1,y1,weights,inside in raster_triangle(xy,size,size):
                zz=weights@q[:,2];valid=inside&(zz>depth[y0:y1+1,x0:x1+1]);image=images[triangle['image']];coords=weights@triangle['uv'];px=np.floor(coords*[image.shape[1],image.shape[0]]).astype(int);px[:,:,0]=px[:,:,0].clip(0,image.shape[1]-1);px[:,:,1]=px[:,:,1].clip(0,image.shape[0]-1)
                rgb[y0:y1+1,x0:x1+1][valid]=image[px[:,:,1][valid],px[:,:,0][valid]];depth[y0:y1+1,x0:x1+1][valid]=zz[valid]
        Image.fromarray(rgb).save(folder/f'{mode}-{angle}.png')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('operation',choices=['extract','propose','compile','render']);parser.add_argument('source',type=Path);parser.add_argument('output',type=Path);parser.add_argument('--observations',type=Path);parser.add_argument('--materials',type=Path);parser.add_argument('--mode',default='source',choices=['source','painted']);args=parser.parse_args();source=Source(args.source)
    if args.operation=='extract':extract(source,args.output)
    elif args.operation=='propose':propose_features(args.output)
    elif args.operation=='compile':compile_art(source,args.output,args.observations,args.materials)
    else:render(source,args.output,args.mode)
