"""OSM M1 networks. Written by AI on 2026-10-26 by model GPT-6 Astra.

Preserve source topology and all valid components. No coverage-driven geometry.
"""
import gzip
import hashlib
import json
import math
import re
from collections import Counter, defaultdict, deque
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from shapely.geometry import LineString, Point, box
from shapely.ops import substring
from heights import HeightSampler
from acquire import ROOT

BOUNDS=(89750,434750,96500,438000)
AREA=box(*BOUNDS)
OUTPUT=ROOT/'scene/v1/networks'
SOURCE=ROOT/'sources/network-osm/2026-10-26/m1-buffer.json.gz'
MOTOR_CLASSES={'motorway','motorway_link','trunk','trunk_link','primary','primary_link','secondary','secondary_link','tertiary','tertiary_link','unclassified','residential','living_street','service','road','track'}
DENIED={'no','private','agricultural','forestry','emergency'}
ALLOWED={'yes','designated','official','permissive','destination','customers','delivery'}


def access_value(tags,mode):
    keys=['motorcar','motor_vehicle','vehicle','access'] if mode=='cars' else ['bicycle','vehicle','access']
    return next((tags[key] for key in keys if key in tags),None)


def eligible(tags,mode):
    highway=tags.get('highway','')
    if tags.get('area')=='yes' or highway in {'construction','proposed','services','platform','elevator'}:return False
    permission=access_value(tags,mode)
    if permission in DENIED or permission in {'dismount','use_sidepath'}:return False
    if mode=='cars':
        return highway in MOTOR_CLASSES or (permission in ALLOWED and any(key in tags for key in ['motorcar','motor_vehicle']) and highway in {'pedestrian','footway','path','cycleway'})
    if tags.get('motorroad')=='yes' or highway in {'motorway','motorway_link','trunk','trunk_link'}:return False
    if highway in {'cycleway','path','track','living_street'} or highway in MOTOR_CLASSES:return True
    return highway in {'pedestrian','footway','bridleway'} and permission in ALLOWED and tags.get('bicycle') in ALLOWED


def directions(tags,mode):
    value=tags.get('oneway')
    if value is None and (tags.get('junction') in {'roundabout','circular'} or tags.get('highway')=='motorway'):value='yes'
    if mode=='bikes':
        override=tags.get('oneway:bicycle')
        if override is not None:value=override
        elif any(tags.get(key,'').startswith('opposite') for key in ['cycleway','cycleway:left','cycleway:right','cycleway:both']):value='no'
    result=[value not in {'-1','reverse'},value not in {'yes','true','1'}]
    if mode=='bikes':
        if tags.get('bicycle:forward')=='no':result[0]=False
        if tags.get('bicycle:backward')=='no':result[1]=False
    else:
        for index,direction in enumerate(['forward','backward']):
            if tags.get(f'motor_vehicle:{direction}')=='no' or tags.get(f'motorcar:{direction}')=='no':result[index]=False
    return result


def maxspeed(tags,forward):
    raw=tags.get('maxspeed:forward' if forward else 'maxspeed:backward',tags.get('maxspeed'))
    codes={'NL:urban':50,'NL:rural':80,'NL:living_street':15,'NL:motorway':130,'NL:motorway:day':100,'NL:trunk':100}
    if raw in codes:return codes[raw],'osm_code'
    if raw:
        values=re.findall(r'\d+(?:\.\d+)?',raw)
        if values:
            value=min(map(float,values))
            if 'mph' in raw:value*=1.609344
            return round(value,1),'osm_maxspeed'
        if raw=='none':return None,'osm_unlimited'
    highway=tags.get('highway','')
    if highway in {'cycleway','footway','path','steps','pedestrian','bridleway'}:return None,'no_general_bicycle_speed_limit'
    if highway=='living_street':return 15,'NL_living_street_default'
    if highway.startswith('motorway'):return 100,'NL_motorway_daytime_default'
    if tags.get('motorroad')=='yes':return 100,'NL_motorroad_default'
    # Entire M1 is central Rotterdam, inside the built-up area. Road rank is not a legal speed limit.
    return 50,'NL_built_up_area_default'


def densify(line):
    coordinates=list(line.simplify(.5).coords);result=[coordinates[0]]
    for a,b in zip(coordinates,coordinates[1:]):
        distance=math.dist(a,b)
        for step in range(1,math.ceil(distance/10)+1):
            t=min(step*10/distance,1)
            result.append((a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t))
    return result


