"""Build the reusable Delfshaven ground scene. Written by AI on 2026-10-25 by model GPT-6.1 Sol."""
import argparse,fcntl,hashlib,io,json,subprocess,os,multiprocessing
from concurrent.futures import ProcessPoolExecutor,as_completed
from shapely.geometry import box
from shapely.strtree import STRtree
from pathlib import Path
from urllib.parse import urlencode
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from archive import ROOT,DATE,fetch
from surfaces import SurfaceData,rasterize,LEGEND,PALETTE,FUNCTION_CLASSES,APPEARANCE_CLASSES,DEFAULT_CLASSES,PLUS_APPEARANCE_CLASSES
from markings import fetch_markings,marking_mask
AREAS={'core':(89750,435750,90750,436750),'m0':(89750,435250,92000,436750),'m1':(89750,434750,96500,438000)}
SCENE=ROOT/'scene/v1';DEBUG=SCENE/'debug-ground'

def ortho(x,y):
 name=f'x{x}_y{y}'
 params={'SERVICE':'WMS','VERSION':'1.3.0','REQUEST':'GetMap','LAYERS':'2026_orthoHR','STYLES':'','CRS':'EPSG:28992','BBOX':f'{x},{y},{x+250},{y+250}','WIDTH':2500,'HEIGHT':2500,'FORMAT':'image/jpeg'}
 url='https://service.pdok.nl/hwh/luchtfotorgb/wms/v1_0?'+urlencode(params)
 raw=fetch('ortho2026',name+'.jpg',url)
 image=Image.open(io.BytesIO(raw));assert image.size==(2500,2500) and image.format=='JPEG'
 target=SCENE/'tiles'/name;target.mkdir(parents=True,exist_ok=True);(target/'ortho.jpg').write_bytes(raw)
 return np.asarray(image.convert('RGB'))

