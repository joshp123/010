#!/usr/bin/env -S .devenv/profile/bin/python
"""Written by AI on 2026-10-26 by GPT-6 Astra. Show the actual ten paired assets."""
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path('/Volumes/Josh Extreme Pro USB4 4TB/010/assets/v1/tiles/x90250_y436000')

def main():
    directory = ROOT/'tier2-comparison'
    selection = json.loads((directory/'selection.json').read_text())
    composition = json.loads((ROOT/'composed/composition.json').read_text())
    records = {w['wall_id']:w for w in composition['walls']}
    atlases = [Image.open(a['path']).convert('RGB') for a in composition['atlases']]
    sheet = Image.new('RGB',(2000,2700),'#eeeae1')
    draw = ImageDraw.Draw(sheet)
    draw.text((20,12),'Ten measured walls: photo evidence | tier 2 parts composition | tier 1 redraw',fill='black')
    draw.text((20,28),'Common 5 cm pixel grid. Interpreted styling is not verification. Labels identify comparison rows.',fill='black')
    manifest=[]
    for i,item in enumerate(selection):
        wall=item['wall']; record=records[wall['wall_id']]
        image=atlases[record['atlas_index']].crop(tuple(record['rectangle_px']))
        source=Image.open(wall['reference']).convert('RGB')
        generated_path=directory/f'tier1-{i+1:02d}.png'
        generated=Image.open(generated_path).convert('RGB').resize(source.size,Image.Resampling.LANCZOS)
        mask=Image.new('L',source.size);md=ImageDraw.Draw(mask)
        for triangle in wall['triangles']:
            md.polygon([tuple(p) for p in triangle['pixel_vertices']],fill=255)
        images=[source,image,generated]
        x=(i%2)*1000;y=65+(i//2)*525
        draw.text((x+12,y),f'{i+1:02d}  {wall["wall_id"]}',fill='black')
        for j,im in enumerate(images):
            clean=Image.new('RGB',source.size,'white');clean.paste(im,(0,0),mask)
            scale=min(305/clean.width,480/clean.height)
            clean=clean.resize((round(clean.width*scale),round(clean.height*scale)),Image.Resampling.NEAREST)
            sheet.paste(clean,(x+j*325+12,y+32))
            draw.text((x+j*325+12,y+17),['Photo evidence','Tier 2 composed','Tier 1 generated'][j],fill='black')
        manifest.append({'wall_id':wall['wall_id'],'reference':wall['reference'],'generated':str(generated_path),'generated_sha256':hashlib.sha256(generated_path.read_bytes()).hexdigest(),'composition_fingerprint':composition['input_fingerprint'],'style_verified':False})
    path=directory/'tier2-vs-tier1.png';sheet.save(path)
    (directory/'comparison.json').write_text(json.dumps({'written_by':'AI, GPT-6 Astra, 2026-10-26','method':'Native 5cm composition versus independently generated facade resized to the same evidence framing; geometry masks applied equally','walls':manifest},indent=2)+'\n')
    print(path)

if __name__ == '__main__':
    main()
