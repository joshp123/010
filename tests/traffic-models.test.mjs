import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import * as THREE from '../public/vendor/three/build/three.module.js';
const source=(await readFile(new URL('../public/traffic-models.js',import.meta.url),'utf8')).replace("'three'",JSON.stringify(new URL('../public/vendor/three/build/three.module.js',import.meta.url).href));
const {createCarGeometries,createBicycleGeometries}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
for(const [name,models] of [['car',createCarGeometries()],['bicycle',createBicycleGeometries()]]) {
 let triangles=0;
 for(const geometry of Object.values(models)) {
  assert.ok(geometry.attributes.position.array.every(Number.isFinite));
  assert.ok(geometry.attributes.normal.array.every(Number.isFinite));
  triangles+=(geometry.index?.count||geometry.attributes.position.count)/3;
 }
 assert.ok(triangles<1500,'modest shared mesh complexity');
 console.log(`${name}: ${triangles} shared model triangles`);
 if(name==='car') {
  const box=new THREE.Box3();for(const g of Object.values(models)){g.computeBoundingBox();box.union(g.boundingBox);}
  const size=box.getSize(new THREE.Vector3());assert.ok(size.x<1.95&&size.y<1.55&&size.z<4.31,'full model stays city-car size including trim');assert.ok(Math.abs(box.min.y)<1e-6,'tyres meet model ground');
  const mesh=new THREE.Mesh(models.glass,new THREE.MeshBasicMaterial());mesh.updateMatrixWorld();
  assert.ok(new THREE.Raycaster(new THREE.Vector3(0,3,0),new THREE.Vector3(0,-1,0)).intersectObject(mesh).length,'cabin roof faces outward');
 }
 for(const g of Object.values(models))g.dispose();
}