def debug_image(name,rgb,classes,bits):
 DEBUG.mkdir(parents=True,exist_ok=True)
 colours=PALETTE[classes].copy()
 # Yellow = tram; cyan = train/metro; white = actual paint; dark = kerb.
 colours[bits&8!=0]=[40,40,40];colours[bits&4!=0]=[255,255,255]
 colours[bits&2!=0]=[0,255,255];colours[bits&1!=0]=[255,224,0]
 photo_overlay=rgb.copy();photo_overlay[bits&4!=0]=[255,60,255];photo_overlay[bits&1!=0]=[255,224,0];photo_overlay[bits&2!=0]=[0,255,255]
 canvas=Image.new('RGB',(7500,2780),'white');font=ImageFont.load_default(size=30)
 for i,(pixels,title) in enumerate([(rgb,'2026 aerial, unmodified'),(colours,'Classes: yellow tram / cyan train-metro / white paint'),(photo_overlay,'Alignment: yellow tram / cyan train-metro / magenta paint')]):
  canvas.paste(Image.fromarray(pixels),(i*2500,80));ImageDraw.Draw(canvas).text((i*2500+20,20),name+' — '+title,fill='black',font=font)
 drawing=ImageDraw.Draw(canvas)
 for index,label in enumerate(LEGEND):
  left=(index%5)*1500+20;top=2600+(index//5)*40
  drawing.rectangle((left,top,left+30,top+30),fill=tuple(PALETTE[index]))
  drawing.text((left+40,top),f'{index}: {label}',fill='black',font=font)
 path=DEBUG/(name+'-comparison.png');canvas.save(path)
 return str(path)

def merge_manifest(report):
 SCENE.mkdir(parents=True,exist_ok=True)
 with (SCENE/'.manifest.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  path=SCENE/'manifest.json';j=json.loads(path.read_text()) if path.exists() else {}
  j.setdefault('crs',{'horizontal':'EPSG:28992','vertical':'EPSG:5709','compound':'EPSG:7415'})
  j.setdefault('grid',{'size_m':250,'tile_name':'x{xmin}_y{ymin}','gltf_axes':{'X':'RD east minus tile xmin','Y':'NAP metres','Z':'negative RD north offset from tile ymin'}})
  j.setdefault('area',{})[report['area']]={'bounds_rd':AREAS[report['area']]}
  tiles=j.setdefault('tiles',{})
  for name,record in report['tiles'].items():
   if isinstance(tiles,dict):tiles.setdefault(name,{}).update(record)
   else:
    existing=next((r for r in tiles if isinstance(r,dict) and r.get('id',r.get('name'))==name),None)
    if existing is None:tiles.append({'id':name,**record})
    else:existing.update(record)
  j['markings_licence']=report['markings_licence']
  j['class_legend']={str(i):label for i,label in enumerate(LEGEND)}
  j['class_mapping']={'function':FUNCTION_CLASSES,'physical_appearance':APPEARANCE_CLASSES,'plus_physical_appearance':PLUS_APPEARANCE_CLASSES,'collection_defaults':DEFAULT_CLASSES,'municipal_3d':report.get('geometry',{}).get('municipal_class_mapping',{}),'municipal_3d_road_function':report.get('geometry',{}).get('municipal_road_function_mapping',{}),'municipal_3d_appearance':report.get('geometry',{}).get('municipal_appearance_mapping',{}),'code':'pipeline/ground/surfaces.py','unknown':'No unrecorded infill. Current, existing, non-underground features only; relative height orders overlaps.'}
  j.setdefault('sources',{}).update(report['sources']);j.setdefault('ground',{})[report['area']]={k:v for k,v in report.items() if k!='tiles'}
  temp=path.with_suffix('.ground.tmp');temp.write_text(json.dumps(j,indent=2));temp.replace(path)

SURFACES=None
MARKINGS=None
MARKING_TREE=None
MASKS_ONLY=False

def build_tile(tile):
 x,y=tile;name=f'x{x}_y{y}';rgb=ortho(x,y);classes,bits,rails=rasterize(SURFACES,x,y)
 local_markings=[MARKINGS[index] for index in MARKING_TREE.query(box(x,y,x+250,y+250))]
 paint,paint_stats=marking_mask(local_markings,(x,y,x+250,y+250),rgb,classes);bits[paint]|=4
 rgba=np.zeros((2500,2500,4),dtype=np.uint8);rgba[:,:,0]=classes;rgba[:,:,1]=bits;rgba[:,:,3]=255
 path=SCENE/'tiles'/name;Image.fromarray(rgba).save(path/'classes.png')
 counts=np.bincount(classes.ravel(),minlength=len(LEGEND));shares={LEGEND[i]:round(int(n)/classes.size,8) for i,n in enumerate(counts)}
 record={'ground':{'class_pixels':{str(i):int(n) for i,n in enumerate(counts)},'class_shares':shares,'rail_features':rails,'line_pixels':{'tram':int(((bits&1)!=0).sum()),'train_metro':int(((bits&2)!=0).sum()),'marking':int(paint.sum()),'kerb':int(((bits&8)!=0).sum())},'marking_method':paint_stats}}
 if not MASKS_ONLY:record['ground'].update(__import__('geometry').build_tile_geometry(x,y,classes))
 debug_path=None
 if name in ('x90250_y436000','x90250_y436250','x90000_y436250','x90000_y436000','x93000_y436000','x91750_y437500'):
  debug_path=debug_image(name,rgb,classes,bits)
 for filename in ['ortho.jpg','classes.png','ground.glb']:
  f=path/filename
  if f.exists():record['ground'].setdefault('files',{})[filename]={'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}
 return name,record,debug_path

def main():
 global SURFACES,MARKINGS,MARKING_TREE,MASKS_ONLY
 parser=argparse.ArgumentParser()
 parser.add_argument('--area',choices=AREAS,default='core')
 parser.add_argument('--workers',type=int,default=6)
 parser.add_argument('--masks-only',action='store_true')
 args=parser.parse_args();MASKS_ONLY=args.masks_only
 bounds=AREAS[args.area];x0,y0,x1,y1=bounds
 tiles=[(x,y) for y in range(y0,y1,250) for x in range(x0,x1,250)]
 source_bounds=(x0-5,y0-5,x1+5,y1+5) if args.area=='m1' else (89745,435245,92005,436755)
 SURFACES=SurfaceData(source_bounds)
 MARKINGS=fetch_markings(source_bounds)
 MARKING_TREE=STRtree([record['geometry'] for record in MARKINGS])
 print('marking records',len(MARKINGS),flush=True)
 geometry_stats={}
 if not args.masks_only:
  from geometry import prepare_geometry
  geometry_stats=prepare_geometry(bounds)
 # All source preparation threads have joined before fork. Shared arrays remain read-only.
 results={};debug=[]
 with ProcessPoolExecutor(max_workers=args.workers,mp_context=multiprocessing.get_context('fork')) as pool:
  futures={pool.submit(build_tile,tile):tile for tile in tiles}
  for future in as_completed(futures):
   name,record,debug_path=future.result();results[name]=record
   if debug_path:debug.append(debug_path)
   print(f"{len(results)}/{len(tiles)} {name} unknown={record['ground']['class_shares']['unknown']} paint={record['ground']['line_pixels']['marking']}",flush=True)
 results=dict(sorted(results.items()));debug.sort()

 sources={}
 for dataset in ['bgt','ortho2026','rotterdam-markings','ground3d','proj-grids']:
  path=ROOT/'sources'/dataset/DATE/'manifest.json'
  if path.exists():sources[dataset]={'manifest':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
 licence=json.loads(Path(__file__).with_name('markings_licence.json').read_text())
 evidence_manifest=ROOT/'sources/markings-licence-evidence/2026-10-26/manifest.json'
 if evidence_manifest.exists():sources['markings-licence-evidence']={'manifest':str(evidence_manifest),'sha256':hashlib.sha256(evidence_manifest.read_bytes()).hexdigest()}
 totals=np.sum([list(r['ground']['class_pixels'].values()) for r in results.values()],axis=0)
 report={'area':args.area,'bounds_rd':bounds,'tiles':results,'class_shares':{LEGEND[i]:float(n/totals.sum()) for i,n in enumerate(totals)},'sources':sources,'geometry':geometry_stats,'markings_licence':licence,'workers':args.workers,'missing_height_share':sum(r['ground'].get('ground_uncovered_nonbuilding_pixels',0) for r in results.values())/sum(6250000-r['ground']['class_pixels']['11'] for r in results.values()),'debug_images':debug,'method':{'rails':'BGT spoor is per-track centreline (BGT catalog 10.3.1). Standard gauge: offsets +/-0.7175 m, 0.10 m sampled rail mask. Tram bit 1; train/sneltram bit 2. Underground excluded.','markings':'Aerial white top-hat, bright neutral pixels and elongated thin components. Broad neutral vehicle roofs detected at a lower threshold and dilated by 50 cm. Parking omitted conservatively. Municipal register archived and measured as diagnostic support, not an extraction gate; visual M1 check found it missed photographed dashes. No invented glyphs.','kerbs':'4-neighbour class boundaries between carriageway/cycle path and pavement; 10 cm on each side.','uncertainties':['Municipal road-marking public endpoint does not specify licence; no open licence is asserted.','Short dashes, broad symbols, zebra stripes, parking paint, shadows and canopy cause marking omissions. Some elongated vehicle highlights can remain; no perfect semantic vehicle classifier is claimed.','Aerial building lean and tree canopy do not move BGT ground boundaries.']},'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'code_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path(__file__).parent.glob('*.py')}}
 (SCENE/f'ground-{args.area}-report.json').write_text(json.dumps(report,indent=2));merge_manifest(report)
 print('CLASS SHARES',json.dumps(report['class_shares']),flush=True)
if __name__=='__main__':main()
