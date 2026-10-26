#!/usr/bin/env -S .devenv/profile/bin/python
"""Written by AI on 2026-10-26 by GPT-6 Astra. Extract reusable generated parts, never photos."""
import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image
ROOT=Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
DIRECTORY=ROOT/'assets/v1/parts'
COMPARISON=ROOT/'assets/v1/tiles/x90250_y436000/tier2-comparison'

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def derive():
 DIRECTORY.mkdir(parents=True,exist_ok=True)
 source=COMPARISON/'tier1-01.png'
 if not source.exists():raise ValueError('Generate comparison tier1-01.png first')
 image=Image.open(source).convert('RGB')
 # Independently inspected generated bounds: an asset image, not source evidence.
 crops=[('brick-01','material','brick',[216,218,290,539],[11,45]),
        ('sash-01','window','sash_with_transom',[39,193,216,532],[25,48]),
        ('sash-02','window','sash_with_transom',[295,662,471,998],[25,48]),
        ('window-short-01','window','unknown',[105,1125,218,1269],[16,20]),
        ('door-01','door','unknown',[479,1313,626,1770],[21,65]),
        ('lintel-01','lintel','arched',[23,125,251,193],[32,10]),
        ('keystone-01','keystone','plain',[113,127,143,184],[4,8]),
        ('cornice-01','cornice','plain',[218,1278,460,1312],[34,5]),
        ('cornice-moulded-01','cornice','moulded',[0,0,780,78],[110,11])]
 parts=[]
 for name,kind,typ,box,size in crops:
  path=DIRECTORY/f'{name}.png'
  image.crop(box).resize(tuple(size),Image.Resampling.BOX).save(path)
  parts.append({'id':name,'kind':kind,'type':typ,'path':path.name,'sha256':digest(path),
                'source_generated_image':str(source),'source_generated_sha256':digest(source),
                'crop_px':box,'image_size_px':size,'pixel_size_m':.05,
                'verified_fraction':0,'interpreted_fraction':1})
 # Add broad modern shopfront and casement styles from the generated gabled elevation.
 source2=COMPARISON/'tier1-02.png'
 if source2.exists():
  second=Image.open(source2).convert('RGB')
  for name,kind,typ,box,size in [('shop-01','shop_front','unknown',[162,1716,559,2041],[56,46]),
      ('balcony-railing-01','balcony','railing',[204,432,475,584],[45,25]),
      ('balcony-glass-01','balcony','glass',[52,834,219,976],[28,24]),
      ('casement-01','window','casement',[58,685,209,836],[22,22])]:
   path=DIRECTORY/f'{name}.png';second.crop(box).resize(tuple(size),Image.Resampling.BOX).save(path)
   parts.append({'id':name,'kind':kind,'type':typ,'path':path.name,'sha256':digest(path),
    'source_generated_image':str(source2),'source_generated_sha256':digest(source2),'crop_px':box,
    'image_size_px':size,'pixel_size_m':.05,'verified_fraction':0,'interpreted_fraction':1})
 source7=COMPARISON/'tier1-07.png'
 if source7.exists():
  seventh=Image.open(source7).convert('RGB')
  for name,kind,typ,box,size in [('glazing-strip-01','glazing_strip','unknown',[81,611,690,737],[100,21]),
       ('modern-01','window','modern',[196,54,399,289],[33,38])]:
   path=DIRECTORY/f'{name}.png';seventh.crop(box).resize(tuple(size),Image.Resampling.BOX).save(path)
   parts.append({'id':name,'kind':kind,'type':typ,'path':path.name,'sha256':digest(path),
     'source_generated_image':str(source7),'source_generated_sha256':digest(source7),'crop_px':box,
     'image_size_px':size,'pixel_size_m':.05,'verified_fraction':0,'interpreted_fraction':1})
 source3=COMPARISON/'tier1-03.png'
 if source3.exists():
  third=Image.open(source3).convert('RGB')
  for name,kind,box,bounds in [
      ('canopy-dentil-01','cornice',[10,1270,688,1369],[2,143,100,157]),
      ('canopy-recess-crests-01','glazing_strip',[20,1369,683,1466],[5,157,97,180]),
      ('canopy-red-panel-01','canopy_front',[20,1466,683,1566],[6,180,97,198])]:
   size=[bounds[2]-bounds[0],bounds[3]-bounds[1]]
   path=DIRECTORY/f'{name}.png';third.crop(box).resize(tuple(size),Image.Resampling.BOX).save(path)
   parts.append({'id':name,'kind':kind,'type':'source-canopy-style','path':path.name,'sha256':digest(path),
    'source_generated_image':str(source3),'source_generated_sha256':digest(source3),'crop_px':box,
    'image_size_px':size,'pixel_size_m':.05,'verified_fraction':0,'interpreted_fraction':1,
    'applies_to_wall':'0599100000671619:side-004','applies_to_rectangle_px':bounds,
    'interpretation':'Local style only. Source-visible canopy zone bounds are measured; crest/dentil shape and spacing are interpreted, not verified openings or storeys.'})
 records_path=COMPARISON/'generation-records.json'
 records={r['image']:r for r in json.loads(records_path.read_text())['outputs']} if records_path.exists() else {}
 for part in parts:
  record=records.get(part['source_generated_image'],{})
  for field in ('model','prompt_sha256','reference','reference_sha256'):
   part[field]=record.get(field)
 result={'written_by':'AI, GPT-6 Astra, 2026-10-26','date':datetime.now(timezone.utc).isoformat(),
 'model':'built-in image generation, exact model not reported','method':'reusable crops from model-made comparison elevations',
 'prompt_hashes':sorted({p['prompt_sha256'] for p in parts if p.get('prompt_sha256')}),
 'generation_records':str(records_path),'generation_records_sha256':digest(records_path) if records_path.exists() else None,
 'reference_hashes':{p['source_generated_image']:p['source_generated_sha256'] for p in parts},
 'photo_texels_retained':0,'verified_fraction':0,'interpreted_fraction':1,
 'scope':'Parts provide interpreted style only; source facts determine placement and scalar material colour. No full facade is reused as tier 2.',
 'parts':parts}
 (DIRECTORY/'library.json').write_text(json.dumps(result,indent=2)+'\n')
 (DIRECTORY/'provenance.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'parts':len(parts),'directory':str(DIRECTORY)}))
if __name__=='__main__':derive()
