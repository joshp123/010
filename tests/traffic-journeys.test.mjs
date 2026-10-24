import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {gunzipSync} from 'node:zlib';
import {createJourneyPlanner} from '../public/traffic-journeys.js';
const trafficModels = 'data:text/javascript;base64,' + Buffer.from((await readFile(new URL('../public/traffic-models.js',import.meta.url),'utf8')).replace("'three'",JSON.stringify(new URL('../public/vendor/three/build/three.module.js',import.meta.url).href))).toString('base64');
const source=(await readFile(new URL('../public/simulated-traffic.js',import.meta.url),'utf8'))
 .replace("'./traffic-models.js'",JSON.stringify(trafficModels)).replace("'three'",JSON.stringify(new URL('../public/vendor/three/build/three.module.js',import.meta.url).href))
 .replace("'./traffic-motion.js'",JSON.stringify(new URL('../public/traffic-motion.js',import.meta.url).href))
 .replace("'./traffic-journeys.js'",JSON.stringify(new URL('../public/traffic-journeys.js',import.meta.url).href));
const {decodeTrafficRoads}=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
function road(id,start,end,coords,direction=1) {
 const points=coords.map(([x,z,y=0])=>({x,y,z}));
 return {id,start,end,direction,points,length:points.slice(1).reduce((s,p,i)=>s+Math.hypot(p.x-points[i].x,p.z-points[i].z),0)};
}
const synthetic=[
 road(1,1,2,[[0,0],[100,0]]),road(2,2,3,[[100,0],[100,100]]),
 road(3,3,4,[[100,100],[0,100]]),road(4,4,5,[[0,100],[-100,100]]),
 road(5,2,6,[[100,0,20],[200,0,20]]), // source junction but incompatible height
 road(6,2,7,[[103,0],[200,0]]), // same ID is insufficient when geometry disagrees
 road(7,70,71,[[50,-100],[50,100]]), // crosses road 1, no junction: must never connect
 road(8,2,8,[[100,0],[0,0]]), // different edge that reverses direction
];
const planner=createJourneyPlanner(synthetic);
assert.deepEqual(planner.transitions(0,1).map(s=>s.roadIndex),[1]);
assert.equal(planner.plan({roadIndex:0,direction:-1,minDistance:100,maxDistance:1000}),null,'one-way origins cannot be reversed');
const trip=planner.plan({roadIndex:0,direction:1,minDistance:200,maxDistance:1000,random:()=>0,preferDestination:p=>p.x===-100});
assert.deepEqual(trip.path.map(s=>s.road.id),[1,2,3,4]);
assert.equal(trip.origin,1);assert.equal(trip.destination,5);
assert.equal(planner.plan({roadIndex:6,direction:1,minDistance:100,maxDistance:1000}),null,'isolated crossing must not invent a journey');
assert.equal(planner.diagnostics().rejectedHeightGaps,1);
assert.equal(planner.diagnostics().rejectedEndpointGaps,1);
assert.equal(planner.diagnostics().rejectedReversals,1);

// A one-way circulation loop can be necessary to reach an exit. Do not collapse
// it by forbidding revisited junctions; forbid only repeated directed edges.
const circulation = [
 road(20,10,11,[[-100,0],[0,0]]), road(21,11,12,[[0,0],[100,0]]),
 road(22,12,13,[[100,0],[100,100]]), road(23,13,14,[[100,100],[0,100]]),
 road(24,14,11,[[0,100],[0,0]]), road(25,11,15,[[0,0],[-100,0]]),
];
const loopTrip=createJourneyPlanner(circulation).plan({roadIndex:0,direction:1,minDistance:500,maxDistance:1000,random:()=>0,preferDestination:p=>p.x===-100});
assert.deepEqual(loopTrip.path.map(step=>step.road.id),[20,21,22,23,24,25]);

function validate(trip,roads) {
 assert.ok(trip.path.length>=2);
 assert.equal(new Set(trip.path.map(s=>`${s.roadIndex}:${s.direction}`)).size,trip.path.length,'no repeated directed edges in a planned trip');
 for(let i=0;i<trip.path.length;i++) {
  const step=trip.path[i],r=roads[step.roadIndex];
  assert.ok(r.direction===3 || (r.direction===1?1:-1)===step.direction);
  if(!i)continue;
  const last=trip.path[i-1],a=roads[last.roadIndex];
  assert.equal(last.direction===1?a.end:a.start,step.direction===1?r.start:r.end);
  const p=last.direction===1?a.points.at(-1):a.points[0],q=step.direction===1?r.points[0]:r.points.at(-1);
  assert.ok(Math.hypot(p.x-q.x,p.z-q.z)<=.5);
  assert.ok(Math.abs(p.y-q.y)<=3);
 }
}
const report={};
for(const [mode,file,bridgeIds] of [['cars','roads',[600728317,600892247]],['bicycles','cycleways',[600491271,601435887]]]) {
 const network=decodeTrafficRoads(gunzipSync(await readFile(new URL(`../public/data/traffic/${file}.pb.gz`,import.meta.url))));
 const roads=network.roads.map(r=>({...r,...road(r.id,r.start,r.end,r.coordinates.map(([lon,lat])=>[(lon-4.49)*68600,(51.915-lat)*111300]),r.direction)}));
 const graph=createJourneyPlanner(roads),summary={...graph.diagnostics(),areas:{},bridgeJourneys:[]};
 for(const [name,lon,lat] of [['centre',4.48,51.92],['Hoek',4.13,51.98]]) {
  const x=(lon-4.49)*68600,z=(51.915-lat)*111300;
  const closest=roads.map((r,index)=>({index,d:Math.min(...r.points.map(p=>Math.hypot(p.x-x,p.z-z)))})).sort((a,b)=>a.d-b.d).slice(0,30);
  let planned=0;
  for(const {index} of closest)for(const direction of roads[index].direction===3?[1,-1]:roads[index].direction===1?[1]:[-1]) {
   const trip=graph.plan({roadIndex:index,direction,minDistance:mode==='cars'?350:150,maxDistance:4000,random:()=>.7});
   if(trip){validate(trip,roads);planned++;}
  }
  assert.ok(planned>=3,`${mode} ${name} must support several multi-edge journeys`);summary.areas[name]=planned;
 }
 for(const id of bridgeIds) {
  const index=roads.findIndex(r=>r.id===id);assert.ok(index>=0,`${mode} bridge ${id} source exists`);
  const trip=graph.plan({roadIndex:index,direction:1,minDistance:800,maxDistance:5000,random:()=>.5});
  assert.ok(trip,`${mode} bridge ${id} connects to onward journey`);validate(trip,roads);
  const latitudes=network.roads[index].coordinates.map(p=>p[1]);
  assert.ok(Math.min(...latitudes)<51.908 && Math.max(...latitudes)>51.912,'actual river crossing, not a named quay fragment');
  summary.bridgeJourneys.push({sourceId:id,origin:trip.origin,destination:trip.destination,edges:trip.path.length,metres:Math.round(trip.length)});
 }
 report[mode]=summary;
}
console.log(JSON.stringify(report,null,2));
