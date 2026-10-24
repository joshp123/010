import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {gunzipSync} from 'node:zlib';
import {createJourneyPlanner} from '../public/traffic-journeys.js';
const trafficModels = 'data:text/javascript;base64,' + Buffer.from((await readFile(new URL('../public/traffic-models.js',import.meta.url),'utf8')).replace("'three'",JSON.stringify(new URL('../public/vendor/three/build/three.module.js',import.meta.url).href))).toString('base64');
const root=new URL('../',import.meta.url);
const text=await readFile(new URL('public/simulated-traffic.js',root),'utf8');
const source=text.replace("'./traffic-models.js'",JSON.stringify(trafficModels)).replace("'three'",JSON.stringify(new URL('public/vendor/three/build/three.module.js',root).href)).replace("'./traffic-motion.js'",JSON.stringify(new URL('public/traffic-motion.js',root).href)).replace("'./traffic-journeys.js'",JSON.stringify(new URL('public/traffic-journeys.js',root).href));
const {decodeTrafficRoads}=await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const csv=gunzipSync(await readFile(new URL('source-data/traffic/wkd-cycling-access.csv.gz',root))).toString().trim().split(/\r?\n/).map(r=>r.split(';'));
const fields=csv.shift(), rows=new Map(csv.map(row=>{const r=Object.fromEntries(fields.map((f,i)=>[f,row[i]]));return [Number(r.WVK_ID),r];}));
function project(network) {return network.roads.map(r=>{const points=r.coordinates.map(([lon,lat])=>({x:(lon-4.49)*68600,y:0,z:(51.915-lat)*111300}));return {...r,points,length:points.slice(1).reduce((s,p,i)=>s+Math.hypot(p.x-points[i].x,p.z-points[i].z),0)};});}
const network=decodeTrafficRoads(gunzipSync(await readFile(new URL('public/data/traffic/cycleways-wkd.pb.gz',root))));
const roads=project(network),planner=createJourneyPlanner(roads);
for(const road of roads) {
 const row=rows.get(road.id);assert.ok(row,`WKD row for ${road.id}`);
 const direction=(row.FIETS_H==='J'?1:0)+(row.FIETS_T==='J'?2:0);
 assert.equal(road.direction,direction,`bicycle-specific permission for ${road.id}`);
}
assert.ok(roads.filter(r=>r.roadClass==='RB').length>15000,'shared streets are represented');
assert.ok(!roads.some(r=>[600728317,600892247].includes(r.id)),'Erasmusbrug motor carriageways exclude bikes');
const report={source:'WKD bicycle access + retained NWB exact IDs',network:planner.diagnostics(),areas:{},bridge:[]};
for(const [area,lon,lat] of [['centre',4.48,51.92],['Hoek',4.13,51.98]]) {
 const x=(lon-4.49)*68600,z=(51.915-lat)*111300;
 const near=roads.map((r,index)=>({index,d:Math.min(...r.points.map(p=>Math.hypot(p.x-x,p.z-z)))})).sort((a,b)=>a.d-b.d).slice(0,100);
 let mixed=0,trips=0,example;
 for(const {index} of near) {
  const road=roads[index];const trip=planner.plan({roadIndex:index,direction:road.direction===2?-1:1,minDistance:400,maxDistance:4000,random:()=>.7});
  if(!trip)continue;trips++;
  const classes=new Set(trip.path.map(s=>s.road.roadClass));
  if(classes.has('FP') && [...classes].some(c=>c!=='FP')) {mixed++;example ||= trip.path.map(s=>({id:s.road.id,direction:s.direction,class:s.road.roadClass}));}
 }
 assert.ok(mixed>=3,`${area}: journeys must connect source cyclepaths to permitted shared streets`);
 report.areas[area]={trips,mixed,example};
}
for(const id of [600491271,601435887]) {
 const index=roads.findIndex(r=>r.id===id);assert.ok(index>=0);
 const direction=roads[index].direction===2?-1:1;
 const trip=planner.plan({roadIndex:index,direction,minDistance:800,maxDistance:4000,random:()=>.5});assert.ok(trip);
 report.bridge.push({id,direction,edges:trip.path.length,metres:Math.round(trip.length)});
}
console.log(JSON.stringify(report,null,2));
