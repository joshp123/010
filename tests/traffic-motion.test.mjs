import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { gunzipSync } from 'node:zlib';
import { rightHandOffset, turnWeight, safeStep, speedForRoadClass } from '../public/traffic-motion.js';
import * as THREE from '../public/vendor/three/build/three.module.js';
const source = (await readFile(new URL('../public/simulated-traffic.js', import.meta.url), 'utf8'))
  .replace("'three'", JSON.stringify(new URL('../public/vendor/three/build/three.module.js', import.meta.url).href))
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
assert.equal(network.roads.length,27218);
const actual = createSimulatedTraffic({project:(lat,lon)=>new THREE.Vector3((lon-4.49)*68600,0,(51.915-lat)*111300)});
actual.setRoads(network);
for(let i=0;i<200;i++) actual.advance(i/30);
for (const mesh of actual.group.children) assert.ok(mesh.instanceMatrix.array.every(Number.isFinite));
console.log(`Traffic motion checks passed; ${network.roads.length} retained roads; ${actual.statistics().cars} vehicles after 200 updates.`);
actual.dispose();
