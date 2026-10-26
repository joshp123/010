"""Inspect the delivered graph, not a fixture. AI-written 2026-10-26, GPT-6 Astra."""
import json
import math
from collections import Counter
from acquire import ROOT


def main():
    output=ROOT/'scene/v1/networks'
    report={}
    for mode in ['cars','bikes']:
        graph=json.loads((output/f'{mode}.json').read_text())
        nodes=graph['nodes'];edges=graph['edges'];ways=graph['ways']
        assert all(len(n)==3 and all(math.isfinite(v) for v in n) for n in nodes)
        assert all(89750<=n[0]<=96500 and 434750<=n[1]<=438000 for n in nodes)
        assert len(edges)==len(graph['edge_ways'])
        assert all(0<=e[0]<len(nodes) and 0<=e[1]<len(nodes) and e[0]!=e[1] for e in edges)
        assert all(nodes[edges[i][0]][2]==nodes[edges[i][1]][2]==-12 for i in graph['tunnel_edges'])
        if mode=='cars':assert not any(w['class'] in ['VP','VZ','FP','BUS','BU','OVB','VDF'] for w in ways)
        reverse={(e[0],e[1],graph['edge_ways'][i]) for i,e in enumerate(edges)}
        assert not any((e[1],e[0],graph['edge_ways'][i]) in reverse for i,e in enumerate(edges) if ways[graph['edge_ways'][i]]['oneway'])
        names={}
        for name in ['Lijnbaan','Coolsingel','Schiedamseweg','Erasmusbrug','Willemsbrug','Maastunnel']:
            indices=[i for i,e in enumerate(edges) if ways[graph['edge_ways'][i]]['name']==name]
            used={n for i in indices for n in edges[i][:2]}
            zs=[nodes[n][2] for n in used]
            names[name]={'edges':len(indices),'z_range_nap_m':[min(zs),max(zs)] if zs else None,
                         'classes':dict(Counter(ways[graph['edge_ways'][i]]['class'] for i in indices))}
        if mode=='cars':assert names['Lijnbaan']['edges']==0
        report[mode]={'named_routes':names,'max_segment_xy_m':max(math.dist(nodes[e[0]][:2],nodes[e[1]][:2]) for e in edges),
                      'distinct_source_ways':len({w['wvk_id'] for w in ways}),
                      'known_gap':'Weak connectivity does not mean every node can reach every other node; source dead ends and directed components remain.'}
    (output/'inspection.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
