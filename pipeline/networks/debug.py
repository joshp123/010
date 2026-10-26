"""Render archived 2026 aerial network proofs.

Written by AI on 2026-10-26 by model GPT-6 Astra.
"""
import argparse
import datetime
import hashlib
import io
import json
import math
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import shape

ROOT = Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
SOURCE = ROOT / 'sources/network-ortho/2026-10-26'
OUTPUT = ROOT / 'renders/debug-networks'
WMS = 'https://service.pdok.nl/hwh/luchtfotorgb/wms/v1_0'
METADATA = ('https://www.nationaalgeoregister.nl/geonetwork/srv/api/records/'
            '4d8e14a9-302c-48e7-a0ee-1b23ed2a2122/formatters/xml')
M1 = (89750, 434750, 96500, 438000)
CAR = '#00eaff'
BIKE = '#ff4fd8'


def archive(name, url):
    SOURCE.mkdir(parents=True, exist_ok=True)
    manifest_path = SOURCE / 'manifest.json'
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
        'dataset': 'PDOK 2026_orthoHR', 'license': 'CC-BY-4.0',
        'license_url': 'https://creativecommons.org/licenses/by/4.0/',
        'credit': 'Beeldmateriaal.nl / PDOK', 'metadata_url': METADATA, 'files': {}}
    path = SOURCE / name
    if path.exists():
        raw = path.read_bytes()
        assert manifest['files'][name]['url'] == url
        assert manifest['files'][name]['sha256'] == hashlib.sha256(raw).hexdigest()
    else:
        response = requests.get(url, timeout=120)
        response.raise_for_status()
        raw = response.content
        if name.endswith('.jpg'):
            Image.open(io.BytesIO(raw)).verify()
        path.write_bytes(raw)
        manifest['files'][name] = {'url': url, 'sha256': hashlib.sha256(raw).hexdigest(),
                                  'bytes': len(raw), 'fetched_at': datetime.datetime.now(datetime.timezone.utc).isoformat()}
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    return raw


def street_bounds(name):
    bounds = [shape(f['geometry']).bounds
              for path in (ROOT / 'sources/nwb-networks/2026-10-26').glob('page-*.json')
              for f in json.loads(path.read_text())['features']
              if f['properties']['stt_naam'] == name]
    if not bounds:
        raise ValueError(f'No NWB street named {name}')
    return (max(M1[0], math.floor(min(b[0] for b in bounds) - 80)),
            max(M1[1], math.floor(min(b[1] for b in bounds) - 80)),
            min(M1[2], math.ceil(max(b[2] for b in bounds) + 80)),
            min(M1[3], math.ceil(max(b[3] for b in bounds) + 80)))


def aerial(name, bounds, resolution):
    width = math.ceil((bounds[2] - bounds[0]) / resolution)
    height = math.ceil((bounds[3] - bounds[1]) / resolution)
    params = {'SERVICE': 'WMS', 'VERSION': '1.3.0', 'REQUEST': 'GetMap',
              'LAYERS': '2026_orthoHR', 'STYLES': '', 'CRS': 'EPSG:28992',
              'BBOX': ','.join(map(str, bounds)), 'WIDTH': width, 'HEIGHT': height,
              'FORMAT': 'image/jpeg', 'TRANSPARENT': 'FALSE'}
    url = requests.Request('GET', WMS, params=params).prepare().url
    return Image.open(io.BytesIO(archive(f'{name}-{resolution}m.jpg', url))).convert('RGB')


