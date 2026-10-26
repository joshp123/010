#!/usr/bin/env -S .devenv/profile/bin/python
"""Written by AI, GPT-6 Codex, 2026-10-26. Source-only full-resolution aperture review."""
import argparse
from datetime import datetime,timezone
import fcntl
import hashlib
import json
import subprocess
import time
from PIL import Image,ImageDraw
import perceive_walls as c3

PROMPT='''Inventory every directly visible outer window, door and shop-front aperture in the attached original Rotterdam facade photo. Work only from this photo. No tools, files, browsing, writing or delegation. Match the actual source, never extrapolate a typical pattern into obscured areas. One outer aperture includes its entire frame; glazing lights inside that frame are inner divisions, not additional outer apertures. Separate apertures have visible masonry between them. Fit complete outer frame boundaries. Include visible small apertures. Partial apertures retain only their visible extent and partial=true. Return JSON only: {"openings":[{"kind":"window|door|shop_front","box":[left,top,right,bottom],"type":"sash_with_transom|casement|modern|other|unknown","partial":false,"vertical_divisions":[],"horizontal_divisions":[],"divisions_observed":false}],"window_rows":[{"window_indices":[]}],"note":"uncertainty only"}. Coordinates are integer pixels of the original attached photo, origin top-left. Inner bar centrelines are normalized0..1 relative to each aperture box. List only resolved observed bars, never derive a regular division pattern from a type label. Unresolved inner bars use empty arrays and divisions_observed=false. A clearly undivided frame uses empty arrays and divisions_observed=true. Do not estimate colour or material.'''


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--tile',required=True);parser.add_argument('--wall-id',required=True)
    args=parser.parse_args();c3.TILE=args.tile;c3.WORK=c3.ROOT/'facts/v1/work'/args.tile
    c3.TILE_X,c3.TILE_Y=map(int,args.tile[1:].split('_y'))
    lock=(c3.WORK/'perception.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX)
    c3.ALL_WALLS=c3.load(c3.WORK/'walls.json')['walls'];wall=next(w for w in c3.ALL_WALLS if w['wall_id']==args.wall_id)
    model=c3.configured_model();size=Image.open(wall['reference']).size
    prompt=PROMPT+'\nPhoto dimensions: '+json.dumps(list(size))+'.'
    identity=hashlib.sha256((prompt+model+wall['reference_sha256']).encode()).hexdigest()
    directory=c3.WORK/'geometry-batches'/identity;directory.mkdir(parents=True,exist_ok=True)
    (directory/'prompt.txt').write_text(prompt);answer=directory/'answer.json'
    if not answer.exists():
        started=datetime.now(timezone.utc).isoformat();clock=time.monotonic()
        command=[c3.CLI,'exec','--json','--skip-git-repo-check','-C',str(c3.REPOSITORY),'-o',str(answer),'-i',wall['reference'],'-']
        with (directory/'events.jsonl').open('w') as stdout,(directory/'stderr.txt').open('w') as stderr:
            completed=subprocess.run(command,input=prompt,text=True,stdout=stdout,stderr=stderr,timeout=900)
        events=(directory/'events.jsonl').read_text();limited=c3.rate_limit_error(events,(directory/'stderr.txt').read_text())
        c3.save(directory/'call.json',{'model':model,'started_at':started,'ended_at':datetime.now(timezone.utc).isoformat(),'seconds':time.monotonic()-clock,'returncode':completed.returncode,'rate_limited':limited,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest()})
        c3.archive_completed(events,directory)
        if limited or completed.returncode:raise SystemExit('Source aperture review stopped: rate limit or failed native call')
    result=json.loads(answer.read_text().removeprefix('```json').removeprefix('```').removesuffix('```').strip())
    previous=c3.load(c3.Path(wall['reference']).parent/'perception.json')
    provenance={'model':model,'date':datetime.now(timezone.utc).isoformat(),'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'reference_hashes':{wall['reference']:wall['reference_sha256']},'response':str(answer),'call':str(directory/'call.json'),'method':'source-only-full-resolution-apertures'}
    inventory={'wall_scale':[1,1],'wall_display_size_px':list(size),'roof_display_size_px':[1,1],'roof_aerial_rectangle_px':[0,0,1,1],'roof_display_scale':1}
    fact=c3.measure(wall,result,inventory,provenance,preserved=previous)
    keys=('window_rows','openings','rejected_openings','doors','shop_fronts','source_partial_openings')
    c3.save(c3.Path(wall['reference']).parent/'geometry-observations.json',{'wall_id':wall['wall_id'],'reference_sha256':wall['reference_sha256'],'aperture_facts':{key:fact[key] for key in keys},'provenance':provenance})
    photo=Image.open(wall['reference']).convert('RGB')
    geometry=Image.open(c3.Path(wall['reference']).parent/'geometry-mask.png').convert('L')
    overlay=Image.composite(photo,Image.new('RGB',photo.size,'white'),geometry);draw=ImageDraw.Draw(overlay)
    for key,colour in [('openings','lime'),('rejected_openings','orange')]:
        for opening in fact[key]:
            if not opening.get('box_px'):continue
            draw.rectangle(opening['box_px'],outline=colour,width=1)
            draw.text(tuple(opening['box_px'][:2]),str(opening['source_index']),fill=colour)
    overlay.save(directory/'source-apertures.png')
    c3.publish();print(json.dumps({'wall_id':wall['wall_id'],'complete_openings':len(fact['openings']),'partial_openings':len(fact['source_partial_openings']),'rejected':len(fact['rejected_openings']),'directory':str(directory)}),flush=True)


if __name__=='__main__':main()
