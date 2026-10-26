"""Written by AI on 2026-10-26 by model GPT-6 Astra. Inspect delivered overview files."""
import gzip
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
SCENE = ROOT / 'scene/overview-v1'
RENDERS = ROOT / 'renders/overview'
COLORS = [(220, 211, 201), (155, 154, 145), (185, 141, 119), (201, 193, 175),
          (155, 153, 149), (145, 136, 119), (152, 177, 126), (105, 146, 98),
          (82, 145, 173), (215, 201, 158), (179, 175, 160), (215, 212, 203),
          (181, 162, 139), (144, 134, 120), (151, 140, 124), (187, 180, 158),
          (139, 132, 118)]


def draw_geometry(draw, geometry, bounds, resolution, fill, holes=None, outline=None):
    if geometry['type'] == 'MultiPolygon':
        for polygon in geometry['coordinates']:
            draw_geometry(draw, {'type': 'Polygon', 'coordinates': polygon}, bounds, resolution, fill, holes, outline)
    elif geometry['type'] == 'Polygon':
        for n, ring in enumerate(geometry['coordinates']):
            points = [((x - bounds[0]) / resolution, (bounds[3] - y) / resolution) for x, y, *_ in ring]
            if n == 0:
                draw.polygon(points, fill=fill, outline=outline)
            elif holes is not None:
                draw.polygon(points, fill=holes)


def render(index, footprints, bounds, resolution, prefix):
    width = math.ceil((bounds[2] - bounds[0]) / resolution)
    height = math.ceil((bounds[3] - bounds[1]) / resolution)
    classes = Image.new('RGB', (width, height), COLORS[0])
    aerial = Image.new('RGB', (width, height), (235, 234, 227))
    palette = np.array(COLORS, dtype=np.uint8)
    for tile, record in index['tiles'].items():
        xmin, ymin, xmax, ymax = record['bounds_rd']
        if xmax <= bounds[0] or xmin >= bounds[2] or ymax <= bounds[1] or ymin >= bounds[3]:
            continue
        directory = SCENE / 'tiles' / tile
        side = round(1000 / resolution)
        with Image.open(directory / 'classes.png') as source:
            raster = np.asarray(source.resize((side, side), Image.Resampling.NEAREST))
        image = palette[raster[:, :, 0]]
        image[(raster[:, :, 1] & 3) != 0] = (95, 74, 64)
        offset = (round((xmin - bounds[0]) / resolution), round((bounds[3] - ymax) / resolution))
        classes.paste(Image.fromarray(image), offset)
        with Image.open(directory / 'ortho.jpg') as source:
            aerial.paste(source.resize((side, side), Image.Resampling.LANCZOS), offset)
    mask = Image.new('L', classes.size)
    draw_geometry(ImageDraw.Draw(mask), index['boundary_rd'], bounds, resolution, 255, holes=0)
    background = Image.new('RGB', classes.size, (245, 244, 237))
    classes = Image.composite(classes, background, mask)
    aerial = Image.composite(aerial, background, mask)
    classes.save(RENDERS / f'{prefix}-classes.png')
    building_layer = Image.new('RGBA', classes.size)
    draw = ImageDraw.Draw(building_layer)
    for feature in footprints['features']:
        height_m = feature['properties']['height_m']
        shade = max(65, round(95 - min(height_m, 100) * .25))
        color = (shade + 20, shade + 15, shade + 9, 255)
        draw_geometry(draw, feature['geometry'], bounds, resolution, color, holes=(0, 0, 0, 0))
    classes = Image.alpha_composite(classes.convert('RGBA'), building_layer).convert('RGB')
    classes = Image.composite(classes, background, mask)
    classes.save(RENDERS / f'{prefix}.png')
    aerial.save(RENDERS / f'{prefix}-aerial.jpg', quality=92)
    return {'bounds_rd': bounds, 'resolution_m': resolution, 'pixels': [width, height],
            'mosaic': str(RENDERS / f'{prefix}.png'), 'aerial': str(RENDERS / f'{prefix}-aerial.jpg')}


def main():
    RENDERS.mkdir(parents=True, exist_ok=True)
    index = json.loads((SCENE / 'tile-index.json').read_text())
    footprints = json.loads(gzip.decompress((SCENE / 'building-footprints.geojson.gz').read_bytes()))
    bounds = [min(r['bounds_rd'][0] for r in index['tiles'].values()),
              min(r['bounds_rd'][1] for r in index['tiles'].values()),
              max(r['bounds_rd'][2] for r in index['tiles'].values()),
              max(r['bounds_rd'][3] for r in index['tiles'].values())]
    report = {'whole': render(index, footprints, bounds, 8, 'gemeente-8m')}
    # Spatial windows for visual comparison, not semantic reconstruction rules.
    for name, window in {
        'maasvlakte': [55000, 435000, 66000, 445000],
        'hoek-van-holland': [65000, 440000, 72000, 447000],
        'rozenburg': [74500, 433000, 83500, 439000],
        'pernis-waalhaven': [81500, 430000, 92000, 437000],
        'centre-east': [90000, 431000, 102000, 447000],
    }.items():
        report[name] = render(index, footprints, window, 4, name)
    (RENDERS / 'mosaic-report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report['whole']), flush=True)


if __name__ == '__main__':
    main()
