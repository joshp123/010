import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {gunzipSync} from 'node:zlib';
import {createJourneyPlanner} from '../public/traffic-journeys.js';
const root=new URL('../',import.meta.url),url=p=>new URL(p,root).href;
const models='data:text/javascript;base64,'+Buffer.from((await readFile(new URL('public/traffic-models.js',root),'utf8')).replace("'three'",JSON.stringify(url('public/vendor/three/build/three.module.js')))).toString('base64');
const source=(await readFile(new URL('public/simulated-traffic.js',root),'utf8')).replace("'three'",JSON.stringify(url('public/vendor/three/build/three.module.js'))).replace("'./traffic-motion.js'",JSON.stringify(url('public/traffic-motion.js'))).replace("'./traffic-journeys.js'",JSON.stringify(url('public/traffic-journeys.js'))).replace("'./traffic-models.js'",JSON.stringify(models));
const {decodeTrafficRoads,createSimulatedTraffic}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const network=decodeTrafficRoads(gunzipSync(await readFile(new URL('public/data/traffic/roads.pb.gz',root))));
const actual=network.roads.map(r=>{const points=r.coordinates.map(([lon,lat])=>({x:(lon-4.49)*68600,y:0,z:(51.915-lat)*111300}));return {...r,points,length:points.slice(1).reduce((s,p,i)=>s+Math.hypot(p.x-points[i].x,p.z-points[i].z),0)};});
const audit=JSON.parse(await readFile(new URL('source-data/traffic/osm-municipality-turn-audit.json',root),'utf8'));
const rules=JSON.parse(await readFile(new URL('public/data/traffic/turn-restrictions.json',root),'utf8')).rules;
const baseline=createJourneyPlanner(actual), restricted=createJourneyPlanner(actual,{turnRestrictions:rules}),report=[];
for(const r of audit.relations.filter(r=>audit.strictCandidateRelations.includes(r.osmRelation))) {
const dir=r.matches.from.nwbAtStart?-1:1,toDir=r.matches.to.nwbAtStart?1:-1;
const index=actual.findIndex(e=>e.id===r.fromNWB&&(dir===1?e.end:e.start)===r.nwbJunction);
const options=index>=0?baseline.transitions(index,dir):[];
const after=index>=0?restricted.transitions(index,dir):[];
report.push({id:r.osmRelation,active:rules.some(rule=>rule.osmRelation===r.osmRelation),exists:options.some(s=>actual[s.roadIndex].id===r.toNWB&&s.direction===toDir),options:options.length,remainingOptions:after.length,newlyProhibited:options.filter(s=>!after.some(a=>a.roadIndex===s.roadIndex&&a.direction===s.direction)).map(s=>({roadId:actual[s.roadIndex].id,direction:s.direction})),restriction:r.restriction});
}
console.log(JSON.stringify({diagnostics:restricted.diagnostics(),relations:report},null,2));
