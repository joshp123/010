#!/usr/bin/env -S .devenv/profile/bin/python
"""Written by AI on 2026-10-26 by GPT-6 Astra. Tile roof evidence plumbing."""
import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from PIL import Image

ROOT = Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
DEFAULT_TILE = os.environ.get('ASSET_TILE', 'x90250_y436000')


def prepare(tile=DEFAULT_TILE):
    source = ROOT / 'scene/v1/tiles' / tile / 'ortho.jpg'
    image = Image.open(source).convert('RGB')
    if image.size != (2500, 2500):
        raise ValueError(f'Expected 2500px tile aerial: {source}: {image.size}')
    output = ROOT / 'assets/v1/roofs' / tile
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for name, box in [('nw', (0,0,1250,1250)), ('ne',(1250,0,2500,1250)),
                      ('sw',(0,1250,1250,2500)), ('se',(1250,1250,2500,2500))]:
        folder = output / name
        folder.mkdir(exist_ok=True)
        path = folder / 'reference.png'
        if not path.exists():
            image.crop(box).save(path)
        records.append({'id':name, 'rectangle_px':list(box), 'reference':str(path)})
    x, y = map(int, tile[1:].split('_y'))
    manifest = {'written_by':'AI, GPT-6 Astra, 2026-10-26', 'tile':tile, 'source':str(source),
                'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                'size_px':[2500,2500], 'pixel_size_m':0.1,
                'upper_left_rd':[x,y+250], 'quadrants':records}
    (output / 'reference.json').write_text(json.dumps(manifest, indent=2)+'\n')
    return manifest


def save_webp(image, destination):
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.webp', delete=False) as temporary:
        pending = Path(temporary.name)
    image.save(pending, format='WEBP', quality=90, method=6)
    pending.replace(destination)


def assemble(tile=DEFAULT_TILE):
    output = ROOT / 'assets/v1/roofs' / tile
    manifest=json.loads((output/'reference.json').read_text())
    canvas=Image.new('RGB',(2500,2500))
    for record in manifest['quadrants']:
        raw=output/record['id']/'generated-raw.png'
        resized=Image.open(raw).convert('RGB').resize((1250,1250), Image.Resampling.LANCZOS)
        save_webp(resized, raw.parent/'generated.webp')
        canvas.paste(resized,tuple(record['rectangle_px'][:2]))
    save_webp(canvas, output/'roof.webp')
    return str(output/'roof.webp')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','assemble'])
    parser.add_argument('--tile',default=DEFAULT_TILE)
    args=parser.parse_args()
    print(json.dumps(globals()[args.command](args.tile)))
