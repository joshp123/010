"""Spatial OSM/NWB cross-check. Written by AI on 2026-10-26 by GPT-6 Astra.

The check measures source geometry, never network completeness. Sample intervals
are at most 5 m, with their exact lengths as weights. A match needs a line within
10 m whose local undirected tangent differs by at most 25 degrees.
"""
import gzip
import hashlib
import importlib.util
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

from shapely.geometry import LineString, Point, box, shape
from shapely.strtree import STRtree

ROOT = Path('/Volumes/Josh Extreme Pro USB4 4TB/010')
BOUNDS = (89750,434750,96500,438000)
AREA = box(*BOUNDS)
DISTANCE = 10.0
STEP = 5.0
ANGLE = 25.0
DROPPED_CODES = {'VP','VZ','FP','BUS','BU','OVB','TR','TRAM','RP','VDA','VDF','VDV','CADO'}
CAR_CLASSES = {'motorway','motorway_link','trunk','trunk_link','primary','primary_link',
               'secondary','secondary_link','tertiary','tertiary_link','unclassified',
               'residential','living_street','service','track','road'}


def fallback_eligible(tags, mode):
    """Used only if the final builder's own eligibility function is not present."""
    highway = tags.get('highway')
    if tags.get('area') == 'yes':
        return False
    if mode == 'cars':
        access = tags.get('motorcar',tags.get('motor_vehicle',tags.get('vehicle',tags.get('access','yes'))))
        return highway in CAR_CLASSES and access not in {'no','private','agricultural','forestry'}
    access = tags.get('bicycle',tags.get('vehicle',tags.get('access','yes')))
    return (highway in CAR_CLASSES | {'cycleway','path','footway','pedestrian','bridleway'}
            and highway not in {'motorway','motorway_link','trunk','trunk_link'}
            and tags.get('motorroad') != 'yes'
            and access not in {'no','private','use_sidepath'}
            and (highway not in {'footway','pedestrian'} or tags.get('bicycle') in {'yes','designated','permissive'}))


def eligibility_function():
    for name in ('build_osm','osm_build'):
        path = Path(__file__).with_name(name + '.py')
        if path.exists():
            spec = importlib.util.spec_from_file_location(name,path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module,'eligible'):
                return module.eligible, str(path)
    return fallback_eligible, 'compare_sources.py fallback, recorded explicitly'


def line_parts(geometry):
    if geometry.geom_type == 'LineString':
        if geometry.length > .01:
            yield geometry
    elif hasattr(geometry,'geoms'):
        for part in geometry.geoms:
            yield from line_parts(part)


def load_sources(eligible):
    with gzip.open(ROOT/'sources/network-osm/2026-10-26/m1-buffer.json.gz','rt') as stream:
        source = json.load(stream)
    osm=[]
    for way in source['ways']:
        if 'highway' not in way['tags']:
            continue
        coordinates=[source['nodes'][str(ref)] for ref in way['refs']]
        if len(coordinates)<2:
            continue
        tags=way['tags']
        for line in line_parts(LineString(coordinates).intersection(AREA)):
            osm.append({'id':way['id'],'name':tags.get('name',''),'line':line,'class':tags['highway'],
                        'cars':eligible(tags,'cars'),'bikes':eligible(tags,'bikes')})
    nwb=[]
    for page in sorted((ROOT/'sources/nwb-networks/2026-10-26').glob('page-*.json')):
        for feature in json.loads(page.read_text())['features']:
            tags=feature['properties'];code=tags.get('bst_code','')
            car=code not in DROPPED_CODES
            # NWB road classes cannot establish all road-specific bicycle access.
            # This is a candidate-source comparison, not an access assertion.
            bike=code=='FP' or (car and tags.get('wegbehsrt')!='R')
            for line in line_parts(shape(feature['geometry']).intersection(AREA)):
                nwb.append({'id':tags['wvk_id'],'name':tags.get('stt_naam') or '', 'line':line,
                            'class':code,'cars':car,'bikes':bike})
    return osm,nwb


def tangent(line,distance):
    a=line.interpolate(max(0,distance-2.5));b=line.interpolate(min(line.length,distance+2.5))
    dx=b.x-a.x;dy=b.y-a.y;norm=math.hypot(dx,dy)
    return (dx/norm,dy/norm) if norm else (0.,0.)