def arcs(way,coordinates,anchors):
    start=0
    for index in range(1,len(way['refs'])):
        if index==len(way['refs'])-1 or way['refs'][index] in anchors:
            points=coordinates[start:index+1]
            if len(points)>=2 and LineString(points).length>.01:
                yield way['refs'][start],way['refs'][index],LineString(points)
            start=index


def blocked_node(tags,mode):
    permission=access_value(tags,mode)
    if permission in DENIED:return True
    if mode=='cars' and tags.get('barrier') in {'bollard','block','cycle_barrier','bus_trap','stile','turnstile'}:
        return permission not in ALLOWED
    return False


def graph_statistics(nodes,edges):
    if not edges:return {}
    matrix=coo_matrix((np.ones(len(edges)),([e[0] for e in edges],[e[1] for e in edges])),shape=(len(nodes),len(nodes))).tocsr()
    weak,labels=connected_components(matrix,directed=True,connection='weak')
    strong,strong_labels=connected_components(matrix,directed=True,connection='strong')
    return {'weak_components':int(weak),'strong_components':int(strong),
            'largest_weak_node_share':max(Counter(labels).values())/len(nodes),
            'largest_strong_node_share':max(Counter(strong_labels).values())/len(nodes),
            'components_dropped':0}


def restrictions(source,mode,ways,edges,edge_ways,node_osm):
    by_source=defaultdict(list)
    incoming=defaultdict(list);outgoing=defaultdict(list)
    for index,edge in enumerate(edges):
        by_source[ways[edge_ways[index]]['osm_id']].append(index)
        incoming[edge[1]].append(index);outgoing[edge[0]].append(index)
    result=[];unsupported=[]
    for relation in source['restrictions']:
        tags=relation['tags'];exceptions=set(tags.get('except','').split(';'))
        if (mode=='bikes' and 'bicycle' in exceptions) or (mode=='cars' and exceptions&{'motorcar','motor_vehicle','vehicle'}):continue
        keys=['restriction:motorcar','restriction:motor_vehicle','restriction'] if mode=='cars' else ['restriction:bicycle','restriction']
        rule=next((tags[key] for key in keys if key in tags),None)
        if rule is None:continue
        from_ids=[m['ref'] for m in relation['members'] if m['role']=='from' and m['type']=='way']
        to_ids=[m['ref'] for m in relation['members'] if m['role']=='to' and m['type']=='way']
        via_nodes=[m['ref'] for m in relation['members'] if m['role']=='via' and m['type']=='node']
        via_ways=[m['ref'] for m in relation['members'] if m['role']=='via' and m['type']=='way']
        if not any(by_source[x] for x in from_ids) or not any(by_source[x] for x in to_ids):continue
        record={'osm_id':relation['id'],'restriction':rule,'kind':'only' if rule.startswith('only_') else 'no',
                'from_way_ids':from_ids,'via_way_ids':via_ways,'to_way_ids':to_ids,'tags':tags}
        if via_nodes:
            transitions=[]
            for node_index,osm_id in enumerate(node_osm):
                if osm_id not in via_nodes:continue
                ins=[i for i in incoming[node_index] if ways[edge_ways[i]]['osm_id'] in from_ids]
                outs=[i for i in outgoing[node_index] if ways[edge_ways[i]]['osm_id'] in to_ids]
                if ins and outs:transitions.append({'via_node':node_index,'from_edges':ins,'to_edges':outs})
            if transitions:record['transitions']=transitions;result.append(record)
            else:unsupported.append({**record,'reason':'No retained directed transition at source via-node'})
        elif via_ways:
            # Via-way relation is a stateful sequence constraint. Keep explicit directed edge sets in source order.
            groups=[by_source[x] for x in [*from_ids,*via_ways,*to_ids]]
            if all(groups):
                record['edge_way_sequence']=groups;record['semantics']='Apply kind when traversing from -> ordered via ways -> to; retain state across degree-two nodes.'
                result.append(record)
            else:unsupported.append({**record,'reason':'A via way is not present in this mode/area'})
        else:unsupported.append({**record,'reason':'Unsupported restriction member form'})
    return result,unsupported



