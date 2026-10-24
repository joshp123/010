// Source-junction journeys. Geography/topology are input; trip demand and speeds
// are illustrative. A selected destination and complete path precede all motion.
import { turnWeight } from './traffic-motion.js';

class MinHeap {
  constructor() { this.items = []; }
  push(item) { let i=this.items.length; this.items.push(item); while(i) { const p=(i-1)>>1; if(this.items[p].cost<=item.cost) break; this.items[i]=this.items[p]; i=p; } this.items[i]=item; }
  pop() {
    const root=this.items[0], last=this.items.pop();
    if(this.items.length) { let i=0; while(i*2+1<this.items.length) { let c=i*2+1; if(c+1<this.items.length && this.items[c+1].cost<this.items[c].cost)c++; if(this.items[c].cost>=last.cost)break; this.items[i]=this.items[c];i=c; } this.items[i]=last; }
    return root;
  }
  get length() { return this.items.length; }
}

export function createJourneyPlanner(roads, { turnRestrictions = [] } = {}) {
  const edges=[], lookup=new Map(), outgoing=new Map();
  const stats={directedEdges:0,connections:0,rejectedEndpointGaps:0,rejectedHeightGaps:0,rejectedReversals:0,terminalEdges:0,components:0,largestComponentEdges:0,turnRestrictionRules:0,unresolvedTurnRestrictions:0,restrictedTransitions:0};
  for(let i=0;i<roads.length;i++) {
    const road=roads[i];
    for(const direction of road.direction===3?[1,-1]:road.direction===1?[1]:road.direction===2?[-1]:[]) {
      const start=direction===1?road.points[0]:road.points.at(-1), end=direction===1?road.points.at(-1):road.points[0];
      const afterStart=direction===1?road.points[1]:road.points.at(-2), beforeEnd=direction===1?road.points.at(-2):road.points[1];
      const edge={index:edges.length,road,roadIndex:i,direction,start,end,from:direction===1?road.start:road.end,to:direction===1?road.end:road.start,
        departure:[afterStart.x-start.x,afterStart.z-start.z],arrival:[end.x-beforeEnd.x,end.z-beforeEnd.z],next:[]};
      edges.push(edge);lookup.set(`${i}:${direction}`,edge);
      if(edge.from) { if(!outgoing.has(edge.from))outgoing.set(edge.from,[]);outgoing.get(edge.from).push(edge); }
    }
  }
  const restrictionsByEdge=new Map();
  for(const rule of turnRestrictions) {
    const from=edges.filter(edge=>edge.road.id===rule.from && edge.to===rule.via && edge.direction===rule.fromDirection);
    const to=edges.filter(edge=>edge.road.id===rule.to && edge.from===rule.via && edge.direction===rule.toDirection);
    if(from.length!==1 || to.length!==1 || !/^(no_|only_)/.test(rule.restriction)) {stats.unresolvedTurnRestrictions++;continue;}
    if(!restrictionsByEdge.has(from[0].index))restrictionsByEdge.set(from[0].index,[]);
    restrictionsByEdge.get(from[0].index).push({only:rule.restriction.startsWith('only_'),to:to[0].index});stats.turnRestrictionRules++;
  }
  const parent=edges.map((_,i)=>i), sizes=edges.map(()=>1);
  function root(i) { while(parent[i]!==i) { parent[i]=parent[parent[i]];i=parent[i]; } return i; }
  function join(a,b) { a=root(a);b=root(b);if(a!==b){parent[b]=a;sizes[a]+=sizes[b];} }
  for(const edge of edges) {
    for(const next of outgoing.get(edge.to)||[]) {
      if(next.road.id===edge.road.id)continue;
      if(Math.hypot(edge.end.x-next.start.x,edge.end.z-next.start.z)>.5) {stats.rejectedEndpointGaps++;continue;}
      // Do not bridge a projected vertical discontinuity. A graphic fallback
      // height is not surveyed elevation; source junction identity is still required.
      if(Math.abs(edge.end.y-next.start.y)>3) {stats.rejectedHeightGaps++;continue;}
      const restrictions=restrictionsByEdge.get(edge.index)||[];
      if(restrictions.some(rule=>rule.only?next.index!==rule.to:next.index===rule.to)) {stats.restrictedTransitions++;continue;}
      const weight=turnWeight(edge.arrival,next.departure);
      if(!weight) {stats.rejectedReversals++;continue;}
      edge.next.push({edge:next,weight});join(edge.index,next.index);stats.connections++;
    }
    if(!edge.next.length)stats.terminalEdges++;
  }
  stats.directedEdges=edges.length;
  stats.components=new Set(edges.map(edge=>root(edge.index))).size;
  stats.largestComponentEdges=Math.max(0,...sizes);

  function plan({roadIndex,direction,random=Math.random,minDistance=350,maxDistance=3000,maxSearchEdges=900,preferDestination=()=>false}) {
    const first=lookup.get(`${roadIndex}:${direction}`);
    if(!first?.from || sizes[root(first.index)]<2)return null;
    const heap=new MinHeap(),costs=new Map([[first.index,first.road.length]]), previous=new Map(), visited=new Set(), destinations=[];
    heap.push({edge:first,cost:first.road.length});
    while(heap.length && visited.size<maxSearchEdges) {
      const {edge,cost}=heap.pop();
      if(visited.has(edge.index)||cost!==costs.get(edge.index))continue;
      visited.add(edge.index);
      if(cost>maxDistance)continue;
      if(edge!==first && edge.to && cost>=minDistance)destinations.push({edge,cost,preferred:preferDestination(edge.end)});
      for(const transition of edge.next) {
        const next=transition.edge;
        if(visited.has(next.index))continue;
        // Positive turn cost favours direct journeys without erasing real loops
        // such as one-way roundabouts or blocks that need a circulation route.
        const nextCost=cost+next.road.length+(transition.weight<5?12:0);
        if(nextCost>maxDistance || nextCost>=(costs.get(next.index)??Infinity))continue;
        costs.set(next.index,nextCost);previous.set(next.index,{edge,weight:transition.weight});heap.push({edge:next,cost:nextCost});
      }
    }
    if(!destinations.length)return null;
    const preferred=destinations.filter(item=>item.preferred), pool=preferred.length?preferred:destinations;
    const destination=pool[Math.min(pool.length-1,Math.floor(random()*pool.length))];
    const path=[]; let cursor=destination.edge;
    while(cursor) {
      const predecessor=previous.get(cursor.index);
      path.push({road:cursor.road,roadIndex:cursor.roadIndex,direction:cursor.direction,weight:predecessor?.weight??8});
      if(cursor===first)break;
      cursor=predecessor?.edge;
    }
    path.reverse();
    if(path[0]?.road!==first.road)return null;
    return {path,origin:first.from,destination:destination.edge.to,length:path.reduce((sum,step)=>sum+step.road.length,0)};
  }
  return {plan,diagnostics:()=>({...stats}),transitions:(roadIndex,direction)=>(lookup.get(`${roadIndex}:${direction}`)?.next||[]).map(({edge,weight})=>({roadIndex:edge.roadIndex,direction:edge.direction,weight}))};
}