def compare(records, references):
    lines=[record['line'] for record in references]
    tree=STRtree(lines)
    cosine=math.cos(math.radians(ANGLE))
    streets=defaultdict(lambda:{'length_m':0.,'unmatched_m':0.,'source_ids':set(),'unmatched_source_ids':set(),'classes':set()})
    total=missing=0.
    for record in records:
        line=record['line'];length=line.length
        street=streets[record['name']]
        street['length_m']+=length;street['source_ids'].add(record['id']);street['classes'].add(record['class'])
        intervals=max(1,math.ceil(length/STEP));weight=length/intervals
        unmatched=0.
        for index in range(intervals):
            distance=length*(index+.5)/intervals
            point=line.interpolate(distance);direction=tangent(line,distance)
            matched=False
            for candidate_index in tree.query(point.buffer(DISTANCE)):
                candidate=lines[candidate_index]
                if candidate.distance(point)>DISTANCE:
                    continue
                candidate_direction=tangent(candidate,candidate.project(point))
                if abs(direction[0]*candidate_direction[0]+direction[1]*candidate_direction[1])>=cosine:
                    matched=True
                    break
            if not matched:
                unmatched+=weight
        street['unmatched_m']+=unmatched
        if unmatched:
            street['unmatched_source_ids'].add(record['id'])
        total+=length;missing+=unmatched
    result=[]
    for name,street in streets.items():
        result.append({'street':name or '(unnamed)',
            'length_m':round(street['length_m'],1),'unmatched_m':round(street['unmatched_m'],1),
            'unmatched_share':round(street['unmatched_m']/street['length_m'],6),
            'source_ids':sorted(street['source_ids']),
            'unmatched_source_ids':sorted(street['unmatched_source_ids']),
            'classes':sorted(street['classes'])})
    result.sort(key=lambda record:record['unmatched_m'],reverse=True)
    return {'source_line_length_m':round(total,1),'unmatched_length_m':round(missing,1),
            'unmatched_length_share':missing/total if total else None,
            'streets':result,'worst_ten_named_streets':[r for r in result if r['street']!='(unnamed)'][:10]}


def graph_records(mode):
    path=ROOT/'scene/v1/networks'/f'{mode}.json'
    graph=json.loads(path.read_text())
    if graph.get('version')!=2:
        raise ValueError(f'{mode}: expected rebuilt OSM version 2 graph')
    records=[];seen=set()
    for index,edge in enumerate(graph['edges']):
        key=tuple(sorted(edge[:2]))
        if key in seen:
            continue
        seen.add(key)
        way=graph['ways'][graph['edge_ways'][index]]
        records.append({'id':way['osm_id'],'name':way.get('name',''), 'class':way['class'],
                        'line':LineString([graph['nodes'][edge[0]][:2],graph['nodes'][edge[1]][:2]])})
    return records


def main():
    eligible,eligibility_source=eligibility_function()
    osm,nwb=load_sources(eligible)
    output=ROOT/'scene/v1/networks/osm-nwb-comparison.json'
    if '--graphs-only' in sys.argv:
        report=json.loads(output.read_text())
        report['final_graph_comparisons']={}
        for mode in ['cars','bikes']:
            graph=graph_records(mode);nwb_mode=[r for r in nwb if r[mode]]
            report['final_graph_comparisons'][mode]={
                'graph_sha256':hashlib.sha256((ROOT/'scene/v1/networks'/f'{mode}.json').read_bytes()).hexdigest(),
                'nwb_not_spatially_matched_by_graph':compare(nwb_mode,graph),
                'graph_not_spatially_matched_by_nwb':compare(graph,nwb_mode)}
        output.write_text(json.dumps(report,indent=2)+'\n')
        print(output,flush=True)
        return
    report={'bounds_rd':BOUNDS,'method':{'sample_interval_max_m':STEP,
        'distance_threshold_m':DISTANCE,'undirected_tangent_max_angle_degrees':ANGLE,
        'weight':'actual sample interval length; line geometry clipped to M1; no graph pruning',
        'osm_eligibility_source':eligibility_source,
        'nwb_car_dropped_codes':sorted(DROPPED_CODES),
        'nwb_bike_candidates':'FP plus car-code carriageways except road manager R; specific access unknown',
        'limitations':['Parallel lines within 10 m may match despite being separate carriageways or paths.',
                      'Source offsets greater than 10 m count as unmatched.',
                      'No direction, turning, height or accessibility validation is implied.',
                      'All-highways comparison includes footways and other non-driving ways.']},'comparisons':{}}
    for mode in ['all','cars','bikes','cycle_paths']:
        osm_mode=osm if mode=='all' else [r for r in osm if r['class']=='cycleway'] if mode=='cycle_paths' else [r for r in osm if r[mode]]
        nwb_mode=nwb if mode=='all' else [r for r in nwb if r['class']=='FP'] if mode=='cycle_paths' else [r for r in nwb if r[mode]]
        print(mode,len(osm_mode),len(nwb_mode),flush=True)
        osm_names={r['name'].casefold():r['name'] for r in osm_mode if r['name']}
        nwb_names={r['name'].casefold():r['name'] for r in nwb_mode if r['name']}
        report['comparisons'][mode]={
            'nwb_not_spatially_matched_by_osm':compare(nwb_mode,osm_mode),
            'osm_not_spatially_matched_by_nwb':compare(osm_mode,nwb_mode),
            'name_only_differences':{'nwb_names_absent_osm':sorted(nwb_names[k] for k in nwb_names.keys()-osm_names.keys()),
                                     'osm_names_absent_nwb':sorted(osm_names[k] for k in osm_names.keys()-nwb_names.keys()),
                                     'warning':'Names are casefolded only; aliases and naming scope differ. Not coverage proof.'}}
    output=ROOT/'scene/v1/networks/osm-nwb-comparison.json'
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(output,flush=True)


if __name__=='__main__':
    main()
