#!/usr/bin/env python3
"""Evidence for unresolved BGT/network gaps. Written by AI, GPT-6 Astra, 2026-10-26."""
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from hashlib import sha256
import gzip
import json
from pathlib import Path
import time

import numpy as np
from PIL import Image
import shapely
from build_osm import access_value, eligible, SOURCE
from coverage import ROOT, load_graph

OUTPUT = ROOT / 'scene/v1/networks'
EVIDENCE_RADIUS = 8.0
DESCRIPTIONS = {
    'explicit_source_exclusion_nearby': 'A nearer OSM way has explicit mode access restrictions or construction tags within 8 m. Its tags are evidence; they do not prove that every affected BGT pixel belongs to that way.',
    'mode_excluded_source_nearby': 'A nearer OSM way within 8 m is excluded by the graph mode selection (for example a footway or cycleway for cars). This is a source classification conflict, not verified legal or physical access.',
    'width_or_alignment_unresolved': 'Uncovered pixels are 4–12 m from car graph geometry or 3–8 m from bike graph geometry. Wide surfaces, centreline alignment or missing parallel ways are possible; cause is unresolved.',
    'eligible_source_geometry_not_represented_nearby': 'Eligible original OSM geometry is within 8 m while delivered graph geometry is farther away. This requires source/build investigation; no cause is asserted.',
    'no_nearby_eligible_network_unresolved': 'No nearby eligible graph/source geometry within the stated diagnostic distances. This is an unresolved source gap, not evidence of construction or private access.',
}


def explicit_exclusion(tags, mode):
    permission = access_value(tags, mode)
    if permission in {'no','private','agricultural','forestry','emergency','dismount','use_sidepath'}:
        return True
    return tags.get('highway') in {'construction','proposed'} or tags.get('construction') not in {None,'no'}


def source_index(source, mode, selected):
    records = []
    geometries = []
    for way in source['ways']:
        if 'highway' not in way['tags'] or eligible(way['tags'],mode) != selected:
            continue
        coordinates = [source['nodes'][str(ref)] for ref in way['refs']]
        if len(coordinates)<2:
            continue
        records.append(way)
        geometries.append(shapely.LineString(coordinates))
    return shapely.STRtree(geometries), records


def nearest(tree, points):
    distances = np.full(len(points),np.inf)
    indices = np.full(len(points),-1,dtype=np.int64)
    if len(tree):
        matches, values = tree.query_nearest(points, return_distance=True, all_matches=False)
        distances[matches[0]] = values
        indices[matches[0]] = matches[1]
    return indices, distances


def tile_reason(name, mode, audited, graph_tree, selected_tree, selected_records,
                excluded_tree, excluded_records):
    x,y = audited['bounds_rd'][:2]
    class_id, threshold, nearby = (1,4.,12.) if mode=='cars' else (2,3.,8.)
    field = 'carriageway' if mode=='cars' else 'cycle_path'
    classes = np.asarray(Image.open(ROOT/'scene/v1/tiles'/name/'classes.png'))[:,:,0]
    rows,columns=np.where(classes==class_id)
    category_counts=Counter()
    evidence_counts=defaultdict(Counter)
    evidence_distances=defaultdict(lambda:[np.inf,0.])
    for start in range(0,len(rows),100000):
        end=min(len(rows),start+100000)
        points=shapely.points(x+(columns[start:end]+.5)*.1,y+250-(rows[start:end]+.5)*.1)
        hits=graph_tree.query(points,predicate='dwithin',distance=threshold)
        uncovered=np.ones(len(points),dtype=bool)
        uncovered[np.unique(hits[0])]=False
        points=points[uncovered]
        if not len(points):continue
        _,graph_distance=nearest(graph_tree,points)
        selected_indices,selected_distance=nearest(selected_tree,points)
        excluded_indices,excluded_distance=nearest(excluded_tree,points)
        # These distances diagnose failures only; the immutable coverage thresholds stay 4 m / 3 m.
        categories=np.full(len(points),'no_nearby_eligible_network_unresolved',dtype=object)
        ids=np.full(len(points),-1,dtype=np.int64)
        evidence_kind=np.full(len(points),'none',dtype=object)
        chosen_distance=np.full(len(points),np.inf)
        original_near=selected_distance<=EVIDENCE_RADIUS
        categories[original_near]='eligible_source_geometry_not_represented_nearby'
        ids[original_near]=selected_indices[original_near]
        evidence_kind[original_near]='selected'
        chosen_distance[original_near]=selected_distance[original_near]
        near_graph=graph_distance<=nearby
        categories[near_graph]='width_or_alignment_unresolved'
        ids[near_graph]=selected_indices[near_graph]
        evidence_kind[near_graph]='selected'
        chosen_distance[near_graph]=selected_distance[near_graph]
        nearer_excluded=(excluded_distance<=EVIDENCE_RADIUS)&(excluded_distance<selected_distance)&(excluded_distance<graph_distance)
        for index in np.flatnonzero(nearer_excluded):
            way=excluded_records[excluded_indices[index]]
            categories[index]='explicit_source_exclusion_nearby' if explicit_exclusion(way['tags'],mode) else 'mode_excluded_source_nearby'
            ids[index]=excluded_indices[index]
            evidence_kind[index]='excluded'
            chosen_distance[index]=excluded_distance[index]
        for category in np.unique(categories):
            mask=categories==category
            category_counts[category]+=int(mask.sum())
            for kind in ['selected','excluded']:
                chosen=mask&(evidence_kind==kind)
                if not chosen.any():continue
                records=selected_records if kind=='selected' else excluded_records
                unique_indices,counts=np.unique(ids[chosen],return_counts=True)
                for source_index_value,count in zip(unique_indices,counts):
                    way=records[source_index_value]
                    key=(category,str(way['id']))
                    evidence_counts[category][str(way['id'])]+=int(count)
                    these=chosen&(ids==source_index_value)
                    values=chosen_distance[these]
                    evidence_distances[key][0]=min(evidence_distances[key][0],float(values.min()))
                    evidence_distances[key][1]=max(evidence_distances[key][1],float(values.max()))
    expected=audited[field]['uncovered_pixels']
    if sum(category_counts.values())!=expected:
        raise RuntimeError(f'{name}/{mode}: gap pixel count differs from immutable coverage report')
    categories={}
    evidence_ids=set()
    for category,count in sorted(category_counts.items()):
        evidence=[]
        for way_id,way_count in evidence_counts[category].most_common():
            evidence_ids.add(way_id)
            distances=evidence_distances[(category,way_id)]
            evidence.append({'osm_way_id':int(way_id),'pixels':way_count,
                             'distance_range_m':[round(value,3) for value in distances]})
        categories[category]={'pixels':count,'area_m2':round(count*.01,2),'source_evidence':evidence}
    return name,mode,{'coverage':audited[field]['coverage'],'class_pixels':audited[field]['pixels'],
                      'uncovered_pixels':expected,'categories':categories},evidence_ids


