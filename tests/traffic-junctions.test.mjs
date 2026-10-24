import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {createJunctionArbitrator,routeFollowingGap} from '../public/traffic-motion.js';
// Native manager capture, c38d61f, Blaak 51.918427/4.484522, 200m,
// retained verbatim from upstream commit 75cf50d. These five cars were stopped
// at the same positions in captures 27.73s apart. Actual NWB multipart sources
// supply the junction topology; captured lengths include runtime projection.
const initial=JSON.parse(readFileSync(new URL('./fixtures/blaak-stopped-queue-initial.json',import.meta.url)));
const later=JSON.parse(readFileSync(new URL('./fixtures/blaak-stopped-queue.json',import.meta.url)));
const raw=JSON.parse(gunzipSync(readFileSync(new URL('../source-data/traffic/nwb-roads.geojson.gz',import.meta.url))));
const ids=[185274103,185274085,185274058,185274104,600909887];
const roads=new Map(raw.features.filter(f=>ids.includes(f.properties.wvk_id)).map(f=>{
 const p=f.properties,coords=f.geometry.coordinates[0];
 assert.equal(f.geometry.type,'MultiLineString');assert.equal(f.geometry.coordinates.length,1);
 const measured=coords.slice(1).reduce((sum,q,i)=>sum+Math.hypot((q[0]-coords[i][0])*68600,(q[1]-coords[i][1])*111300),0);
 return [p.wvk_id,{id:p.wvk_id,start:p.jte_id_beg,end:p.jte_id_end,length:initial.find(c=>c.roadId===p.wvk_id)?.roadLengthMetres||measured}];
}));
assert.equal(roads.size,5);
const targetIds=[2,17,20,43,50];
function makeCars(){return initial.filter(c=>targetIds.includes(c.vehicleId)).map(c=>{
 const tail=c.roadId===185274103||c.roadId===185274085?[600909887]:[185274103,600909887];
 const path=[c.roadId,...tail].map(id=>({road:roads.get(id),direction:id===185274085||id===600909887?-1:1}));
 const stopped=later.cars.find(v=>v.vehicleId===c.vehicleId&&v.roadId===c.roadId);
 assert.ok(Math.abs(stopped.distanceMetres-c.distanceMetres)<1e-8,'actual unchanged queue');
 for(let i=1;i<path.length;i++)assert.equal(path[i-1].direction===1?path[i-1].road.end:path[i-1].road.start,path[i].direction===1?path[i].road.start:path[i].road.end);
 return {...c,road:path[0].road,direction:path[0].direction,distance:c.distanceMetres,speed:0,journey:{path},journeyIndex:0,next:path[1],ending:false};
});}
function snapshot(cars){const map=new Map();for(const car of cars){if(!map.has(car.road))map.set(car.road,[]);map.get(car.road).push({vehicle:car,direction:car.direction,distance:car.distance});}return map;}
function replay(reverse){
 let cars=makeCars();if(reverse)cars.reverse();
 const control=createJunctionArbitrator(),passed=new Set();
 const first=control.update(cars,snapshot(cars),.05);
 assert.equal(first.get(185274094).vehicleId,17,'leader wins, not earlier array follower 2');
 for(let tick=0;tick<1200;tick++){
  const occupied=snapshot(cars),claims=control.update(cars,occupied,.05);
  cars=cars.filter(car=>{
   const remaining=car.direction===1?car.road.length-car.distance:car.distance;
   const node=car.direction===1?car.road.end:car.road.start;
   const gap=routeFollowingGap(car,occupied);
   let target=Math.min(7,Number.isFinite(gap)?Math.max(0,(gap-5.5)/1.4):7);
   if(remaining<10&&!car.ending&&claims.get(node)!==car)target=Math.min(target,Math.max(0,(remaining-3)*.6));
   car.speed+=Math.max(-.3,Math.min(.1,target-car.speed));
   let travel=car.speed*.05;
   while(travel>0){const available=car.direction===1?car.road.length-car.distance:car.distance;
    if(travel<available){car.distance+=travel*car.direction;break;}
    travel-=available;if(!car.next){passed.add(car.vehicleId);return false;}
    car.journeyIndex++;car.road=car.next.road;car.direction=car.next.direction;car.distance=car.direction===1?0:car.road.length;car.next=car.journey.path[car.journeyIndex+1];car.ending=!car.next;
   }
   return true;
  });
 }
 assert.deepEqual([...passed].sort((a,b)=>a-b),targetIds,'every formerly stuck car completes its connected route without reset or teleport');
}
replay(false);replay(true);
console.log('Actual Blaak queue clears in both array orders; all five vehicles complete their unchanged connected routes.');
// Explicit clearance and stale-owner tests: a winner crossing the node must not
// release a conflicting merge before its rear clears; removal must release it.
{
 const cars=makeCars(),control=createJunctionArbitrator();
 const leader=cars.find(c=>c.vehicleId===17),crossing=cars.find(c=>c.vehicleId===43);
 control.update(cars,snapshot(cars),.05);
 leader.journeyIndex=1;leader.road=roads.get(600909887);leader.direction=-1;leader.distance=leader.road.length-2;leader.next=null;leader.ending=true;
 assert.equal(control.update(cars,snapshot(cars),.05).get(185274094),leader,'rear still in crossing retains reservation');
 leader.distance=leader.road.length-6;
 assert.notEqual(control.update(cars,snapshot(cars),.05).get(185274094),leader,'rear cleared releases reservation');
 control.clear();
 assert.equal(control.update([crossing],snapshot([crossing]),.05).get(185274094),crossing);
 assert.equal(control.update([],new Map(),.05).size,0,'culled winner cannot leave stale reservation');
}
