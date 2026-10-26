"""Match GTFS routing to retained BRT rails. Written by AI on 2026-10-26 by model GPT-6."""
from collections import defaultdict
import heapq
import json
import math
from shapely.geometry import Point,LineString,box
from shapely.ops import substring
from .build import BOUNDS,SOURCE,parts
from .elevations import PhysicalForm
from .supplement import fill_gaps


def matched():
    planar=json.loads((SOURCE/'planar.json').read_text())
    physical=PhysicalForm()
    results=[]
    failures=[]
    for mode in ('tram','metro','train'):
        tree,geometries,features=physical.groups[mode]
        adjacency=defaultdict(list)
        def node(p):return tuple(round(v,2) for v in p)
        for index,line in enumerate(geometries):
            a,b=node(line.coords[0]),node(line.coords[-1])
            adjacency[a].append((b,line.length,index,0,line.length))
            adjacency[b].append((a,line.length,index,line.length,0))
        def anchors(coordinate):
            point=Point(coordinate)
            nearest=int(tree.nearest(point))
            minimum=point.distance(geometries[nearest])
            if minimum>100:return []
            radius=40 if mode=='train' else 12
            count=12 if mode=='train' else 5
            candidates=sorted((point.distance(geometries[int(i)]),int(i)) for i in tree.query(point.buffer(minimum+radius)))[:count]
            return [(index,geometries[index].project(point),distance) for distance,index in candidates]
        def route(a,b):
            ia,da=a[:2];ib,db=b[:2]
            if ia==ib:return [(ia,da,db)]
            ga,gb=geometries[ia],geometries[ib]
            # Every connection is a real BRT endpoint; XY crossings do not invent transfers.
            starts=[(node(ga.coords[0]),da,[(ia,da,0)]),(node(ga.coords[-1]),ga.length-da,[(ia,da,ga.length)])]
            ends={node(gb.coords[0]):(db,0),node(gb.coords[-1]):(gb.length-db,gb.length)}
            queue=[];best={};serial=0
            straight=ga.interpolate(da).distance(gb.interpolate(db))
            for start,cost,path in starts:
                heapq.heappush(queue,(cost,serial,start,path));serial+=1
            winner=None
            while queue:
                cost,_,current,path=heapq.heappop(queue)
                if cost>=best.get(current,math.inf):continue
                best[current]=cost
                if winner is not None and cost>winner[0]:break
                if cost>max(400,straight*3+200):continue
                if current in ends:
                    extra,offset=ends[current]
                    candidate=(cost+extra,path+[(ib,offset,db)])
                    if winner is None or candidate[0]<winner[0]:winner=candidate
                for other,length,index,start,end in adjacency[current]:
                    if cost+length<best.get(other,math.inf):
                        heapq.heappush(queue,(cost+length,serial,other,path+[(index,start,end)]));serial+=1
            return winner[1] if winner else None
        for group in (g for g in planar if g['mode']==mode):
            intervals=defaultdict(list)
            for path in group['paths']:
                candidates=[anchors(p) for p in path]
                # Retain connected parallel-track choices rather than independently
                # jumping to whichever rail happens to be nearest at each fix.
                states={i:(a[2]*4,[]) for i,a in enumerate(candidates[0])}
                selected=[]
                for position in range(1,len(path)):
                    updated={}
                    for j,b in enumerate(candidates[position]):
                        choices=[]
                        for i,(cost,history) in states.items():
                            steps=route(candidates[position-1][i],b)
                            if steps is not None:
                                length=sum(abs(end-start) for _,start,end in steps)
                                choices.append((cost+length+b[2]*4,history+[steps]))
                        if choices:updated[j]=min(choices,key=lambda c:c[0])
                    if not updated:
                        if states:selected.extend(min(states.values(),key=lambda c:c[0])[1])
                        selected.append(None)
                        states={i:(a[2]*4,[]) for i,a in enumerate(candidates[position])}
                    else:states=updated
                if states:selected.extend(min(states.values(),key=lambda c:c[0])[1])
                for steps,aa,bb in zip(selected,path,path[1:]):
                    if steps is None:
                        failures.append({'mode':mode,'line':group['line'],'direction':group['direction'],'a':aa,'b':bb,'length':math.dist(aa,bb)})
                        continue
                    for index,start,end in steps:
                        if abs(start-end)>.02:
                            intervals[index,1 if end>start else -1].append((min(start,end),max(start,end)))
            paths=[]
            for (index,direction),ranges in sorted(intervals.items()):
                merged=[]
                for a,b in sorted(ranges):
                    if merged and a<=merged[-1][1]+.05:merged[-1][1]=max(b,merged[-1][1])
                    else:merged.append([a,b])
                for a,b in merged:
                    geometry=substring(geometries[index],a,b) if direction>0 else substring(geometries[index],b,a)
                    for g in parts(geometry.intersection(box(*BOUNDS))):
                        if g.length<.1:continue
                        prop=features[index]['properties']
                        physical_form=prop.get('fysiekvoorkomen') or ''
                        paths.append({'xy':list(g.simplify(.5,preserve_topology=False).coords),'physical':'tunnel' if 'in tunnel' in physical_form else 'bridge' if 'brug' in physical_form else 'surface','brtId':features[index]['id'],'sourcePhysical':physical_form,'orientation':direction,'offsets':[geometries[index].project(Point(g.coords[0])),geometries[index].project(Point(g.coords[-1]))]})
            results.append({'mode':mode,'line':group['line'],'direction':group['direction'],'paths':paths})
    for group in planar:
        if group['mode']=='ferry':results.append({**group,'paths':[{'xy':list(g.coords),'physical':'water','brtId':None} for p in group['paths'] for g in parts(LineString(p).intersection(box(*BOUNDS)))]})
    # GTFS direction IDs can differ between route variants. Physical traversal,
    # rather than that label, is the final de-duplication key.
    intervals=defaultdict(list)
    originals={}
    for mode,(_,geometries,features) in physical.groups.items():
        originals.update({f['id']:(g,f['properties']) for g,f in zip(geometries,features)})
    for group in results:
        if group['mode']=='ferry':continue
        for path in group['paths']:
            intervals[group['mode'],group['line'],path['brtId'],path['orientation']].append(sorted(path['offsets']))
    consolidated=defaultdict(list)
    for (mode,line,identifier,direction),ranges in sorted(intervals.items()):
        merged=[]
        for a,b in sorted(ranges):
            if merged and a<=merged[-1][1]+.05:merged[-1][1]=max(b,merged[-1][1])
            else:merged.append([a,b])
        geometry,props=originals[identifier]
        form=props.get('fysiekvoorkomen') or ''
        for a,b in merged:
            g=substring(geometry,a,b) if direction>0 else substring(geometry,b,a)
            consolidated[mode,line,direction].append({'xy':list(g.simplify(.5,preserve_topology=False).coords),'physical':'tunnel' if 'in tunnel' in form else 'bridge' if 'brug' in form else 'surface','brtId':identifier,'sourcePhysical':form,'orientation':direction,'offsets':[a,b]})
    ferries=[g for g in results if g['mode']=='ferry']
    results=[{'mode':mode,'line':line,'direction':str(direction),'paths':paths} for (mode,line,direction),paths in sorted(consolidated.items())]+ferries
    supplements,resolved=fill_gaps(failures)
    results.extend(supplements)
    (SOURCE/'matched.json').write_text(json.dumps(results,separators=(',',':'))+'\n')
    unresolved=[f for f in failures if not any(all(f[k]==r[k] for k in ('mode','line','direction','a','b')) for r in resolved)]
    in_bounds=[f for f in unresolved if LineString([f['a'],f['b']]).intersects(box(*BOUNDS))]
    report={'writtenBy':'AI, GPT-6, 2026-10-26','method':'GTFS line/direction and routing matched to same-mode BRT network. Candidate anchor distance <=100 m; alternatives within nearest +12 m (train +40 m, up to 12 candidates). Minimum-cost connected sequence: metres travelled + 4 x anchor offset. Shortest paths follow existing source endpoints; XY crossings do not invent connections. Overlapping intervals per BRT feature, passenger line and physical traversal direction are unioned before 0.5 m simplification. BGT spoor supplies the Woudestein BRT gap; its intervals are unioned the same way. Final paths clip to requested bounds.','unmatchedLegs':unresolved,'unmatchedLegsInsideOutput':in_bounds,'bgtResolvedLegs':resolved,'groups':len(results),'paths':sum(len(g['paths']) for g in results)}
    (SOURCE/'matching-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('unmatchedLegs','bgtResolvedLegs')},indent=2),flush=True)
    print('Unmatched inside output:',len(in_bounds),'BGT resolved:',len(resolved),flush=True)
    return results


if __name__=='__main__':matched()
