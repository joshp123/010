#!/usr/bin/env python3
"""Exact BGT pixel-centre audit. Written by AI, GPT-6 Astra, 2026-10-26."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
import json
from pathlib import Path
import shutil
import time

import numpy as np
from PIL import Image, ImageDraw
import shapely

ROOT = Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
BOUNDS = (89750, 434750, 96500, 438000)
PALETTE = np.array([
    [32,34,37], [112,112,112], [119,87,91], [69,69,65], [91,89,82],
    [105,98,81], [53,72,49], [43,60,42], [42,65,80], [75,69,55],
    [80,76,69], [59,58,58], [119,114,101], [70,71,70], [88,83,75],
    [80,77,62], [69,67,63]], dtype=np.uint8)


def load_graph(path):
    raw = path.read_bytes()
    graph = json.loads(raw)
    nodes = np.asarray(graph['nodes'], dtype=float)
    pairs = np.asarray([edge[:2] for edge in graph['edges']], dtype=np.int64)
    pairs = np.unique(np.sort(pairs, axis=1), axis=0)
    lines = shapely.linestrings(nodes[pairs, :2])
    return shapely.STRtree(lines), {
        'path': str(path), 'sha256': sha256(raw).hexdigest(),
        'nodes': len(nodes), 'directed_edges': len(graph['edges']),
        'unique_geometric_segments': len(lines),
    }


def covered_pixels(classes, class_id, distance_m, tree, x, y):
    rows, columns = np.where(classes == class_id)
    covered = np.zeros(len(rows), dtype=bool)
    for start in range(0, len(rows), 150000):
        end = min(start + 150000, len(rows))
        points = shapely.points(x + (columns[start:end] + .5) * .1,
                                y + 250 - (rows[start:end] + .5) * .1)
        hits = tree.query(points, predicate='dwithin', distance=distance_m)
        covered[start + np.unique(hits[0])] = True
    gap_blocks = np.zeros((125, 125), dtype=bool)
    gap_blocks[rows[~covered] // 20, columns[~covered] // 20] = True
    total = len(rows)
    count = int(covered.sum())
    return {'pixels': total, 'covered_pixels': count, 'uncovered_pixels': total-count,
            'area_m2': round(total * .01, 2),
            'coverage': count / total if total else None}, gap_blocks


def audit_tile(x, y, car_tree, bike_tree):
    name = f'x{x}_y{y}'
    path = ROOT / 'scene/v1/tiles' / name / 'classes.png'
    if not path.exists():
        return name, {'bounds_rd': [x,y,x+250,y+250], 'status': 'missing_classes'}, None
    classes = np.asarray(Image.open(path))[:, :, 0]
    if classes.shape != (2500, 2500):
        raise ValueError(f'{path}: expected 2500x2500, got {classes.shape}')
    car, car_gaps = covered_pixels(classes, 1, 4, car_tree, x, y)
    bike, bike_gaps = covered_pixels(classes, 2, 3, bike_tree, x, y)
    # Background is the modal BGT class of each 2 m display pixel. Audit stays at 0.1 m.
    blocks = classes.reshape(125,20,125,20).transpose(0,2,1,3).reshape(15625,400)
    counts = np.stack([(blocks == value).sum(axis=1) for value in range(17)], axis=1)
    display = PALETTE[counts.argmax(axis=1)].reshape(125,125,3)
    display[car_gaps] = [255,35,35]
    display[bike_gaps] = [255,0,230]
    display[car_gaps & bike_gaps] = [255,92,210]
    return name, {'bounds_rd': [x,y,x+250,y+250], 'status':'audited',
                  'carriageway':car, 'cycle_path':bike}, display


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', default='after')
    parser.add_argument('--graphs', type=Path)
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    output = ROOT / 'scene/v1/networks'
    graph_dir = args.graphs or output
    if args.label == 'before' and args.graphs is None:
        graph_dir = output / 'before-osm'
        graph_dir.mkdir(exist_ok=True)
        for name in ('cars.json','bikes.json'):
            target = graph_dir / name
            if not target.exists():
                shutil.copy2(output / name, target)
    car_tree, car_source = load_graph(graph_dir/'cars.json')
    bike_tree, bike_source = load_graph(graph_dir/'bikes.json')
    tiles = [(x,y) for y in range(434750,438000,250) for x in range(89750,96500,250)]
    canvas = np.full((1625,3375,3), [220,170,20], dtype=np.uint8)
    records = {}
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(audit_tile,x,y,car_tree,bike_tree) for x,y in tiles]
        for future in as_completed(futures):
            name, record, image = future.result()
            records[name] = record
            if image is not None:
                x,y = record['bounds_rd'][:2]
                row,col=(438000-y-250)//2,(x-89750)//2
                canvas[row:row+125,col:col+125] = image
            if len(records)%25 == 0:
                print(f'{args.label}: {len(records)}/351 tiles, {time.monotonic()-started:.1f}s',flush=True)
    summary = {}
    for key,target in [('carriageway',.97),('cycle_path',.95)]:
        values = [record[key] for record in records.values() if record['status']=='audited']
        total = sum(value['pixels'] for value in values)
        count = sum(value['covered_pixels'] for value in values)
        summary[key] = {'pixels':total,'covered_pixels':count,'uncovered_pixels':total-count,
                        'coverage':count/total if total else None,'target':target,
                        'worst_ten_tiles':[{'tile':name,**record[key]} for name,record in sorted(
                            [(name,record) for name,record in records.items() if record.get(key,{}).get('coverage') is not None],
                            key=lambda item:(item[1][key]['coverage'],item[0]))[:10]],
                        'below_target_tiles':[name for name,record in sorted(records.items())
                            if record.get(key,{}).get('coverage') is not None and record[key]['coverage']<target]}
    missing = [name for name,record in records.items() if record['status']!='audited']
    report = {'written_by':'AI, GPT-6 Astra, 2026-10-26','label':args.label,'bounds_rd':BOUNDS,
              'method':{'input_resolution_m':.1,'sample':'every BGT class pixel centre',
                        'distance':'exact planar Euclidean distance to graph XY line segments, inclusive threshold',
                        'carriageway_class':1,'car_distance_m':4,'cycle_path_class':2,'bike_distance_m':3,
                        'z_used':False,'excluded_class_pixels':[],'display_resolution_m':2,
                        'gap_display':'2 m cell coloured if any underlying 0.1 m target pixel is uncovered'},
              'graphs':{'cars':car_source,'bikes':bike_source},'expected_tiles':351,
              'audited_tiles':len(records)-len(missing),'missing_classes_tiles':sorted(missing),
              'whole_area_complete':not missing,'summary':summary,'tiles':dict(sorted(records.items()))}
    suffix = '' if args.label == 'after' else f'-{args.label}'
    report_path=output/f'coverage{suffix}.json'
    report_path.write_text(json.dumps(report,indent=2)+'\n')
    render_dir=ROOT/'renders/debug-networks'
    render_dir.mkdir(parents=True,exist_ok=True)
    image=Image.new('RGB',(3375,1667),(20,20,20))
    image.paste(Image.fromarray(canvas),(0,42))
    draw=ImageDraw.Draw(image)
    draw.rectangle((0,0,1050,42),fill=(20,20,20))
    draw.text((8,6),f'{args.label}: red = uncovered carriageway (>4 m); magenta = uncovered cycle path (>3 m)',fill=(255,255,255))
    draw.text((8,23),'BGT classes background | 2 m per display pixel | audit uses all 0.1 m pixel centres | yellow = missing tile',fill=(230,230,230))
    image_path=render_dir/f'coverage{suffix}-2m.png'
    image.save(image_path)
    print(json.dumps({'report':str(report_path),'gap_map':str(image_path),'summary':summary,
                      'missing_tiles':missing,'seconds':time.monotonic()-started},indent=2),flush=True)


if __name__=='__main__':
    main()
