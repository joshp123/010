import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {gunzipSync} from 'node:zlib';
import {createJourneyPlanner} from '../public/traffic-journeys.js';
function road(id,start,end,coords) {const points=coords.map(([x,z])=>({x,y:0,z}));return {id,start,end,direction:3,points,length:100};}
const roads=[road(1,1,2,[[-100,0],[0,0]]),road(2,2,3,[[0,0],[100,0]]),road(3,2,4,[[0,0],[0,100]]),road(4,2,5,[[0,0],[0,-100]])];
let planner=createJourneyPlanner(roads,{turnRestrictions:[{from:1,via:2,to:3,fromDirection:1,toDirection:1,restriction:'no_left_turn'}]});
assert.deepEqual(planner.transitions(0,1).map(s=>s.roadIndex),[1,3]);
planner=createJourneyPlanner(roads,{turnRestrictions:[{from:1,via:2,to:3,fromDirection:1,toDirection:1,restriction:'only_right_turn'}]});
assert.deepEqual(planner.transitions(0,1).map(s=>s.roadIndex),[2],'only_* excludes all other exits');
assert.ok(planner.transitions(3,-1).some(s=>s.roadIndex===1),'restriction is specific to incoming direction');
const root=new URL('../',import.meta.url),url=p=>new URL(p,root).href;
const models='data:text/javascript;base64,'+Buffer.from((await readFile(new URL('public/traffic-models.js',root),'utf8')).replace("'three'",JSON.stringify(url('public/vendor/three/build/three.module.js')))).toString('base64');
const source=(await readFile(new URL('public/simulated-traffic.js',root),'utf8')).replace("'three'",JSON.stringify(url('public/vendor/three/build/three.module.js'))).replace("'./traffic-motion.js'",JSON.stringify(url('public/traffic-motion.js'))).replace("'./traffic-journeys.js'",JSON.stringify(url('public/traffic-journeys.js'))).replace("'./traffic-models.js'",JSON.stringify(models));
const {decodeTrafficRoads,createSimulatedTraffic}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const network=decodeTrafficRoads(gunzipSync(await readFile(new URL('public/data/traffic/roads.pb.gz',root))));
const actual=network.roads.map(r=>{const points=r.coordinates.map(([lon,lat])=>({x:(lon-4.49)*68600,y:0,z:(51.915-lat)*111300}));return {...r,points,length:points.slice(1).reduce((s,p,i)=>s+Math.hypot(p.x-points[i].x,p.z-points[i].z),0)};});
const {rules}=JSON.parse(await readFile(new URL('public/data/traffic/turn-restrictions.json',root),'utf8'));
const baseline=createJourneyPlanner(actual),restricted=createJourneyPlanner(actual,{turnRestrictions:rules});
assert.equal(restricted.diagnostics().unresolvedTurnRestrictions,0);
assert.equal(restricted.diagnostics().turnRestrictionRules,10);
let removed=0;
for(const rule of rules) {
 const index=actual.findIndex(r=>r.id===rule.from&&(rule.fromDirection===1?r.end:r.start)===rule.via);
 assert.ok(index>=0);
 const before=baseline.transitions(index,rule.fromDirection),after=restricted.transitions(index,rule.fromDirection);
 assert.ok(before.some(step=>actual[step.roadIndex].id===rule.to&&step.direction===rule.toDirection),'verified target exists in runtime graph');
 if(rule.restriction.startsWith('only_')) {assert.ok(after.length);assert.ok(after.every(step=>actual[step.roadIndex].id===rule.to&&step.direction===rule.toDirection));}
 else assert.ok(after.every(step=>actual[step.roadIndex].id!==rule.to||step.direction!==rule.toDirection));
 removed+=before.length-after.length;
}
assert.ok(removed>=10);console.log(`Actual OSM/NWB rules: ${rules.length}; blocked directed transitions: ${removed}`);

// Exercise the actual loader: loaded rules survive reprojection; an unavailable
// source reports unavailable and never inherits stale restrictions.
const originalFetch=globalThis.fetch;
const roadBytes=await readFile(new URL('public/data/traffic/roads.pb.gz',root));
const layer=createSimulatedTraffic({maximumVehicles:0,project:(lat,lon,alt)=>({x:(lon-4.49)*68600,y:alt,z:(51.915-lat)*111300})});
try {
 globalThis.fetch=async url=>String(url).endsWith('turn-restrictions.json')?new Response(JSON.stringify({version:1,mode:'motorcar',rules})):new Response(roadBytes);
 await layer.load();assert.equal(layer.statistics().restrictionStatus,'loaded:10');assert.equal(layer.statistics().network.turnRestrictionRules,10);
 layer.refreshProjection();assert.equal(layer.statistics().network.turnRestrictionRules,10);
 globalThis.fetch=async url=>String(url).endsWith('turn-restrictions.json')?new Response('',{status:404}):new Response(roadBytes);
 await layer.load();assert.match(layer.statistics().restrictionStatus,/unavailable:HTTP 404/);assert.equal(layer.statistics().network.turnRestrictionRules,0);
} finally {globalThis.fetch=originalFetch;layer.dispose();}
