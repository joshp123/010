"""Build source-linked Rotterdam transit paths. Written by AI on 2026-10-26 by model GPT-6."""
import csv
import hashlib
import io
import json
from collections import defaultdict
from pathlib import Path
import zipfile

import numpy as np
from pyproj import Transformer
from shapely import line_merge, set_precision
from shapely.geometry import LineString, box
from shapely.ops import unary_union

ROOT = Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
REPO = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'sources/transit/2026-10-26'
OUTPUT = ROOT / 'scene/v1/networks'
BOUNDS = (87750, 432750, 98500, 440000)
ARCHIVE = Path('/Volumes/Josh Extreme Pro USB4 4TB/Projects/010/work/data-cache/transit/gtfs-nl.zip')
MODE = {0:'tram', 1:'metro', 2:'train', 4:'ferry'}


def parts(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == 'LineString':
        return [geometry] if geometry.length else []
    return [line for item in geometry.geoms for line in parts(item)]


def planar():
    SOURCE.mkdir(parents=True, exist_ok=True)
    bbox = box(*BOUNDS)
    project = Transformer.from_crs(4326, 28992, always_xy=True)
    inverse = Transformer.from_crs(28992,4326,always_xy=True)
    corners = [inverse.transform(x,y) for x in BOUNDS[::2] for y in BOUNDS[1::2]]
    minlon,maxlon=min(c[0] for c in corners)-.01,max(c[0] for c in corners)+.01
    minlat,maxlat=min(c[1] for c in corners)-.01,max(c[1] for c in corners)+.01
    selected = defaultdict(list)
    with zipfile.ZipFile(ARCHIVE) as archive:
        def rows(name):
            return csv.DictReader(io.TextIOWrapper(archive.open(name), encoding='utf-8-sig', newline=''))
        licenses = {row['licensed_table_name']:row['license_spdx_id'] for row in rows('licenses.txt')}
        assert licenses.get('shapes.txt') == 'ODbL-1.0'
        routes = {r['route_id']:(MODE[int(r['route_type'])], r['route_short_name']) for r in rows('routes.txt') if int(r['route_type']) in MODE}
        shape_lines = defaultdict(set)
        for trip in rows('trips.txt'):
            if trip['route_id'] in routes and trip.get('shape_id'):
                shape_lines[trip['shape_id']].add((*routes[trip['route_id']],trip.get('direction_id') or '0'))
        current, points = None, []
        used_shapes = {}
        def retain(identifier, points):
            if identifier not in shape_lines or len(points)<2:
                return
            points.sort()
            ll = np.array([[p[1],p[2]] for p in points])
            if ll[:,0].max()<minlon or ll[:,0].min()>maxlon or ll[:,1].max()<minlat or ll[:,1].min()>maxlat:
                return
            xs,ys=project.transform(ll[:,0],ll[:,1])
            original=set_precision(LineString(zip(xs,ys)),.01)
            if not original.intersects(bbox):return
            # Match before final clipping: a coarse GTFS chord can cross the
            # output boundary far from the true curved railway.
            geometry=original.intersection(bbox.buffer(2000))
            lines=parts(geometry)
            if not lines:
                return
            used_shapes[identifier]=[list(key) for key in sorted(shape_lines[identifier])]
            for key in shape_lines[identifier]:
                selected[key].extend(lines)
        for row in rows('shapes.txt'):
            identifier=row['shape_id']
            if current is not None and identifier!=current:
                retain(current,points); points=[]
            current=identifier
            if identifier in shape_lines:
                points.append((int(row['shape_pt_sequence']),float(row['shape_pt_lon']),float(row['shape_pt_lat'])))
        if current is not None:
            retain(current,points)
    output=[]
    groups=[]
    for (mode,line,direction),geometries in sorted(selected.items()):
        unique={g.wkb:g for g in geometries}
        merged=line_merge(unary_union(list(unique.values())),directed=True)
        paths=[list(g.simplify(.5,preserve_topology=False).coords) for g in parts(merged) if g.length>.05]
        output.append({'mode':mode,'line':line,'direction':direction,'paths':paths})
        groups.append({'mode':mode,'line':line,'direction':direction,'inputShapes':len(geometries),'uniqueShapes':len(unique),'paths':len(paths),'inputMetres':sum(g.length for g in geometries),'deduplicatedMetres':sum(LineString(p).length for p in paths)})
    (SOURCE/'planar.json').write_text(json.dumps(output,separators=(',',':'))+'\n')
    (SOURCE/'shape-links.json').write_text(json.dumps(used_shapes,separators=(',',':'))+'\n')
    (SOURCE/'planar-report.json').write_text(json.dumps({'writtenBy':'AI, GPT-6, 2026-10-26','archive':str(ARCHIVE),'sha256':hashlib.file_digest(ARCHIVE.open('rb'),'sha256').hexdigest(),'boundsRd':BOUNDS,'groups':groups},indent=2)+'\n')
    print(json.dumps({'groups':len(output),'paths':sum(len(g['paths']) for g in output),'vertices':sum(len(p) for g in output for p in g['paths']),'modes':{m:sorted({g['line'] for g in output if g['mode']==m}) for m in MODE.values()}},indent=2),flush=True)
    return output


if __name__=='__main__':
    planar()
