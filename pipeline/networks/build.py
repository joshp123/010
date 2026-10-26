"""Build M1 directed networks. Written by AI on 2026-10-26 by model GPT-6 Astra."""
import csv
import hashlib
import io
import json
import math
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from shapely.geometry import LineString, Point, box, shape
from shapely.ops import substring, unary_union
from shapely.strtree import STRtree
from acquire import ROOT, SOURCE
from heights import HeightSampler

BOUNDS = (89750, 434750, 96500, 438000)
AREA = box(*BOUNDS)
OUTPUT = ROOT / 'scene/v1/networks'
DROPPED_CODES = {'VP','VZ','FP','BUS','BU','OVB','TR','TRAM','RP','VDA','VDF','VDV','CADO'}


def read_sources():
    features = [f for p in sorted(SOURCE.glob('page-*.json')) for f in json.loads(p.read_text())['features']]
    records = []
    for feature in features:
        properties = feature['properties']
        for coordinates in feature['geometry']['coordinates']:
            original = LineString(coordinates)
            clipped = original.intersection(AREA)
            parts = list(clipped.geoms) if hasattr(clipped, 'geoms') else [clipped]
            for part in parts:
                if part.geom_type != 'LineString' or part.length < .1:
                    continue
                records.append({'properties': properties, 'line': part,
                    'begin': properties['jte_id_beg'] if Point(part.coords[0]).distance(Point(original.coords[0])) < .05 else None,
                    'end': properties['jte_id_end'] if Point(part.coords[-1]).distance(Point(original.coords[-1])) < .05 else None})
    ids = {str(r['properties']['wvk_id']) for r in records}
    wkd_path = ROOT / 'sources/network-wkd/2026-10-26/verkeerstypen.zip'
    with zipfile.ZipFile(wkd_path) as archive:
        name = next(n for n in archive.namelist() if n.endswith('.csv'))
        wkd = {r['WVK_ID']:r for r in csv.DictReader(io.TextIOWrapper(archive.open(name),encoding='utf-8-sig'), delimiter=';') if r['WVK_ID'] in ids}
    brt = []
    manifests = []
    archive = ROOT / 'sources/overview-brt/2026-10-26'
    for collection in ['wegdeel_vlak','wegdeel_lijn']:
        for path in sorted((archive/collection).glob('*.json')):
            used = False
            for feature in json.loads(path.read_text())['features']:
                geometry = shape(feature['geometry'])
                if not geometry.intersects(AREA):continue
                p = feature['properties']
                if p.get('status') != 'in gebruik':continue
                brt.append((p,geometry))
                used=True
            if used:manifests.append({'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    tunnels = [(p,g.buffer(.5)) for p,g in brt if p.get('fysiekvoorkomen') == 'in tunnel']
    bridges = unary_union([g for p,g in brt if 'brug' in (p.get('fysiekvoorkomen') or '')]).buffer(.5)
    motorways = unary_union([g for p,g in brt if 'autosnelweg' in (p.get('typeweg') or '') or 'autoweg' in (p.get('typeweg') or '')]).buffer(1)
    return records, wkd, tunnels, motorways, bridges, manifests


def densified_coordinates(line):
    simplified = line.simplify(.5,preserve_topology=True)
    coordinates = list(simplified.coords)
    output = [coordinates[0]]
    for first, last in zip(coordinates,coordinates[1:]):
        length = math.dist(first,last)
        for step in range(1,math.ceil(length/10)+1):
            t = min(step*10/length,1)
            output.append((first[0]+t*(last[0]-first[0]),first[1]+t*(last[1]-first[1])))
    return output


def make_parallel_test(records):
    paths = [r['line'] for r in records if r['properties']['bst_code']=='FP']
    tree = STRtree(paths)
    def parallel(point, tangent):
        for index in tree.query(point.buffer(12)):
            path=paths[index]
            distance=path.project(point)
            if point.distance(path)>12:continue
            a=path.interpolate(max(0,distance-3));b=path.interpolate(min(path.length,distance+3))
            vector=np.array([b.x-a.x,b.y-a.y]);denom=np.linalg.norm(vector)*np.linalg.norm(tangent)
            if denom and abs(np.dot(vector,tangent)/denom)>=math.cos(math.radians(25)):return True
        return False
    return parallel


def build_graph(mode, records, wkd, tunnels, motorways, sampler, parallel, bridges):
    nodes=[];edges=[];edge_ways=[];ways=[];junctions=defaultdict(list);stats=Counter();height_sources=Counter()
    def node(coordinate,junction,tunnel):
        # Shared NWB junctions only; crossing polylines do not imply a junction.
        if junction is not None:
            for existing in junctions[junction]:
                if math.dist(nodes[existing][:2],coordinate)<.5:
                    return existing
        if tunnel:z,source=-12.,'assumed_tunnel_-12m'
        else:z,source=sampler.sample(*coordinate, bridge=bridges.covers(Point(coordinate)))
        if z is None:return None
        index=len(nodes);nodes.append([round(coordinate[0],1),round(coordinate[1],1),round(z,1)])
        height_sources[source]+=1
        if junction is not None:junctions[junction].append(index)
        return index
    for record in records:
        p=record['properties'];code=p['bst_code'];line=record['line'];direction=p['rijrichtng'];wk=wkd.get(str(p['wvk_id']))
        if mode=='cars':
            if code in DROPPED_CODES:stats['drop_code_'+code]+=1;continue
            allowed=[direction in ('H','B'), direction in ('T','B')]
            if wk:allowed=[allowed[0] and wk['AUTO_H']=='J',allowed[1] and wk['AUTO_T']=='J']
        else:
            if code!='FP' and code in DROPPED_CODES:stats['drop_code_'+code]+=1;continue
            if code=='FP':allowed=[direction in ('H','B'),direction in ('T','B')]
            elif wk:allowed=[wk['FIETS_H']=='J',wk['FIETS_T']=='J']
            else:allowed=[direction in ('H','B'),direction in ('T','B')];stats['carriageway_direction_fallback_nwb']+=1
            if code!='FP' and (p['wegbehsrt']=='R' or motorways.intersection(line).length>line.length*.5):
                stats['drop_motorway_or_rijksweg']+=1;continue
        if not any(allowed):stats['drop_unknown_or_prohibited_direction']+=1;continue
        coordinates=densified_coordinates(line)
        # Segment at 10m maximum, retaining all 0.5m-simplified corners.
        way_index=len(ways)
        way={'wvk_id':p['wvk_id'],'name':p['stt_naam'],'class':code,'manager':p['wegbehsrt'],
             'manager_code':p['wegbehcode'],'direction':direction,'oneway':sum(allowed)==1,
             'tunnel':False,'cycling_direction_source':'NWB FP' if code=='FP' else 'WKD' if wk else 'NWB fallback'}
        ways.append(way)
        tunnel_way_index=None
        previous=None
        for index,(a,b) in enumerate(zip(coordinates,coordinates[1:])):
            segment=LineString([a,b]);mid=segment.interpolate(.5,normalized=True)
            if mode=='bikes' and code!='FP' and parallel(mid,np.subtract(b,a)):
                stats['drop_parallel_segments']+=1;previous=None;continue
            # NWB negative level alone includes underpasses; BRT supplies the actual tunnel mask.
            tunnel=False
            for tunnel_properties,tunnel_geometry in tunnels:
                use=tunnel_properties.get('hoofdverkeersgebruik') or ''
                if use=='voetgangers' or (mode=='cars' and 'fietsers' in use):continue
                if not tunnel_geometry.covers(mid):continue
                corners=list(tunnel_geometry.minimum_rotated_rectangle.exterior.coords)
                axis=max((np.subtract(v,u) for u,v in zip(corners,corners[1:])),key=np.linalg.norm)
                tangent=np.subtract(b,a);denominator=np.linalg.norm(axis)*np.linalg.norm(tangent)
                if denominator and abs(np.dot(axis,tangent)/denominator)>=math.cos(math.radians(35)):
                    tunnel=True;break
            tunnel=tunnel or ('maastunnel' in p['stt_naam'].lower() and (p.get('rel_hoogte') or 0)<0)
            first = previous if previous is not None else node(a,record['begin'] if index==0 else None,tunnel)
            last=node(b,record['end'] if index==len(coordinates)-2 else None,tunnel)
            if first is None or last is None:stats['drop_nodata_segments']+=1;previous=None;continue
            previous=last
            if first==last:continue
            # Each tunnel flag must describe only its own segment, not the entire source feature.
            this_way=way_index
            if tunnel:
                if tunnel_way_index is None:
                    ways.append({**way,'tunnel':True});tunnel_way_index=len(ways)-1
                this_way=tunnel_way_index
                nodes[first][2]=-12.
                nodes[last][2]=-12.
            speed = 18 if mode=='bikes' else 15 if code in ('ERF','PP') else 50 if p['wegbehsrt']=='R' else 30
            for start,end,yes in [(first,last,allowed[0]),(last,first,allowed[1])]:
                if yes:edges.append([start,end,speed,1,code]);edge_ways.append(this_way)
            stats['kept_segments']+=1
    rows=np.array([e[0] for e in edges]);cols=np.array([e[1] for e in edges])
    adjacency=coo_matrix((np.ones(len(edges)),(rows,cols)),shape=(len(nodes),len(nodes))).tocsr()
    count,labels=connected_components(adjacency,directed=True,connection='weak')
    lengths=defaultdict(float);edge_counts=Counter()
    for e in edges:lengths[int(labels[e[0]])]+=math.dist(nodes[e[0]][:2],nodes[e[1]][:2]);edge_counts[int(labels[e[0]])]+=1
    largest=max(lengths,key=lengths.get)
    kept_indices=[i for i,e in enumerate(edges) if labels[e[0]]==largest]
    used_nodes=sorted({v for i in kept_indices for v in edges[i][:2]});remap={old:new for new,old in enumerate(used_nodes)}
    used_ways=sorted({edge_ways[i] for i in kept_indices});way_remap={old:new for new,old in enumerate(used_ways)}
    final_edges=[[remap[edges[i][0]],remap[edges[i][1]],*edges[i][2:]] for i in kept_indices]
    strong_count,strong_labels=connected_components(adjacency,directed=True,connection='strong')
    strong_sizes=Counter(strong_labels[used_nodes]);strong_largest=max(strong_sizes.values())
    connectivity={'input_weak_components':int(count),'largest_component_edge_share':len(kept_indices)/len(edges),
        'largest_component_directed_length_share':lengths[largest]/sum(lengths.values()),
        'largest_component_node_share':len(used_nodes)/len(nodes),'dropped_edges':len(edges)-len(kept_indices),
        'retained_weak_components':1,'largest_strong_component_node_share':strong_largest/len(used_nodes),
        'components_by_directed_length_m':sorted(lengths.values(),reverse=True)[:10]}
    result={'version':1,'crs':'EPSG:28992+5709','bounds_rd':BOUNDS,'nodes':[nodes[i] for i in used_nodes],
        'edges':final_edges,'ways':[ways[i] for i in used_ways],'edge_ways':[way_remap[edge_ways[i]] for i in kept_indices],
        'tunnel_edges':[j for j,i in enumerate(kept_indices) if ways[edge_ways[i]]['tunnel']],
        'connectivity':connectivity}
    path=OUTPUT/f'{mode}.json';path.write_text(json.dumps(result,separators=(',',':'))+'\n')
    return {'nodes':len(used_nodes),'edges':len(final_edges),'bytes':path.stat().st_size,'connectivity':connectivity,
        'filters':dict(stats),'height_samples':dict(height_sources),'kept_codes':dict(Counter(w['class'] for w in result['ways'])),
        'tunnel_edges':len(result['tunnel_edges']),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    records,wkd,tunnels,motorways,bridges,brt_sources=read_sources()
    print(f'{len(records)} clipped NWB parts, {len(wkd)} WKD matches',flush=True)
    sampler=HeightSampler();parallel=make_parallel_test(records)
    report={'bounds_rd':BOUNDS,'status':'built',
        'sources':{'NWB':'Rijkswaterstaat / PDOK CC0-1.0', 'WKD':'Rijkswaterstaat / NDW CC0-1.0',
                   'AHN':'AHN / Rijkswaterstaat / PDOK CC0-1.0', 'BRT':'Kadaster / PDOK CC-BY-4.0'},
        'wkd_matches':len(wkd),'brt_sources':brt_sources,
        'car_eligible_codes':sorted({r['properties']['bst_code'] for r in records}-DROPPED_CODES),
        'car_dropped_codes':sorted({r['properties']['bst_code'] for r in records}&DROPPED_CODES),
        'road_managers':dict(Counter(r['properties']['wegbehsrt'] for r in records)),
        'assumptions':{'tunnel_nap_m':-12, 'tunnel_depth_is_surveyed':False,
                       'speed_and_lane_fields':'Simulation defaults; not measured limits or lane counts',
                       'bike_parallel_path_threshold_m':12, 'bike_parallel_angle_degrees':25,
                       'law':'RVV 1990 articles 5 and 42; the 12m spatial rule is user-specified, not law text',
                       'simplification_tolerance_m':.5,'max_sampling_interval_m':10,'coordinate_precision_m':.1},
        'turn_restrictions':'Not integrated; no OSM/ODbL source used',
        'graphs':{}}
    for mode in ['cars','bikes']:
        report['graphs'][mode]=build_graph(mode,records,wkd,tunnels,motorways,sampler,parallel,bridges)
        print(mode,json.dumps(report['graphs'][mode]),flush=True)
    (OUTPUT/'build-report.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