def keep_largest_component(nodes,edges,edge_ways,node_osm,node_heights,ways):
    matrix=coo_matrix((np.ones(len(edges)),([e[0] for e in edges],[e[1] for e in edges])),shape=(len(nodes),len(nodes))).tocsr()
    count,labels=connected_components(matrix,directed=True,connection='weak')
    largest=max(Counter(labels),key=Counter(labels).get)
    retained=[i for i,e in enumerate(edges) if labels[e[0]]==largest]
    used_nodes=sorted({v for i in retained for v in edges[i][:2]})
    used_ways=sorted({edge_ways[i] for i in retained})
    node_map={old:new for new,old in enumerate(used_nodes)}
    way_map={old:new for new,old in enumerate(used_ways)}
    info={'input_weak_components':int(count),'largest_component_node_share':len(used_nodes)/len(nodes),
          'largest_component_edge_share':len(retained)/len(edges),'discarded_edges':len(edges)-len(retained),
          'retained_weak_components':1,'components_dropped':int(count)-1}
    return ([nodes[i] for i in used_nodes],[[node_map[e[0]],node_map[e[1]],*e[2:]] for i in retained for e in [edges[i]]],
            [way_map[edge_ways[i]] for i in retained],[node_osm[i] for i in used_nodes],
            [node_heights[i] for i in used_nodes],[ways[i] for i in used_ways],info)


