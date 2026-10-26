"""Written by AI on 2026-10-26 by model GPT-6 Astra. Roof evidence plumbing."""
import argparse
import json
from pathlib import Path
from PIL import Image

ROOT = Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
OUTPUT = ROOT / 'assets/v1/roofs/x90250_y436000'

def prepare():
    source = ROOT / 'scene/v1/tiles/x90250_y436000/ortho.jpg'
    image = Image.open(source).convert('RGB')
    assert image.size == (2500, 2500)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    records = []
    for name, box in [('nw', (0,0,1250,1250)), ('ne',(1250,0,2500,1250)),
                      ('sw',(0,1250,1250,2500)), ('se',(1250,1250,2500,2500))]:
        folder = OUTPUT / name
        folder.mkdir(exist_ok=True)
        path = folder / 'reference.png'
        if not path.exists():
            image.crop(box).save(path)
        records.append({'id':name, 'rectangle_px':list(box), 'reference':str(path)})
    manifest = {'written_by':'AI, GPT-6 Astra, 2026-10-26', 'source':str(source),
                'size_px':[2500,2500], 'pixel_size_m':0.1,
                'upper_left_rd':[90250,436250], 'quadrants':records}
    (OUTPUT / 'reference.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(manifest))

def assemble():
    manifest=json.loads((OUTPUT/'reference.json').read_text())
    canvas=Image.new('RGB',(2500,2500))
    for record in manifest['quadrants']:
        raw=OUTPUT/record['id']/'generated-raw.png'
        resized=Image.open(raw).convert('RGB').resize((1250,1250), Image.Resampling.LANCZOS)
        resized.save(raw.parent/'generated.webp',format='WEBP',quality=90,method=6)
        canvas.paste(resized,tuple(record['rectangle_px'][:2]))
    canvas.save(OUTPUT/'roof.webp',format='WEBP',quality=90,method=6)
    print(OUTPUT/'roof.webp')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','assemble'])
    args=parser.parse_args()
    globals()[args.command]()
