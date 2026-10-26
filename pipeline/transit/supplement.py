"""Fill BRT source gaps using retained BGT rails. Written by AI on 2026-10-26 by model GPT-6."""
from collections import defaultdict
import heapq
import json
import math
from shapely.geometry import shape,Point,LineString,box
from shapely.ops import substring
from .build import ROOT,BOUNDS,parts


def fill_gaps(failures):
    """Use only connected, existing same-mode BGT tracks; never bridge a gap."""
    features=[f for p in sorted((ROOT/'sources/bgt/2026-10-25/spoor').glob('*.json')) for f in json.loads(p.read_bytes())['features'] if f['properties'].get('eind_registratie') is None and f['properties'].get('status')=='bestaand']
    output=[];resolved=[]
    for mode,types in {'tram':['tram'],'train':['trein'],'metro':['sneltram']}.items():
        fs=[f for f in features if f['properties'].get('functie') in types]
        gs=[shape(f['geometry']) for f in fs]
        adjacency=defaultdict(list)
        node=lambda p:tuple(round(v,2) for v in p)
        for i,g in enumerate(gs):
            a,b=node(g.coords[0]),node(g.coords[-1])
            adjacency[a].append((b,g.length,i,0,g.length))
            adjacency[b].append((a,g.length,i,g.length,0))
        intervals=defaultdict(list)
        for failure in failures:
            if failure['mode']!=mode or not LineString([failure['a'],failure['b']]).intersects(box(*BOUNDS)):continue
            anchors=[]
            for xy in [failure['a'],failure['b']]:
                point=Point(xy)
                anchors.append([(d,i,g.project(point)) for d,i,g in sorted((point.distance(g),i,g) for i,g in enumerate(gs))[:4] if d<40])
            choices=[]
            for dist_a,ia,da in anchors[0]:
                for dist_b,ib,db in anchors[1]:
                    if ia==ib:choices.append((abs(da-db)+4*(dist_a+dist_b),[(ia,da,db)]));continue
                    ga,gb=gs[ia],gs[ib]
                    ends={node(gb.coords[0]):(db,0),node(gb.coords[-1]):(gb.length-db,gb.length)}
                    q=[(da,node(ga.coords[0]),[(ia,da,0)]),(ga.length-da,node(ga.coords[-1]),[(ia,da,ga.length)])]
                    heapq.heapify(q);best={}
                    while q:
                        cost,n,steps=heapq.heappop(q)
                        if cost>=best.get(n,math.inf) or cost>failure['length']*3+100:continue
                        best[n]=cost
                        if n in ends:
                            extra,offset=ends[n]
                            choices.append((cost+extra+4*(dist_a+dist_b),steps+[(ib,offset,db)]))
                        for other,length,i,a,b in adjacency[n]:
                            if cost+length<best.get(other,math.inf):heapq.heappush(q,(cost+length,other,steps+[(i,a,b)]))
            if not choices:continue
            cost,steps=min(choices,key=lambda c:c[0])
            resolved.append({**failure,'replacement':'retained BGT spoor, CC0','cost':cost})
            for index,a,b in steps:
                if abs(a-b)>.02:intervals[failure['line'],index,1 if b>a else -1].append(sorted([a,b]))
        byline=defaultdict(list)
        for (line,index,direction),ranges in sorted(intervals.items()):
            merged=[]
            for a,b in sorted(ranges):
                if merged and a<=merged[-1][1]+.05:merged[-1][1]=max(b,merged[-1][1])
                else:merged.append([a,b])
            for a,b in merged:
                geometry=substring(gs[index],a,b) if direction>0 else substring(gs[index],b,a)
                for g in parts(geometry.intersection(box(*BOUNDS))):
                    byline[line,direction].append({'xy':list(g.simplify(.5,preserve_topology=False).coords),'physical':'surface','brtId':None,'bgtId':fs[index]['id'],'orientation':direction})
        output.extend({'mode':mode,'line':line,'direction':str(direction),'paths':paths} for (line,direction),paths in byline.items())
    return output,resolved
