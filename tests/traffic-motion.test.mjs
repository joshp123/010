import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { gunzipSync } from 'node:zlib';
import { rightHandOffset, turnWeight, safeStep, speedForRoadClass } from '../public/traffic-motion.js';
import * as THREE from '../public/vendor/three/build/three.module.js';
const source = (await readFile(new URL('../public/simulated-traffic.js', import.meta.url), 'utf8'))
  .replace("'three'", JSON.stringify(new URL('../public/vendor/three/build/three.module.js', import.meta.url).href))
  .replace("'./traffic-journeys.js'", JSON.stringify(new URL('../public/traffic-journeys.js', import.meta.url).href))
  .replace("'./traffic-motion.js'", JSON.stringify(new URL('../public/traffic-motion.js', import.meta.url).href));
const { createSimulatedTraffic, decodeTrafficRoads } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
assert.deepEqual(rightHandOffset(1, 0, 1, 50, 100, true), [-0, 1.15]);
assert.deepEqual(rightHandOffset(1, 0, -1, 50, 100, true), [0, -1.15]);
assert.equal(Math.hypot(...rightHandOffset(1, 0, 1, 0, 100, true)), 0, 'junction offsets meet continuously');
assert.equal(turnWeight([1, 0], [-1, 0]), 0, 'different-edge reversal forbidden');
assert.ok(turnWeight([1, 0], [1, 0]) > turnWeight([1, 0], [0, 1]));
assert.equal(safeStep(60), .1, 'suspended frame must not jump a minute');
assert.equal(speedForRoadClass('HR'), 7, 'HR must not imply motorway speed');

let height = 0;
const traffic = createSimulatedTraffic({ project: (lat, lon) => new THREE.Vector3(lon, height, lat), maximumVehicles: 20, vehiclesPerKilometre: 20 });
traffic.setRoads({ version: 1, roads: [
  {id:1,start:1,end:2,direction:3,roadClass:'HR',coordinates:[[0,0],[1000,0]]},
  {id:2,start:2,end:3,direction:3,roadClass:'HR',coordinates:[[1000,0],[2000,0]]},
]});
traffic.advance(0); traffic.advance(.1);
const before = traffic.group.children[0].instanceMatrix.array.slice();
const beforeCount = traffic.group.children[0].count;
height = 5; traffic.refreshProjection();
const after = traffic.group.children[0].instanceMatrix.array;
for(let i=0;i<beforeCount;i++) {
  assert.equal(after[i*16+12], before[i*16+12], 'reprojection preserves longitudinal position');
  assert.equal(after[i*16+14], before[i*16+14], 'reprojection preserves lane');
  assert.ok(Math.abs(after[i*16+13] - before[i*16+13] - 5)<1e-5);
}
const beforePause = traffic.group.children[0].instanceMatrix.array.slice();
traffic.setPaused(true); traffic.advance(100); traffic.setPaused(false); traffic.advance(101);
assert.deepEqual(traffic.group.children[0].instanceMatrix.array, beforePause, 'pause/resume does not catch up');
traffic.dispose();

const network = decodeTrafficRoads(gunzipSync(await readFile(new URL('../public/data/traffic/roads.pb.gz',import.meta.url))));
assert.ok(network.roads.length > 27218, 'short surveyed junction connectors must survive preparation');
const actual = createSimulatedTraffic({project:(lat,lon)=>new THREE.Vector3((lon-4.49)*68600,0,(51.915-lat)*111300)});
actual.setRoads(network);
for(let i=0;i<200;i++) actual.advance(i/30);
for (const mesh of actual.group.children) assert.ok(mesh.instanceMatrix.array.every(Number.isFinite));
console.log(`Traffic motion checks passed; ${network.roads.length} retained roads; ${actual.statistics().cars} vehicles after 200 updates.`);
actual.dispose();

const cyclists = createSimulatedTraffic({ bicycles:true,project:(lat,lon)=>new THREE.Vector3(lon,0,lat),maximumVehicles:8,vehiclesPerKilometre:20 });
cyclists.setRoads({version:1,roads:[{id:1,start:1,end:2,direction:3,roadClass:'FP',coordinates:[[0,0],[400,0]]},{id:2,start:2,end:3,direction:3,roadClass:'FP',coordinates:[[400,0],[800,0]]}]});
for(let i=0;i<100;i++) cyclists.advance(i/30);
assert.equal(cyclists.statistics().cars,0,'riders must not be counted as cars');
assert.equal(cyclists.statistics().cyclists,8);
assert.equal(cyclists.group.children.find(m=>m.name==='Bicycle wheels').count,16);
for(const mesh of cyclists.group.children) assert.ok(mesh.instanceMatrix.array.every(Number.isFinite));
cyclists.dispose();

const cycleNetwork = decodeTrafficRoads(gunzipSync(await readFile(new URL('../public/data/traffic/cycleways.pb.gz',import.meta.url))));
assert.ok(cycleNetwork.roads.length > 7000);
assert.ok(cycleNetwork.roads.every(road=>road.roadClass==='FP'), 'cycle simulation must not fall back to motor roads');
for(const [name,lon,lat] of [['centre',4.48,51.92],['Hoek',4.13,51.98],['Maasvlakte',4.01,51.96]]) {
  assert.ok(cycleNetwork.roads.some(road=>road.coordinates.some(point=>Math.abs(point[0]-lon)<.025 && Math.abs(point[1]-lat)<.025)), `${name}: retained FP coverage`);
}
console.log(`Cycling graph checks passed: ${cycleNetwork.roads.length} dedicated FP pieces across centre, Hoek and Maasvlakte.`);
