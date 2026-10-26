#!/usr/bin/env -S .devenv/profile/bin/python
"""Written by AI on 2026-10-26 by model GPT-6 Astra.
C3: native ChatGPT contact-sheet perception, source-only masks and edge checks.
"""
import argparse
import fcntl
import os
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from skimage.color import rgb2lab
from skimage.filters import sobel
import tomllib
CLI = '/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex'
REPOSITORY = Path(__file__).resolve().parents[2]
MATERIALS = {'brick', 'plaster/render', 'concrete', 'glass curtain wall', 'metal cladding', 'timber', 'stone', 'other'}

def configured_model():
    authentication = json.loads((Path.home()/'.codex/auth.json').read_text())
    if authentication.get('auth_mode') != 'chatgpt':
        raise ValueError('Perception requires existing free ChatGPT authentication')
    return tomllib.loads((Path.home()/'.codex/config.toml').read_text())['model']

def archive_completed(events, directory):
    parsed = []
    for line in events.splitlines():
        try: parsed.append(json.loads(line))
        except json.JSONDecodeError: continue
    tool_events = [event for event in parsed if event.get('type') in {'item.started','item.completed'} and event.get('item',{}).get('type') in {'command_execution','mcp_tool_call','web_search','file_change'}]
    if tool_events:
        raise ValueError('Visual worker used tools outside image-only scope')
    thread = next((event.get('thread_id') for event in parsed if event.get('type') == 'thread.started'), None)
    if thread and any(event.get('type') == 'turn.completed' for event in parsed):
        completed = subprocess.run([CLI,'archive',thread],capture_output=True,text=True,timeout=45)
        (directory/'archive.txt').write_text(completed.stdout+completed.stderr)


ROOT=Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
TILE='x90250_y436000'
WORK=ROOT/'facts/v1/work'/TILE
TILE_X,TILE_Y=90250,436000
PROMPT='''You are the C3 perception stage for a faithful miniature of Rotterdam. Josh: "the model should get EVERY SINGLE FUCKING COMPONENT RIGHT". Match the photo; "reads as" is not a pass. Interpret only attached source photographs; no tools, files, browsing, writing or delegation. Return JSON only.
The first sheet contains labelled rectified wall photos (2018). Grey is absent evidence. Each wall photo has its OWN displayed pixel coordinates, origin top-left excluding labels/margins, dimensions in inventory. The second sheet has building-labelled north-up aerial crops (2026); a cyan polygon outlines the target roof. A photo texture can be a neighbour's roof, sky, a tree or stretched UVs rather than this facade. Mark such regions occluded/nonfacade, never invent openings. Shadows do not establish concealed detail. Observe ONLY visible actual windows/doors/shop fronts. An opening means ONE COMPLETE OUTER MASONRY APERTURE including its entire frame: paired casements, sash lights, transoms and glazing panes inside one common frame are ONE opening, never separate openings. Separate apertures have visible masonry between them. Fit the outer frame boundary, not the glass alone. Inventory EVERY visible aperture, including small basement and attic apertures; do not substitute a typical count or pattern. Occluded detail is interpreted, never verified.
Return one object per requested wall_id in a JSON array, exactly:
{"wall_id":"...","material":"brick|plaster/render|concrete|glass curtain wall|metal cladding|timber|stone|other","wall_boxes":[[left,top,right,bottom]],"window_rows":[{"window_indices":[0,1]}],"openings":[{"kind":"window|door|shop_front","box":[left,top,right,bottom],"type":"sash_with_transom|casement|modern|other|unknown","partial":false,"vertical_divisions":[],"horizontal_divisions":[],"divisions_observed":false}],"cornice":{"type":"none|plain|moulded|dentilled|unknown","box":null},"gable_type":"none|stepped|pointed|bell|neck|other|unknown","occlusion_polygons":[[[x,y],[x,y],[x,y]]],"unusable_photo":false,"roof":{"type":"pitched_tile|flat_bitumen|metal|green|glass|other|unknown","equipment":[{"kind":"solar_panel|skylight|dormer|chimney|ventilation|other","box":[left,top,right,bottom]}]},"note":"uncertainty only"}
For each outer aperture, list only visibly observed internal frame/mullion centrelines as vertical_divisions and horizontal_divisions, normalized 0..1 relative to that aperture box (left-to-right and top-to-bottom). Separate outer apertures remain separate openings; glass lights inside one frame never become extra outer openings. Do not derive internal bars from the type label or a typical grid. Use divisions_observed=false and empty lists when unresolved. A clearly undivided opening has divisions_observed=true and empty lists. All boxes/polygons integer PIXELS relative to that wall's displayed photo, except roof equipment boxes relative to that building's displayed aerial crop. Small wall_boxes must sample visibly exposed main wall material, excluding windows, trim, vegetation, roofs and heavy shadow. If the material class cannot be distinguished use material=other, but still select small clearly exposed main-wall colour patches when their surface can be separated from glazing, trim and vegetation. Class uncertainty does not make a visible colour unknown. Use wall_boxes=[] only when no uncontaminated main-wall colour patch is visible. Occlusion polygons must cover ALL trees, foreground objects, roof bleed, nonfacade regions and invisible detail within wall geometry. If the whole photo is not a usable facade set unusable_photo=true, material=other, openings=[], wall_boxes=[]. Do not guess under trees. Include every directly visible opening, not a typical rhythm. Partial openings keep visible extents and partial=true. Do not invent hidden halves or extrapolated rows. Cornice box only if visible. Roof equipment comes ONLY from the aerial, unknown if roof is outside coverage/ambiguous. Roof outline positions are not equipment. Empty/unknown is an honest result. No colours or metric dimensions: code measures texels and transforms positions.
'''

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):
    path=Path(path)
    temporary=path.with_name('.'+path.name+f'.{os.getpid()}.pending')
    temporary.write_text(json.dumps(value,indent=2)+'\n')
    temporary.replace(path)
