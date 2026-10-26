"""Overview aerial comparison image. Written by AI, GPT-6, 2026-10-26."""
import json
from pathlib import Path
from PIL import Image, ImageDraw
ROOT = Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
SCENE = ROOT / 'scene/overview-v1'
index = json.loads((SCENE / 'tile-index.json').read_text())
records = index['tiles']
xs = [record['bounds_rd'][0] for record in records.values()]
ys = [record['bounds_rd'][1] for record in records.values()]
left, bottom, right, top = min(xs), min(ys), max(xs) + 1000, max(ys) + 1000
image = Image.new('RGB', ((right-left)//8, (top-bottom)//8), '#e6e6e6')
for tile_id, record in records.items():
    x, y, _, _ = record['bounds_rd']
    source = Image.open(SCENE / 'tiles' / tile_id / 'ortho.jpg')
    image.paste(source.resize((125, 125), Image.Resampling.LANCZOS), ((x-left)//8, (top-y-1000)//8))
output = ROOT / 'renders/overview'
output.mkdir(parents=True, exist_ok=True)
image.save(output / 'aerial-8m.png')
print(output / 'aerial-8m.png')
