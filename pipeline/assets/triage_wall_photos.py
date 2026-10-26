#!/usr/bin/env -S .devenv/profile/bin/python
"""Written by AI on 2026-10-26 by model GPT-6 Astra.
Prioritise actual visible facades over roof bleed before detailed C3 measurement.
This source-only classification is an interpretation, never verification.
"""
import argparse
import fcntl
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time

from PIL import Image, ImageDraw
from perceive_walls import CLI, REPOSITORY, configured_model, archive_completed, rate_limit_error, sha, load, save, valid_measurement
from wall_facts import prepare_walls

ROOT=Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
PROMPT='''Task: source-only photographic evidence triage for a faithful Rotterdam miniature. Josh: every component must match the photo; never invent hidden parts. Inspect only the attached labelled contact sheet, no tools, files, writing, browsing or delegation. Each cell is one rectified WALL view from the actual 2018 source mesh. Grey is missing photo evidence. Many wall textures incorrectly show a roof, sky, trees, ground, stretched streaks or neighbours rather than the target facade. Select usable_facade=true ONLY if some actual wall face and its material or complete window/door openings are clearly visible. Mixed views with a visible facade and partial foreground occlusion qualify. Roofs with skylights do not qualify as walls. Tiny ambiguous slivers do not qualify. false means no usable actual facade is distinguishable in this source view; it does not mean the real building has no windows. Do not infer unseen content or a typical street layout. Return JSON only: an array of {"wall_id":"exact label", "usable_facade":true, "note":"brief visible evidence or ambiguity"}, exactly one per inventory entry. This classification will only prioritize detailed measurement and supplies no verified surface mask or facts.'''


def scan(tile,batch_size=96,max_calls=1):
    work=ROOT/'facts/v1/work'/tile
    work.mkdir(parents=True,exist_ok=True)
    tile_lock=(work/'perception.lock').open('a')
    fcntl.flock(tile_lock,fcntl.LOCK_EX)
    walls_path=prepare_walls(tile)
    walls=load(walls_path)['walls']
    work=walls_path.parent
    destination=work/'source-triage.json'
    previous=load(destination) if destination.exists() else {'walls':{}}
    decisions=previous['walls']
    candidates=[wall for wall in walls if wall['street_facing'] and wall['photo_pixels']>0 and not valid_measurement(wall)
                and decisions.get(wall['wall_id'],{}).get('reference_sha256')!=wall['reference_sha256']]
    candidates.sort(key=lambda wall:(not (10<=wall['area_m2']<=100 and wall.get('photo_fraction',0)>=.6),-wall['area_m2']))
    model=configured_model()
    for offset in range(0,min(len(candidates),batch_size*max_calls),batch_size):
        batch=candidates[offset:offset+batch_size]
        identity=hashlib.sha256((PROMPT+model+''.join(w['wall_id']+w['reference_sha256'] for w in batch)).encode()).hexdigest()
        folder=work/'source-triage-calls'/identity
        folder.mkdir(parents=True,exist_ok=True)
        columns,cell_width,cell_height=8,230,190
        sheet=Image.new('RGB',(columns*cell_width,((len(batch)+columns-1)//columns)*cell_height),'white')
        draw=ImageDraw.Draw(sheet)
        for index,wall in enumerate(batch):
            x,y=(index%columns)*cell_width,(index//columns)*cell_height
            image=Image.open(wall['reference']).convert('RGB');image.thumbnail((220,160))
            sheet.paste(image,(x+5,y+25));draw.text((x+5,y+5),wall['wall_id'],fill='black')
        image_path=folder/'source-views.jpg';sheet.save(image_path,quality=95)
        prompt=PROMPT+'\nInventory:\n'+json.dumps([{'wall_id':w['wall_id'],'reference_sha256':w['reference_sha256']} for w in batch])
        (folder/'prompt.txt').write_text(prompt)
        answer=folder/'answer.json';timing=folder/'call.json'
        if not answer.exists():
            start=time.monotonic();started=datetime.now(timezone.utc).isoformat()
            command=[CLI,'exec','--json','--skip-git-repo-check','-C',str(REPOSITORY),'-o',str(answer),'-i',str(image_path),'-']
            with (folder/'events.jsonl').open('w') as stdout,(folder/'stderr.txt').open('w') as stderr:
                try: result=subprocess.run(command,input=prompt,text=True,stdout=stdout,stderr=stderr,timeout=900)
                except subprocess.TimeoutExpired:
                    save(timing,{'model':model,'started_at':started,'seconds':time.monotonic()-start,'status':'timeout','wall_count':len(batch)})
                    raise SystemExit(75)
            events=(folder/'events.jsonl').read_text();limited=rate_limit_error(events,(folder/'stderr.txt').read_text())
            save(timing,{'model':model,'started_at':started,'seconds':time.monotonic()-start,'returncode':result.returncode,'rate_limited':limited,'wall_count':len(batch),'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest()})
            if limited or result.returncode: raise SystemExit(75)
            archive_completed(events,folder)
        text=answer.read_text().strip()
        if text.startswith('```'):text=text[text.index('\n')+1:text.rfind('```')]
        values=json.loads(text);by_id={value['wall_id']:value for value in values}
        if len(values)!=len(batch) or set(by_id)!={wall['wall_id'] for wall in batch}:
            raise ValueError('Source triage omitted, duplicated or invented wall IDs')
        for wall in batch:
            value=by_id[wall['wall_id']]
            if not isinstance(value.get('usable_facade'),bool):raise ValueError('Invalid source triage class')
            decisions[wall['wall_id']]=dict(value,reference_sha256=wall['reference_sha256'],model=model,date=datetime.now(timezone.utc).isoformat(),prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),reference=wall['reference'],response=str(answer),verified_fraction=0)
        save(destination,{'written_by':'AI, GPT-6 Astra, 2026-10-26','tile':tile,'source_sha256':load(walls_path)['source']['sha256'],'method':'source-only-facade-triage-not-verification','walls':decisions})
        print(json.dumps({'tile':tile,'views_classified':len(batch),'usable_facades':sum(value['usable_facade'] for value in values),'call':str(timing)}),flush=True)
    return destination

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tile',required=True)
    parser.add_argument('--batch-size',type=int,default=96)
    parser.add_argument('--max-calls',type=int,default=1)
    args=parser.parse_args();scan(args.tile,args.batch_size,args.max_calls)