def main():
    audit_path=OUTPUT/'coverage.json'
    audit=json.loads(audit_path.read_text())
    if not audit['whole_area_complete']:raise RuntimeError('Coverage audit lacks class tiles')
    source=json.loads(gzip.decompress(SOURCE.read_bytes()))
    jobs=[]
    started=time.monotonic()
    result={}
    evidence_ids=set()
    for mode,field in [('cars','carriageway'),('bikes','cycle_path')]:
        path=OUTPUT/f'{mode}.json'
        if sha256(path.read_bytes()).hexdigest()!=audit['graphs'][mode]['sha256']:
            raise RuntimeError('Graph changed since coverage.json; rerun coverage.py first')
        graph_tree,_=load_graph(path)
        selected_tree,selected_records=source_index(source,mode,True)
        excluded_tree,excluded_records=source_index(source,mode,False)
        below=audit['summary'][field]['below_target_tiles']
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures=[pool.submit(tile_reason,name,mode,audit['tiles'][name],graph_tree,
                        selected_tree,selected_records,excluded_tree,excluded_records) for name in below]
            for done,future in enumerate(as_completed(futures),1):
                name,_,record,ids=future.result()
                result.setdefault(name,{})[mode]=record
                evidence_ids.update(ids)
                if done%25==0:print(f'{mode}: {done}/{len(below)}, {time.monotonic()-started:.1f}s',flush=True)
    summaries={}
    for mode in ['cars','bikes']:
        counts=Counter()
        for record in result.values():
            for category,details in record.get(mode,{}).get('categories',{}).items():counts[category]+=details['pixels']
        summaries[mode]=dict(counts)
    report={'written_by':'AI, GPT-6 Astra, 2026-10-26','coverage_sha256':sha256(audit_path.read_bytes()).hexdigest(),
            'source':str(SOURCE),'source_sha256':sha256(SOURCE.read_bytes()).hexdigest(),
            'license':'ODbL-1.0','attribution':'© OpenStreetMap contributors / Geofabrik',
            'method':{'scope':'Every below-target tile and every uncovered 0.1 m class pixel centre in those tiles',
                       'diagnostic_near_graph_m':{'cars':12,'bikes':8},'source_evidence_radius_m':8,
                       'nearest_way_ties':'one nearest source feature; ties do not assert ownership',
                       'causality':'Proximity and tags are evidence, not proof of the physical cause. No inferred private land or construction.',
                       'coverage_thresholds_unchanged':{'cars':4,'bikes':3}},
            'category_descriptions':DESCRIPTIONS,'below_target_tile_category_pixels':summaries,
            'tiles':dict(sorted(result.items())),
            'source_ways':{str(way['id']):{'osm_id':way['id'],'tags':way['tags']} for way in source['ways'] if str(way['id']) in evidence_ids}}
    output=OUTPUT/'coverage-reasons.json'
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'path':str(output),'tiles':len(result),'seconds':time.monotonic()-started,
                      'categories':summaries},indent=2),flush=True)


if __name__=='__main__':main()