def font(size):
    for path in ['/System/Library/Fonts/Supplemental/Arial.ttf', '/System/Library/Fonts/Helvetica.ttc']:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def render(name, bounds, resolution, graphs):
    raw = aerial(name, bounds, resolution)
    overlay = raw.copy()
    draw = ImageDraw.Draw(overlay)
    sx = raw.width / (bounds[2] - bounds[0])
    sy = raw.height / (bounds[3] - bounds[1])

    def pixel(node):
        return ((node[0] - bounds[0]) * sx, (bounds[3] - node[1]) * sy)

    for graph, color in zip(graphs, [CAR, BIKE]):
        nodes = graph['nodes']
        metadata = ([graph['ways'][index] for index in graph['edge_ways']]
                    if 'edge_ways' in graph else graph.get('edge_metadata', [{} for _ in graph['edges']]))
        arrow_distance_by_way = {}
        for edge, attributes in zip(graph['edges'], metadata):
            start, end = nodes[edge[0]], nodes[edge[1]]
            if max(start[0], end[0]) < bounds[0] or min(start[0], end[0]) > bounds[2] or max(start[1], end[1]) < bounds[1] or min(start[1], end[1]) > bounds[3]:
                continue
            a, b = pixel(start), pixel(end)
            width = (4 if resolution == 1 else 3) if color == CAR else (2 if resolution == 1 else 1)
            draw.line([a, b], fill=color, width=width)
            if attributes.get('oneway'):
                dx, dy = b[0] - a[0], b[1] - a[1]
                length = math.hypot(dx, dy)
                way_id = attributes.get('wvk_id', id(attributes))
                arrow_distance_by_way[way_id] = arrow_distance_by_way.get(way_id, 25 * sx) + length
                if length >= 2 and arrow_distance_by_way[way_id] >= 40 * sx:
                    arrow_distance_by_way[way_id] = 0
                    ux, uy = dx / length, dy / length
                    center = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                    tip = (center[0] + 3.5 * ux, center[1] + 3.5 * uy)
                    draw.line([(center[0] - 3.5 * ux - 3.5 * uy, center[1] - 3.5 * uy + 3.5 * ux), tip,
                               (center[0] - 3.5 * ux + 3.5 * uy, center[1] - 3.5 * uy - 3.5 * ux)], fill=color, width=min(width, 2))
    # Crop panels keep every source pixel, with raw imagery available beside the graph.
    panels = [raw, overlay] if resolution == 1 else [overlay]
    banner = 84
    result = Image.new('RGB', (sum(p.width for p in panels), raw.height + banner), '#16212a')
    label_draw = ImageDraw.Draw(result)
    x = 0
    for i, panel in enumerate(panels):
        result.paste(panel, (x, banner))
        label = '2026 aerial' if len(panels) == 2 and i == 0 else 'Network overlay'
        label_draw.text((x + 10, 8), f'{name} | {resolution} m/px | {label}', fill='white', font=font(14))
        label_draw.text((x + 10, 30), 'Cyan: cars | magenta: bikes | arrows: one-way | north up', fill='white', font=font(12))
        label_draw.text((x + 10, 50), 'Aerial: Beeldmateriaal.nl / PDOK (CC BY 4.0)', fill='white', font=font(12))
        x += panel.width
    # A 100 m scale bar is drawn on each panel.
    for panel_index in range(len(panels)):
        x0, y0 = panel_index * raw.width + 15, result.height - 20
        label_draw.line([(x0, y0), (x0 + 100 * sx, y0)], fill='white', width=4)
        label_draw.text((x0, y0 - 19), '100 m', fill='white', stroke_width=1, stroke_fill='black', font=font(12))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / f'{name}-{resolution}m.png'
    result.save(path)
    return {'path': str(path), 'bbox_rd': bounds, 'metres_per_pixel': resolution,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch-only', action='store_true')
    args = parser.parse_args()
    archive('metadata.xml', METADATA)
    archive('capabilities.xml', WMS + '?SERVICE=WMS&REQUEST=GetCapabilities')
    views = [('m1', M1, 2), ('coolsingel', street_bounds('Coolsingel'), 1),
             ('schiedamseweg', street_bounds('Schiedamseweg'), 1)]
    if args.fetch_only:
        for name, bounds, resolution in views:
            im = aerial(name, bounds, resolution)
            print(name, bounds, im.size, flush=True)
        return
    graphs = [json.loads((ROOT / f'scene/v1/networks/{mode}.json').read_text()) for mode in ['cars', 'bikes']]
    outputs = [render(name, bounds, resolution, graphs) for name, bounds, resolution in views]
    (OUTPUT / 'manifest.json').write_text(json.dumps({'images': outputs, 'aerial_credit': 'Beeldmateriaal.nl / PDOK',
                                                    'aerial_license': 'CC-BY-4.0'}, indent=2) + '\n')
    print(json.dumps(outputs, indent=2))


if __name__ == '__main__':
    main()