def load(path): return json.loads(Path(path).read_text())

def geometry_signature(wall):
    keys=sorted((t['primitive_index'],t['triangle_index']) for t in wall['triangles'])
    return hashlib.sha256(json.dumps(keys).encode()).hexdigest()


def sheets(walls,directory):
    cols=4; cell=(420,370); rows=(len(walls)+cols-1)//cols
    sheet=Image.new('RGB',(cols*cell[0],rows*cell[1]),'white'); draw=ImageDraw.Draw(sheet)
    aerial=Image.open(ROOT/'scene/v1/tiles'/TILE/'ortho.jpg').convert('RGB')
    roofs=Image.new('RGB',sheet.size,'white'); roofdraw=ImageDraw.Draw(roofs)
    inventory=[]
    for index,wall in enumerate(walls):
        x=(index%cols)*cell[0]+5;y=(index//cols)*cell[1]+35
        image=Image.open(wall['reference']).convert('RGB'); original=image.size
        factor=min(1,410/image.width,325/image.height)
        image=image.resize((max(1,round(image.width*factor)),max(1,round(image.height*factor))))
        sheet.paste(image,(x,y));draw.text((x,y-30),wall['wall_id'],fill='black');draw.text((x,y-15),str(image.size),fill='black')
        vertices=np.concatenate([np.asarray(t['rd_nap_vertices']) for t in wall['triangles']])
        # A full-building roof crop is supplied consistently for all its walls.
        all_vertices=np.concatenate([np.asarray(t['rd_nap_vertices']) for w in ALL_WALLS if w['bag_id']==wall['bag_id'] for t in w['triangles']])
        px=np.column_stack(((all_vertices[:,0]-TILE_X)*10,(TILE_Y+250-all_vertices[:,1])*10))
        bbox=[int(np.floor(px[:,0].min()))-12,int(np.floor(px[:,1].min()))-12,int(np.ceil(px[:,0].max()))+12,int(np.ceil(px[:,1].max()))+12]
        crop=aerial.crop(tuple(bbox)); rf=min(1,410/crop.width,325/crop.height); crop=crop.resize((max(1,round(crop.width*rf)),max(1,round(crop.height*rf))))
        from shapely.geometry import MultiPoint
        outline=np.asarray(MultiPoint(px).convex_hull.exterior.coords)
        cd=ImageDraw.Draw(crop);cd.line([tuple((p-np.array(bbox[:2]))*rf) for p in outline],fill='cyan',width=1)
        roofs.paste(crop,(x,y));roofdraw.text((x,y-30),wall['bag_id']+' roof north up',fill='black');roofdraw.text((x,y-15),str(crop.size),fill='black')
        inventory.append({'wall_id':wall['wall_id'],'wall_display_size_px':list(image.size),'wall_original_size_px':list(original),'reference_sha256':wall['reference_sha256'],'geometry_signature':geometry_signature(wall),'wall_scale':[image.width/original[0],image.height/original[1]],'roof_display_size_px':list(crop.size),'roof_aerial_rectangle_px':bbox,'roof_display_scale':rf})
    sheet.save(directory/'walls.jpg',quality=95);roofs.save(directory/'roofs.jpg',quality=95)
    return inventory

def validate_box(box,size):
    return isinstance(box,list) and len(box)==4 and all(isinstance(v,(int,float)) for v in box) and 0<=box[0]<box[2]<=size[0] and 0<=box[1]<box[3]<=size[1]

def checked_inner_divisions(opening, box, distance, visible):
    x0,y0,x1,y1=map(round,box)
    values={'vertical':[],'horizontal':[],'rejected':[],
            'status':'observed' if opening.get('divisions_observed') else 'unknown',
            'position_basis':'fraction-of-visible-outer-aperture-box',
            'edge_checks':[]}
    height,width=visible.shape
    for axis in ('vertical','horizontal'):
        for fraction in opening.get(axis+'_divisions',[]) or []:
            if not isinstance(fraction,(int,float)) or isinstance(fraction,bool) or not 0<fraction<1:
                values['rejected'].append({'axis':axis,'position':fraction,'reason':'invalid-inner-position'});continue
            line=np.zeros_like(visible)
            if axis=='vertical':
                coordinate=round(x0+fraction*max(1,x1-x0-1))
                if 0<=coordinate<width:line[max(0,y0+2):min(height,y1-2),coordinate]=True
            else:
                coordinate=round(y0+fraction*max(1,y1-y0-1))
                if 0<=coordinate<height:line[coordinate,max(0,x0+2):min(width,x1-2)]=True
            eligible=line&visible
            agreement=float((distance[eligible]<=2).mean()) if eligible.any() else 0
            check={'axis':axis,'position':float(fraction),'edge_agreement':agreement,'visible_samples':int(eligible.sum()),'tolerance_display_px':2}
            if eligible.sum()>=4 and agreement>=.5:
                values[axis].append(float(fraction));values['edge_checks'].append(check)
                values['status']='source-edge-supported'
            else:values['rejected'].append(dict(check,reason='inner-photo-edge-mismatch-or-occlusion'))
    return values


def apply_division_observations(record,wall):
    geometry_path=Path(wall['reference']).parent/'geometry-observations.json'
    if geometry_path.exists():
        geometry=load(geometry_path)
        if geometry.get('reference_sha256')==wall['reference_sha256']:
            record.update(geometry['aperture_facts'])
            record['geometry_observations']=geometry['provenance']
    material_path=Path(wall['reference']).parent/'material-observations.json'
    if material_path.exists():
        material=load(material_path)
        if material.get('reference_sha256')==wall['reference_sha256']:
            pixels=np.asarray(Image.open(wall['reference']).convert('RGB'))
            visible=np.asarray(Image.open(record['evidence_mask']).convert('L'))>0
            samples=[]
            for box in material['sample_boxes_px']:
                x0,y0,x1,y1=box
                mask=visible[y0:y1,x0:x1]
                if mask.size and mask.mean()>=.9:samples.append(pixels[y0:y1,x0:x1][mask])
            if samples:
                colour=np.rint(np.concatenate(samples).mean(0)).astype(int)
                record['mean_colour_srgb']='#'+''.join(f'{value:02x}' for value in colour)
                record['material_sample_boxes_px']=material['sample_boxes_px']
                record['material_observations']=material
    path=Path(wall['reference']).parent/'division-observations.json'
    if not path.exists():return record
    observed=load(path)
    if observed.get('reference_sha256')!=wall['reference_sha256']:return record
    by_box={(tuple(item['box_px']),item['kind']):item for item in observed.get('openings',[])}
    for key in ('openings','doors','shop_fronts','source_partial_openings'):
        for opening in record.get(key,[]):
            value=by_box.get((tuple(opening.get('box_px',[])),opening['kind']))
            if value:opening['inner_divisions']=value['inner_divisions']
    return record


def measure(wall,result,inv,provenance,preserved=None):
    pixels=np.asarray(Image.open(wall['reference']).convert('RGB')); photo=np.asarray(Image.open(wall['photo_mask']))>0; geometry=np.asarray(Image.open(wall['geometry_mask']))>0
    height,width=photo.shape; sx,sy=inv['wall_scale']; mask=Image.new('L',(width,height),0);draw=ImageDraw.Draw(mask)
    for polygon in result.get('occlusion_polygons',[]):
        if len(polygon)>=3: draw.polygon([(round(p[0]/sx),round(p[1]/sy)) for p in polygon],fill=255)
    occluded=np.asarray(mask)>0
    if result.get('unusable_photo'): occluded|=geometry
    visible=(np.asarray(Image.open(preserved['evidence_mask']).convert('L'))>0) if preserved else photo&geometry&~occluded
    # Source coverage holes and semantic masks remain interpreted, not verified.
    interpreted=geometry&~visible
    folder=Path(wall['reference']).parent
    Image.fromarray(visible.astype(np.uint8)*255).save(folder/'evidence-mask.png')
    Image.fromarray(interpreted.astype(np.uint8)*255).save(folder/'interpreted-mask.png')
    material_exclusion=np.zeros_like(visible)
    excluded_boxes=[o.get('box') for o in result.get('openings',[])]
    excluded_boxes.append(result.get('cornice',{}).get('box'))
    for box in excluded_boxes:
        if validate_box(box,inv['wall_display_size_px']):
            x0,y0,x1,y1=[round(v/(sx if i%2==0 else sy)) for i,v in enumerate(box)]
            material_exclusion[y0:y1,x0:x1]=True
    exclusion_path=WORK/'material-exclusions.json'
    if exclusion_path.exists():
        annotations=load(exclusion_path).get('walls',{})
        for annotation in annotations.values():
            if annotation.get('reference_sha256')==wall['reference_sha256']:
                for box in annotation.get('boxes_px',[])+[r['box_px'] for r in annotation.get('regions',[]) if r.get('exclude_from_main_material')]:
                    x0,y0,x1,y1=box
                    material_exclusion[y0:y1,x0:x1]=True
    samples=[]; material_boxes=[]; rejected_material_boxes=[]
    for box in result.get('wall_boxes',[]):
        if not validate_box(box,inv['wall_display_size_px']): continue
        x0,y0,x1,y1=[round(v/(sx if i%2==0 else sy)) for i,v in enumerate(box)]
        eligible_material=visible[y0:y1,x0:x1]&~material_exclusion[y0:y1,x0:x1]
        if eligible_material.mean()<.8:
            rejected_material_boxes.append({'box_px':[x0,y0,x1,y1],'reason':'opening_trim_occlusion_or_missing_photo_contamination'})
            continue
        selected=pixels[y0:y1,x0:x1][eligible_material]
        if len(selected): samples.append(selected);material_boxes.append([x0,y0,x1,y1])
    colour=None
    if samples:
        # Arithmetic mean in source sRGB texels; no model-colour estimates.
        rgb=np.rint(np.concatenate(samples).mean(axis=0)).astype(int);colour='#'+''.join(f'{v:02x}' for v in rgb)
    # Match the exact source view presented to the model. Rectified 5cm textures
    # often oversample a blurry 2018 source; Sobel on that upsampled grid loses
    # the real photo edges. Verification tolerance is recorded in both grids.
    display_size=tuple(inv['wall_display_size_px'])
    displayed=Image.open(wall['reference']).convert('RGB').resize(display_size)
    displayed_visible=np.asarray(Image.fromarray(visible.astype(np.uint8)*255).resize(display_size,Image.Resampling.NEAREST))>0
    luminance=np.asarray(displayed.convert('L'))/255.
    contrast_low,contrast_high=np.percentile(luminance[displayed_visible],[2,98]) if displayed_visible.any() else (0.,1.)
    normalized=np.clip((luminance-contrast_low)/max(float(contrast_high-contrast_low),.001),0,1)
    edges=sobel(normalized)>.06
    distance=ndimage.distance_transform_edt(~edges)
    openings=[]; rejected=[]
    for index,opening in enumerate(result.get('openings',[])):
        box=opening.get('box')
        if not validate_box(box,inv['wall_display_size_px']): rejected.append({'index':index,'reason':'invalid_box'});continue
        x0,y0,x1,y1=[round(v/(sx if i%2==0 else sy)) for i,v in enumerate(box)]
        x0=max(0,min(width-1,x0));x1=max(x0+1,min(width,x1));y0=max(0,min(height-1,y0));y1=max(y0+1,min(height,y1))
        dx0,dy0,dx1,dy1=[round(v) for v in box]
        boundary=np.zeros((display_size[1],display_size[0]),dtype=bool)
        boundary[dy0:dy1,dx0]=1;boundary[dy0:dy1,dx1-1]=1
        boundary[dy0,dx0:dx1]=1;boundary[dy1-1,dx0:dx1]=1
        eligible=boundary&ndimage.binary_erosion(displayed_visible,iterations=1)
        share=float((distance[eligible]<=2).mean()) if eligible.any() else 0
        visible_share=float(visible[y0:y1,x0:x1].mean())
        value=dict(opening,source_index=index,box_px=[x0,y0,x1,y1],box_m=[round(v*.05,3) for v in [x0,y0,x1,y1]],edge_agreement=share,evidence_fraction=visible_share,edge_check={'grid':'exact_contact_sheet_source_view','display_size_px':list(display_size),'sobel_threshold':.06,'tolerance_display_px':2,'tolerance_m_xy':[.1/sx,.1/sy],'contrast_percentiles':[2,98],'luminance_range':[float(contrast_low),float(contrast_high)]})
        if opening.get('kind') in ('window','shop_front'):
            value['inner_divisions']=checked_inner_divisions(opening,box,distance,displayed_visible)
        if eligible.sum()<8 or share<.5 or visible_share<.85 or opening.get('partial'):
            value['status']='rejected';value['reason']='partial_or_occluded' if opening.get('partial') or visible_share<.85 else 'photo_edge_mismatch';rejected.append(value)
        else: value['status']='edge_supported';openings.append(value)
    total=max(int(geometry.sum()),1)
    record={key:wall[key] for key in ['wall_id','street_facing','area_m2','wall_plane_rd_nap','pixel_transform','image_size_px','triangles']}
    record.update({'material':result.get('material','other') if colour and result.get('material') in MATERIALS else 'other','mean_colour_srgb':colour,'material_sample_boxes_px':material_boxes,'rejected_material_sample_boxes':rejected_material_boxes,'window_rows':[{**row,'window_indices':[i for i in row.get('window_indices',[]) if i in {o['source_index'] for o in openings}]} for row in result.get('window_rows',[])],'openings':openings,'rejected_openings':rejected,'doors':[o for o in openings if o['kind']=='door'],'shop_fronts':[o for o in openings if o['kind']=='shop_front'],'cornice':normalise_cornice(result.get('cornice',{}),inv),'gable_type':result.get('gable_type','unknown'),'roof':normalise_roof(result.get('roof',{}),inv),'occlusion_mask':str(folder/'interpreted-mask.png'),'evidence_mask':str(folder/'evidence-mask.png'),'photo':wall['reference'],'verified_fraction':0.,'visible_evidence_fraction':int(visible.sum())/total,'occluded_fraction':int(interpreted.sum())/total,'verification_status':'machine_edge_checked_not_independently_verified','note':result.get('note',''),'provenance':provenance})
    partials=[]
    for opening in rejected:
        rectangle=opening.get('box_px')
        if (not opening.get('partial') or not rectangle or opening.get('edge_agreement',0)<.5
                or opening.get('evidence_fraction',0)<.85):
            continue
        x0,y0,x1,y1=rectangle
        clipped=[edge for edge,condition in [('left',x0==0),('top',y0==0),('right',x1==width),('bottom',y1==height)] if condition]
        if clipped:
            partials.append(dict(opening,clip_edges=clipped,drawing_status='source-visible-partial-interpreted',
                                 note='Only visible extent is drawn; cropped edges omit an invented complete outer frame.'))
    record['source_partial_openings']=partials
    # A model selection plus edge support does not establish semantic truth of an entire wall.
    if preserved:
        aperture_keys=('window_rows','openings','rejected_openings','doors','shop_fronts','source_partial_openings')
        record=dict(preserved,**{key:record[key] for key in aperture_keys},geometry_observations=provenance)
    else:
        record=apply_division_observations(record,wall)
    save(folder/'perception.json',record)
    return record

def normalise_roof(value, inventory):
    equipment=[]
    for item in value.get('equipment',[]):
        if not validate_box(item.get('box'),inventory['roof_display_size_px']):
            continue
        box=item['box']
        crop=inventory['roof_aerial_rectangle_px']
        scale=inventory['roof_display_scale']
        aerial=[box[0]/scale+crop[0],box[1]/scale+crop[1],box[2]/scale+crop[0],box[3]/scale+crop[1]]
        equipment.append(dict(item,box_px=box,aerial_box_px=aerial,bounds_rd=[TILE_X+aerial[0]*.1,TILE_Y+250-aerial[3]*.1,TILE_X+aerial[2]*.1,TILE_Y+250-aerial[1]*.1],verification_status='model_observed_not_independently_verified'))
    return dict(value,equipment=equipment,aerial_crop=inventory['roof_aerial_rectangle_px'],display_scale=inventory['roof_display_scale'],source_date='2026',verification_status='model_observed_not_independently_verified')


def normalise_cornice(value, inventory):
    box = value.get('box')
    observed = value.get('type') not in (None, 'none', 'unknown') and validate_box(box, inventory['wall_display_size_px'])
    return dict(value, observed=observed, box_px=[round(v / inventory['wall_scale'][i % 2]) for i, v in enumerate(box)] if observed else None)


def rate_limit_error(events, stderr):
    # A BAG id or coordinate containing 429 is not an HTTP error.
    for line in events.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get('type') in ('error', 'turn.failed') or event.get('item', {}).get('type') == 'error':
            message = json.dumps(event).lower()
            if '429' in message or 'rate limit' in message or 'rate_limit' in message:
                return True
    return any(token in stderr.lower() for token in ('http 429', 'status: 429', 'rate limit', 'rate_limit'))


ALL_WALLS=[]
PUBLISH_LOCK=threading.Lock()
STOP=threading.Event()


def run_batch(walls, model):
    identity=hashlib.sha256((PROMPT+model+''.join(w['wall_id']+w['reference_sha256'] for w in walls)).encode()).hexdigest()
    directory=WORK/'perception-batches'/identity
    directory.mkdir(parents=True,exist_ok=True)
    inventory=sheets(walls,directory)
    prompt=PROMPT+'\nInventory in sheet row-major order:\n'+json.dumps(inventory)
    save(directory/'inventory.json',inventory)
    (directory/'prompt.txt').write_text(prompt)
    answer=directory/'answer.json'
    timing=directory/'call.json'
    if not answer.exists():
        if STOP.is_set(): return
        started=datetime.now(timezone.utc).isoformat()
        clock=time.monotonic()
        command=[CLI,'exec','--json','--skip-git-repo-check','-C',str(REPOSITORY),'-o',str(answer),'-i',str(directory/'walls.jpg'),'-i',str(directory/'roofs.jpg'),'-']
        with (directory/'events.jsonl').open('w') as stdout,(directory/'stderr.txt').open('w') as stderr:
            try:
                completed=subprocess.run(command,input=prompt,text=True,stdout=stdout,stderr=stderr,timeout=900)
            except subprocess.TimeoutExpired:
                STOP.set()
                save(timing,{'model':model,'started_at':started,'seconds':time.monotonic()-clock,'wall_count':len(walls),'status':'timeout'})
                return
        events=(directory/'events.jsonl').read_text()
        limited=rate_limit_error(events,(directory/'stderr.txt').read_text())
        save(timing,{'model':model,'started_at':started,'ended_at':datetime.now(timezone.utc).isoformat(),'seconds':time.monotonic()-clock,'wall_count':len(walls),'rate_limited':limited,'returncode':completed.returncode,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest()})
        archive_completed(events,directory)
        if limited or completed.returncode:
            STOP.set()
            print(json.dumps({'stopped':'rate_limit' if limited else 'call_failed','directory':str(directory)}),flush=True)
            return
    text=answer.read_text().strip()
    if text.startswith('```'):text=text[text.index('\n')+1:text.rfind('```')]
    results=json.loads(text)
    byid={r['wall_id']:r for r in results}
    if len(results)!=len(walls) or set(byid)!=set(w['wall_id'] for w in walls):raise ValueError('Wall reply missing, duplicate or unexpected ids')
    for wall,inv in zip(walls,inventory):
        provenance={'model':model,'date':datetime.now(timezone.utc).isoformat(),'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'reference_hashes':{str(ROOT/'scene/v1/tiles'/TILE/'ortho.jpg'):sha(ROOT/'scene/v1/tiles'/TILE/'ortho.jpg'),wall['reference']:sha(wall['reference']),str(directory/'walls.jpg'):sha(directory/'walls.jpg'),str(directory/'roofs.jpg'):sha(directory/'roofs.jpg')},'response':str(answer),'call':str(timing),'method':'model_contact_sheet_v1','opening_definition':'outer_masonry_aperture_v2','material_selection_revision':'independent-class-colour-v2'}
        measure(wall,byid[wall['wall_id']],inv,provenance)
    with PUBLISH_LOCK:
        publish()
    print(json.dumps({'walls_measured':len(walls),'directory':str(directory)}),flush=True)


DIVISION_PROMPT='''Task: measure only visible inner window-frame divisions in the attached actual Rotterdam source photos. Josh: every component must match the photo, never invent. No tools, files, writing, browsing or delegation. The inventory fixes every existing OUTER aperture and source_index. Do not add, remove, split, resize or move any outer aperture. Several glazing lights within one outer frame remain one opening. For each inventory aperture, return only visibly observed vertical/horizontal mullion or sash-bar centre positions, normalized 0..1 relative to that aperture's supplied display box (left-to-right and top-to-bottom). Do not infer a typical count, regular spacing, symmetry or a division from the window type. Distinguish actual pale/dark frame bars from glass reflection streaks and vegetation. If the resolution/occlusion does not resolve a bar, omit it and set divisions_observed=false. A clearly undivided aperture has divisions_observed=true and empty lists. Retain every supplied index even when unknown. Return JSON only: [{"wall_id":"...","openings":[{"source_index":0,"vertical_divisions":[0.2,0.4],"horizontal_divisions":[],"divisions_observed":true}]}]. The example positions are schema examples, never a template.'''


def wall_apertures(wall):
    fact=load(Path(wall['reference']).parent/'perception.json')
    return [opening for key in ('openings','source_partial_openings') for opening in fact.get(key,[])
            if opening['kind'] in ('window','shop_front') and opening.get('source_index') is not None]


def division_review_needed(wall):
    if not valid_measurement(wall):return False
    openings=wall_apertures(wall)
    if not openings:return False
    path=Path(wall['reference']).parent/'division-observations.json'
    if not path.exists():return True
    current=load(path)
    expected={(tuple(opening['box_px']),opening['kind']) for opening in openings}
    observed={(tuple(opening['box_px']),opening['kind']) for opening in current.get('openings',[])}
    return current.get('reference_sha256')!=wall['reference_sha256'] or not expected.issubset(observed)


def run_division_batch(walls,model):
    apertures={wall['wall_id']:wall_apertures(wall) for wall in walls}
    identity=hashlib.sha256((DIVISION_PROMPT+model+json.dumps(apertures,sort_keys=True)+''.join(w['reference_sha256'] for w in walls)).encode()).hexdigest()
    directory=WORK/'division-batches'/identity
    directory.mkdir(parents=True,exist_ok=True)
    inventory=sheets(walls,directory)
    for wall,entry in zip(walls,inventory):
        sx,sy=entry['wall_scale']
        entry['openings']=[{'source_index':o['source_index'],'kind':o['kind'],'display_box':[round(v*(sx if i%2==0 else sy),3) for i,v in enumerate(o['box_px'])]} for o in apertures[wall['wall_id']]]
    prompt=DIVISION_PROMPT+'\nInventory:\n'+json.dumps(inventory)
    save(directory/'inventory.json',inventory);(directory/'prompt.txt').write_text(prompt)
    answer=directory/'answer.json';timing=directory/'call.json'
    if not answer.exists():
        if STOP.is_set():return
        started=datetime.now(timezone.utc).isoformat();clock=time.monotonic()
        command=[CLI,'exec','--json','--skip-git-repo-check','-C',str(REPOSITORY),'-o',str(answer),'-i',str(directory/'walls.jpg'),'-']
        with (directory/'events.jsonl').open('w') as stdout,(directory/'stderr.txt').open('w') as stderr:
            try:completed=subprocess.run(command,input=prompt,text=True,stdout=stdout,stderr=stderr,timeout=900)
            except subprocess.TimeoutExpired:
                STOP.set();save(timing,{'model':model,'started_at':started,'seconds':time.monotonic()-clock,'wall_count':len(walls),'status':'timeout'});return
        events=(directory/'events.jsonl').read_text();limited=rate_limit_error(events,(directory/'stderr.txt').read_text())
        save(timing,{'model':model,'started_at':started,'seconds':time.monotonic()-clock,'wall_count':len(walls),'rate_limited':limited,'returncode':completed.returncode,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest()})
        if limited or completed.returncode:STOP.set();return
        archive_completed(events,directory)
    text=answer.read_text().strip()
    if text.startswith('```'):text=text[text.index('\n')+1:text.rfind('```')]
    values=json.loads(text);by_id={value['wall_id']:value for value in values}
    if len(values)!=len(walls) or set(by_id)!={wall['wall_id'] for wall in walls}:raise ValueError('Division reply omitted or duplicated a wall')
    for wall,entry in zip(walls,inventory):
        selected=by_id[wall['wall_id']]['openings'];by_index={value['source_index']:value for value in selected}
        expected={opening['source_index'] for opening in apertures[wall['wall_id']]}
        if len(selected)!=len(expected) or set(by_index)!=expected:raise ValueError('Division reply changed outer aperture inventory')
        fact_path=Path(wall['reference']).parent/'perception.json';fact=load(fact_path)
        display_size=tuple(entry['wall_display_size_px'])
        displayed=Image.open(wall['reference']).convert('L').resize(display_size)
        visible=np.asarray(Image.open(fact['evidence_mask']).convert('L').resize(display_size,Image.Resampling.NEAREST))>0
        luminance=np.asarray(displayed)/255.;low,high=np.percentile(luminance[visible],[2,98]) if visible.any() else (0,1)
        distance=ndimage.distance_transform_edt(~(sobel(np.clip((luminance-low)/max(float(high-low),.001),0,1))>.06))
        observations=[]
        for opening,display_opening in zip(apertures[wall['wall_id']],entry['openings']):
            value=checked_inner_divisions(by_index[opening['source_index']],display_opening['display_box'],distance,visible)
            value['provenance']={'model':model,'date':datetime.now(timezone.utc).isoformat(),'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'response':str(answer),'reference_hashes':{wall['reference']:wall['reference_sha256'],str(directory/'walls.jpg'):sha(directory/'walls.jpg')}}
            observations.append({'source_index':opening['source_index'],'box_px':opening['box_px'],'kind':opening['kind'],'inner_divisions':value})
        save(fact_path.parent/'division-observations.json',{'reference_sha256':wall['reference_sha256'],'wall_id':wall['wall_id'],'openings':observations})
        save(fact_path,apply_division_observations(fact,wall))
    with PUBLISH_LOCK:publish()
    print(json.dumps({'inner_divisions_measured_walls':len(walls),'directory':str(directory)}),flush=True)


def reuse_completed(model):
    byid={w['wall_id']:w for w in ALL_WALLS}
    bygeometry={(w['bag_id'],geometry_signature(w),w['reference_sha256']):w for w in ALL_WALLS}
    count=0
    for path in sorted((WORK/'perception-batches').glob('*/answer.json'),key=lambda p:load(p.parent/'call.json').get('started_at','') if (p.parent/'call.json').exists() else ''):
        folder=path.parent
        if not (folder/'call.json').exists(): continue
        call=load(folder/'call.json')
        if call.get('returncode')!=0 or call.get('model')!=model: continue
        text=path.read_text().strip()
        if text.startswith('```'):text=text[text.index('\n')+1:text.rfind('```')]
        results={r['wall_id']:r for r in json.loads(text)}
        geometry_index=load(folder/'geometry-index.json').get('walls',{}) if (folder/'geometry-index.json').exists() else {}
        for original_inv in load(folder/'inventory.json'):
            inv=dict(original_inv,**geometry_index.get(original_inv['wall_id'],{}))
            old_id=inv['wall_id']
            oldref=WORK/'walls'/old_id.replace(':','_')/'reference.png'
            cached_hash=inv.get('reference_sha256',sha(oldref) if oldref.exists() else None)
            if inv.get('geometry_signature'):
                wall=bygeometry.get((old_id.split(':')[0],inv['geometry_signature'],cached_hash))
            else:
                wall=byid.get(old_id)
            if wall is None or cached_hash!=wall['reference_sha256']: continue
            provenance={'model':model,'date':call.get('ended_at'),'prompt_sha256':call.get('prompt_sha256'),'reference_hashes':{str(ROOT/'scene/v1/tiles'/TILE/'ortho.jpg'):sha(ROOT/'scene/v1/tiles'/TILE/'ortho.jpg'),wall['reference']:sha(wall['reference']),str(folder/'walls.jpg'):sha(folder/'walls.jpg'),str(folder/'roofs.jpg'):sha(folder/'roofs.jpg')},'response':str(path),'call':str(folder/'call.json'),'method':'model_contact_sheet_v1','original_wall_id':old_id,'opening_definition':'outer_masonry_aperture_v2' if 'ONE COMPLETE OUTER MASONRY APERTURE' in (folder/'prompt.txt').read_text() else 'original_v1','material_selection_revision':'independent-class-colour-v2' if 'Class uncertainty does not make a visible colour unknown' in (folder/'prompt.txt').read_text() else 'class-coupled-v1'}
            measure(wall,results[old_id],inv,provenance)
            count+=1
    return count


def valid_measurement(wall):
    path=Path(wall['reference']).parent/'perception.json'
    if not path.exists():return False
    record=load(path)
    return (record.get('provenance',{}).get('reference_hashes',{}).get(wall['reference'])==wall['reference_sha256']
            and record.get('wall_id')==wall['wall_id'] and geometry_signature(record)==geometry_signature(wall))


def main():
    global ALL_WALLS, TILE, WORK, TILE_X, TILE_Y
    parser=argparse.ArgumentParser()
    parser.add_argument('--tile', default=TILE)
    parser.add_argument('--batch-size',type=int,default=24)
    parser.add_argument('--max-calls',type=int)
    parser.add_argument('--start',type=int,default=0)
    parser.add_argument('--workers',type=int,default=1)
    parser.add_argument('--wall-id',action='append',help='Limit measurement to an explicit existing wall')
    parser.add_argument('--review-divisions',action='store_true',help='Measure inner bars while preserving all existing outer apertures and material facts')
    parser.add_argument('--review-material',action='store_true',help='Reassess visible wall colours formerly omitted only because material class was unknown')
    parser.add_argument('--only-triaged',action='store_true',help='Measure only source views classified as visibly usable facades')
    parser.add_argument('--review-openings','--review-observed',action='store_true')
    parser.add_argument('--index-cache-geometry',action='store_true')
    args=parser.parse_args()
    TILE=args.tile
    TILE_X,TILE_Y=map(int,TILE[1:].split('_y'))
    WORK=ROOT/'facts/v1/work'/TILE
    WORK.mkdir(parents=True,exist_ok=True)
    tile_lock=(WORK/'perception.lock').open('a')
    fcntl.flock(tile_lock,fcntl.LOCK_EX)
    from wall_facts import prepare_walls
    prepare_walls(TILE)
    ALL_WALLS=load(WORK/'walls.json')['walls']
    if args.index_cache_geometry:
        byid={w['wall_id']:w for w in ALL_WALLS}
        for folder in (WORK/'perception-batches').iterdir():
            if not (folder/'answer.json').exists():continue
            index={}
            for inv in load(folder/'inventory.json'):
                wall=byid.get(inv['wall_id'])
                if wall is None:continue
                cached_hash=inv.get('reference_sha256')
                oldref=WORK/'walls'/wall['wall_id'].replace(':','_')/'reference.png'
                if cached_hash is None and oldref.exists():cached_hash=sha(oldref)
                if cached_hash==wall['reference_sha256']:
                    index[wall['wall_id']]={'geometry_signature':geometry_signature(wall),'reference_sha256':wall['reference_sha256']}
            save(folder/'geometry-index.json',{'source_manifest_sha256':sha(WORK/'walls.json'),'walls':index})
        print('Cache geometry indexed; source call inventories and prompts unchanged.',flush=True)
        return
    model=configured_model()
    reused=reuse_completed(model)
    eligible=[w for w in ALL_WALLS if w['street_facing'] and w['photo_pixels']>0 and not valid_measurement(w)]
    if args.review_openings:
        eligible=[]
        for wall in ALL_WALLS:
            path=Path(wall['reference']).parent/'perception.json'
            if valid_measurement(wall):
                fact=load(path)
                if (fact.get('openings') or fact.get('rejected_openings') or fact.get('material_sample_boxes_px')) and fact['provenance'].get('opening_definition')!='outer_masonry_aperture_v2':
                    eligible.append(wall)
    if args.review_material:
        eligible=[]
        for wall in ALL_WALLS:
            if valid_measurement(wall):
                fact=load(Path(wall['reference']).parent/'perception.json')
                if (not fact.get('mean_colour_srgb') and fact.get('visible_evidence_fraction',0)>.2
                        and fact.get('provenance',{}).get('material_selection_revision')!='independent-class-colour-v2'):
                    eligible.append(wall)
    if args.review_divisions:
        eligible=[wall for wall in ALL_WALLS if division_review_needed(wall)]
    if args.wall_id:
        eligible=[wall for wall in eligible if wall['wall_id'] in set(args.wall_id)]
    triage_path=WORK/'source-triage.json'
    triage=load(triage_path).get('walls',{}) if triage_path.exists() else {}
    def source_class(wall):
        value=triage.get(wall['wall_id'],{})
        if value.get('reference_sha256')!=wall['reference_sha256']:
            return 1
        return 0 if value.get('usable_facade') else 2
    if args.only_triaged:
        eligible=[wall for wall in eligible if source_class(wall)==0]
    eligible.sort(key=lambda w:(source_class(w),not (10 <= w['area_m2'] <= 100 and w.get('photo_fraction',0) >= .6), -w['area_m2']))
    batches=[eligible[i:i+args.batch_size] for i in range(args.start,len(eligible),args.batch_size)]
    if args.max_calls is not None:batches=batches[:args.max_calls]
    print(json.dumps({'cached_measurements':reused,'pending_walls':len(eligible),'batches':len(batches),'workers':args.workers}),flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(run_division_batch if args.review_divisions else run_batch,walls,model) for walls in batches]
        for future in as_completed(futures):
            future.result()
            if STOP.is_set():
                for pending in futures:pending.cancel()
                break
    publish()
    measured=[wall for wall in ALL_WALLS if valid_measurement(wall)]
    pending=[wall for wall in ALL_WALLS if wall['street_facing'] and wall['photo_pixels']>0 and not valid_measurement(wall)]
    measurements=[load(Path(wall['reference']).parent/'perception.json') for wall in measured]
    calls=[load(path) for path in (WORK/'perception-batches').glob('*/call.json')]
    save(WORK/'perception-report.json',{'written_by':'AI, GPT-6 Astra, 2026-10-26',
         'tile':TILE,'source_sha256':load(WORK/'walls.json')['source']['sha256'],
         'walls_measured':len(measured),'street_photo_walls_pending':len(pending),
         'material_measured_walls':sum(bool(fact.get('mean_colour_srgb')) for fact in measurements),
         'accepted_complete_openings':sum(len(fact.get('openings',[])) for fact in measurements),
         'source_visible_partial_openings':sum(len(fact.get('source_partial_openings',[])) for fact in measurements),
         'street_photo_walls':sum(wall['street_facing'] and wall['photo_pixels']>0 for wall in ALL_WALLS),
         'tier2_photo_walls_pending':sum(10<=wall['area_m2']<=100 and wall.get('photo_fraction',0)>=.6 for wall in pending),
         'pending_wall_ids':[wall['wall_id'] for wall in pending],
         'native_visual_calls':len(calls),'image_generation_calls':0,
         'source_triage_calls':len(list((WORK/'source-triage-calls').glob('*/call.json'))),
         'inner_division_calls':len(list((WORK/'division-batches').glob('*/call.json'))),
         'source_geometry_calls':len(list((WORK/'geometry-batches').glob('*/call.json'))),
         'source_triaged_usable_facades_pending':sum(source_class(wall)==0 for wall in pending),
         'native_visual_seconds':sum(call.get('seconds',0) for call in calls),
         'rate_limited':any(call.get('rate_limited',False) for call in calls),
         'status':'stopped' if STOP.is_set() else 'complete' if not pending else 'partial'})
    if STOP.is_set():
        raise SystemExit(75)

def publish():
    grouped=defaultdict(list)
    for wall in ALL_WALLS:
        path=Path(wall['reference']).parent/'perception.json'
        current=load(path) if path.exists() else None
        current_hash=current.get('provenance',{}).get('reference_hashes',{}).get(wall['reference']) if current else None
        if current and current_hash==wall['reference_sha256'] and geometry_signature(current)==geometry_signature(wall):record=current
        else:
            folder=Path(wall['reference']).parent
            if not (folder/'interpreted-mask.png').exists():
                Image.open(wall['geometry_mask']).save(folder/'interpreted-mask.png')
                Image.new('L',tuple(wall['image_size_px']),0).save(folder/'evidence-mask.png')
            record={key:wall[key] for key in ['wall_id','street_facing','area_m2','wall_plane_rd_nap','pixel_transform','image_size_px','triangles']}
            record.update({'material':'other','mean_colour_srgb':None,'openings':[],'doors':[],'shop_fronts':[],'window_rows':[],'cornice':{'type':'unknown','box':None},'gable_type':'unknown','roof':{'type':'unknown','equipment':[]},'photo':wall['reference'],'occlusion_mask':str(folder/'interpreted-mask.png'),'evidence_mask':str(folder/'evidence-mask.png'),'verified_fraction':0.,'visible_evidence_fraction':0.,'occluded_fraction':1.,'verification_status':'not_measured','provenance':{'method':'unmeasured','date':datetime.now(timezone.utc).isoformat(),'reference_hashes':{wall['reference']:wall['reference_sha256']},'model':None,'prompt_sha256':None}})
        grouped[wall['bag_id']].append(record)
    target=WORK/'buildings';target.mkdir(parents=True,exist_ok=True)
    for bag,walls in grouped.items():
        area=sum(w['area_m2'] for w in walls)
        save(target/f'{bag}.json',{'written_by':'AI, GPT-6 Astra, 2026-10-26','schema':'010-building-facts-v1','bag_id':bag,'tile':TILE,'walls':walls,'verified_fraction':sum(w['verified_fraction']*w['area_m2'] for w in walls)/area,'occluded_fraction':sum(w['occluded_fraction']*w['area_m2'] for w in walls)/area,'model':sorted({w['provenance']['model'] for w in walls if w['provenance'].get('model')}),'prompt_hashes':sorted({w['provenance']['prompt_sha256'] for w in walls if w['provenance'].get('prompt_sha256')}),'reference_hashes':{key:value for w in walls for key,value in w['provenance']['reference_hashes'].items()},'date':datetime.now(timezone.utc).isoformat()})
if __name__=='__main__':main()
