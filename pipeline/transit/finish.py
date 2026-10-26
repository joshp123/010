"""Sample and export physical transit paths. Written by AI on 2026-10-26 by model GPT-6."""
from collections import defaultdict,Counter
import json
import math
import hashlib
from .build import SOURCE,OUTPUT
from .elevations import HeightSampler


def sampled_paths():
    groups=json.loads((SOURCE/'matched.json').read_text())
    prepared=[]
    for group in groups:
        for path in group['paths']:
            xy=path['xy'];kind=path['physical']
            step=5 if kind=='bridge' else 40 if kind in ('tunnel','water') else 20
            coordinates=[xy[0]]
            for a,b in zip(xy,xy[1:]):
                pieces=max(1,math.ceil(math.dist(a,b)/step))
                coordinates.extend([[a[0]+(b[0]-a[0])*i/pieces,a[1]+(b[1]-a[1])*i/pieces] for i in range(1,pieces+1)])
            prepared.append({**path,'mode':group['mode'],'line':group['line'],'direction':group['direction'],'xy':coordinates})
    return prepared


def main():
    paths=sampled_paths()
    sampler=HeightSampler()
    jobs=[(x,y,'dsm_05m' if p['physical']=='bridge' else 'dtm_05m') for p in paths if p['physical'] not in ('tunnel','water') for x,y in p['xy']]
    sampler.acquire(jobs)
    fallback=[(x,y,'dsm_05m') for p in paths if p['physical'] not in ('bridge','tunnel','water') for x,y in p['xy'] if sampler.value(x,y,'dtm_05m') is None]
    sampler.acquire(fallback)
    lines=defaultdict(list);stats=Counter();missing=[];metadata=[]
    for p in paths:
        vertices=[]
        for x,y in p['xy']:
            kind=p['physical']
            if kind=='tunnel':z,method=-12.,'assumed_tunnel_-12_NAP'
            elif kind=='water':z,method=0.,'assumed_ferry_0_NAP'
            elif kind=='bridge':z,method=sampler.value(x,y,'dsm_05m',deck=True),'DSM_deck_p02_3m'
            else:
                z,method=sampler.value(x,y,'dtm_05m'),'DTM'
                if z is None:z,method=sampler.value(x,y,'dtm_05m',nearest=True),'DTM_nearest_valid_within_2m'
                if z is None:z,method=sampler.value(x,y,'dsm_05m'),'DSM_fallback'
                if z is None:z,method=sampler.value(x,y,'dsm_05m',nearest=True),'DSM_nearest_valid_within_2m'
            if z is None:
                missing.append({'mode':p['mode'],'line':p['line'],'xy':[x,y],'physical':kind})
                # No invented AHN values; retain the break for inspection.
                if len(vertices)>1:lines[p['mode'],p['line']].append(vertices)
                vertices=[]
                continue
            stats[method]+=1
            vertices.append([round(x,2),round(y,2),round(z,2),int(kind=='tunnel')])
        if len(vertices)>1:
            index=len(lines[p['mode'],p['line']]);lines[p['mode'],p['line']].append(vertices)
            metadata.append({'mode':p['mode'],'line':p['line'],'path':index,'direction':p['direction'],'brtId':p['brtId'],'bgtId':p.get('bgtId'),'physical':p['physical']})
    output={'lines':[{'mode':mode,'line':line,'paths':paths} for (mode,line),paths in sorted(lines.items())]}
    OUTPUT.mkdir(parents=True,exist_ok=True)
    target=OUTPUT/'transit.json'
    target.write_text(json.dumps(output,separators=(',',':'))+'\n')
    report={'writtenBy':'AI, GPT-6, 2026-10-26','outputBytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'lineCounts':dict(Counter(g['mode'] for g in output['lines'])),'vertices':sum(len(p) for g in output['lines'] for p in g['paths']),'heightMethods':dict(stats),'missingAhn':missing,'pathSources':metadata}
    (SOURCE/'height-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('pathSources','missingAhn')},indent=2),flush=True)
    print('Missing AHN:',len(missing),flush=True)


if __name__=='__main__':main()