def build(source,mode):
    sampler=HeightSampler();nodes=[];node_osm=[];node_heights=[];edges=[];edge_ways=[];ways=[];node_lookup={};stats=Counter()
    selected=[way for way in source['ways'] if eligible(way['tags'],mode)]
    counts=Counter(ref for way in selected for ref in set(way['refs']))
    anchors={ref for ref,count in counts.items() if count>1}
    anchors.update(int(ref) for ref,tags in source.get('node_tags',{}).items() if tags)
    anchors.update(m['ref'] for r in source['restrictions'] for m in r['members'] if m['role']=='via' and m['type']=='node')
    def insert(coordinate,key,z,height_source,osm_id=None):
        if key is not None and key in node_lookup:return node_lookup[key]
        index=len(nodes);nodes.append([round(coordinate[0],1),round(coordinate[1],1),round(z,1)]);node_osm.append(osm_id);node_heights.append(height_source)
        if key is not None:node_lookup[key]=index
        return index
    for way in selected:
        tags=way['tags'];coordinates=[source['nodes'][str(ref)] for ref in way['refs']]
        if not LineString(coordinates).intersects(AREA):continue
        allowed=directions(tags,mode)
        if not any(allowed):continue
        tunnel=tags.get('tunnel') not in (None,'no','false','0')
        bridge=tags.get('bridge') not in (None,'no','false','0')
        this_way=len(ways)
        ways.append({'osm_id':way['id'],'name':tags.get('name',''),'class':tags['highway'],
                     'oneway':sum(allowed)==1,'directions':allowed,'tunnel':tunnel,'bridge':bridge,'tags':tags})
        for arc_index,(start_ref,end_ref,arc) in enumerate(arcs(way,coordinates,anchors)):
            clipped=arc.intersection(AREA)
            parts=list(clipped.geoms) if hasattr(clipped,'geoms') else [clipped]
            for part_index,part in enumerate(parts):
                if part.geom_type!='LineString' or part.length<.1:continue
                points=densify(part)
                sampled=[(-12.,'assumed_tunnel_-12m') if tunnel else sampler.sample(*point,bridge=bridge) for point in points]
                valid=[i for i,(z,_) in enumerate(sampled) if z is not None]
                if not valid:
                    source_line=LineString(coordinates)
                    source_samples=[(source_line.project(Point(point)),sampler.sample(*point,bridge=bridge)[0]) for point in coordinates if AREA.covers(Point(point))]
                    source_samples=[pair for pair in source_samples if pair[1] is not None]
                    source_samples.sort()
                    if source_samples:
                        sampled=[(float(np.interp(source_line.project(Point(point)),[pair[0] for pair in source_samples],[pair[1] for pair in source_samples])),'same_source_way_interpolation') for point in points]
                        valid=list(range(len(points)))
                        stats['same_source_way_height_interpolation_arcs']+=1
                    else:
                        stats['all_height_nodata_arcs']+=1
                        continue
                distance=np.concatenate(([0],np.cumsum([math.dist(a,b) for a,b in zip(points,points[1:])])))
                for index,(z,_) in enumerate(sampled):
                    if z is None:
                        sampled[index]=(float(np.interp(distance[index],distance[valid],[sampled[i][0] for i in valid])),'same_source_arc_interpolation')
                        stats['interpolated_height_nodes']+=1
                endpoints=[start_ref if Point(points[0]).distance(Point(arc.coords[0]))<.01 else None,
                           end_ref if Point(points[-1]).distance(Point(arc.coords[-1]))<.01 else None]
                indices=[]
                for index,(point,(z,height_source)) in enumerate(zip(points,sampled)):
                    ref=endpoints[0] if index==0 else endpoints[1] if index==len(points)-1 else None
                    key=('osm',ref) if ref is not None else None
                    if ref is not None and blocked_node(source.get('node_tags',{}).get(str(ref),{}),mode):
                        key=('barrier_end',ref,way['id'],arc_index,index)
                        stats['barrier_terminal_nodes']+=1
                    indices.append(insert(point,key,z,height_source,ref))
                for a,b in zip(indices,indices[1:]):
                    if a==b:continue
                    for forward,start,end,permitted in [(True,a,b,allowed[0]),(False,b,a,allowed[1])]:
                        if not permitted:continue
                        limit,speed_source=maxspeed(tags,forward)
                        raw_lanes=tags.get('lanes:forward' if forward else 'lanes:backward',tags.get('lanes','1'))
                        lanes=max(1,int(float(raw_lanes))) if re.fullmatch(r'\d+(?:\.\d+)?',raw_lanes) else 1
                        if sum(allowed)==2 and 'lanes:forward' not in tags and 'lanes:backward' not in tags:lanes=max(1,lanes//2)
                        speed=min(limit or 18,18) if mode=='bikes' else min(limit or 50,50)
                        edges.append([start,end,speed,lanes,tags['highway'],limit]);edge_ways.append(this_way)
                        stats['maxspeed_'+speed_source]+=1
    nodes,edges,edge_ways,node_osm,node_heights,ways,component_selection=keep_largest_component(nodes,edges,edge_ways,node_osm,node_heights,ways)
    turn_rules,unresolved=restrictions(source,mode,ways,edges,edge_ways,node_osm)
    result={'version':2,'crs':'EPSG:28992+5709','bounds_rd':BOUNDS,
            'edge_fields':['from','to','speed_kmh','lanes','class','maxspeed'],
            'nodes':nodes,'node_osm_ids':node_osm,'edges':edges,'ways':ways,'edge_ways':edge_ways,
            'tunnel_edges':[i for i,w in enumerate(edge_ways) if ways[w]['tunnel']],
            'turn_restrictions':turn_rules,'unresolved_restrictions':unresolved,
            'connectivity':{**graph_statistics(nodes,edges),**component_selection},
            'license':'ODbL-1.0','attribution':'© OpenStreetMap contributors; Geofabrik extract. Heights: AHN / PDOK CC0.'}
    path=OUTPUT/f'{mode}.json';path.write_text(json.dumps(result,separators=(',',':'))+'\n')
    return {'nodes':len(nodes),'edges':len(edges),'source_ways':len(ways),'bytes':path.stat().st_size,
            'height_sources':dict(Counter(node_heights)),'processing':dict(stats),'turn_restrictions':len(turn_rules),
            'unresolved_restrictions':unresolved,'connectivity':result['connectivity'],
            'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    source=json.loads(gzip.decompress(SOURCE.read_bytes()))
    report={'source':str(SOURCE),'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            'license':'ODbL-1.0','attribution':'© OpenStreetMap contributors / Geofabrik',
            'assumptions':{'tunnels_nap_m':-12,'height_gaps':'Linear interpolation along same source arc; no 2D road geometry removed except all-nodata arcs.',
                           'untagged_speed':'Built-up area 50km/h, living_street15, motorway daytime100. No general bicycle speed limit.',
                           'components':'Largest weak component retained as requested. Barriers terminalize blocked source nodes.'},'graphs':{}}
    for mode in ['cars','bikes']:
        report['graphs'][mode]=build(source,mode)
        print(mode,json.dumps({k:v for k,v in report['graphs'][mode].items() if k!='unresolved_restrictions'}),flush=True)
    (OUTPUT/'osm-build-report.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
