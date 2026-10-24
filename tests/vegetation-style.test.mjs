import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import * as THREE from '../public/vendor/three/build/three.module.js';
const source = (await readFile(new URL('../public/vegetation-style.js', import.meta.url), 'utf8'))
  .replace("'three'", JSON.stringify(new URL('../public/vendor/three/build/three.module.js', import.meta.url).href));
const { createCrownGeometry, createVegetationStyle } = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const load = async name => {
  const data=JSON.parse(await readFile(new URL(`../source-data/vegetation-style/${name}-positions.json`,import.meta.url),'utf8'));
  const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(data.positions,3));geometry.computeBoundingBox();return geometry;
};
const original=await load('proto_6'), narrow=await load('proto_7'), trunk=await load('proto_2');
for(const source of [original,narrow]) {
  const before=source.getAttribute('position').array.slice();
  const a=createCrownGeometry(source),b=createCrownGeometry(source);
  assert.deepEqual(a.getAttribute('position').array,b.getAttribute('position').array,'interpretation must be deterministic');
  assert.deepEqual(source.getAttribute('position').array,before,'never mutate retained original vertices');
  for(const endpoint of ['min','max']) for(const axis of ['x','y','z']) assert.ok(Math.abs(a.boundingBox[endpoint][axis]-source.boundingBox[endpoint][axis])<1e-6,'source envelope must be retained');
  assert.ok(a.getAttribute('position').array.every(Number.isFinite));
  const colors=a.getAttribute('color').array;
  assert.ok(new Set(Array.from(colors)).size>3,'crown lobes must carry distinct flat palette regions');
}
const model=new THREE.Group();const crownGroup=new THREE.Group();crownGroup.batchTable={getDataFromId:()=>({attributes:{tree_part:'kruin'}})};model.add(crownGroup);
const trunkGroup=new THREE.Group();trunkGroup.batchTable={getDataFromId:()=>({attributes:{tree_part:'stam'}})};model.add(trunkGroup);
const crownMesh=new THREE.InstancedMesh(original,new THREE.MeshStandardMaterial(),2),trunkMesh=new THREE.InstancedMesh(trunk,new THREE.MeshStandardMaterial(),2);
crownMesh.setMatrixAt(0,new THREE.Matrix4().makeScale(12,20,12));crownMesh.setMatrixAt(1,new THREE.Matrix4().makeTranslation(10,4,2));crownGroup.add(crownMesh);trunkGroup.add(trunkMesh);
const matrices=crownMesh.instanceMatrix.array.slice();const style=createVegetationStyle();style.addModel(model);
assert.deepEqual(crownMesh.instanceMatrix.array,matrices,'inventory placement, orientation and physical dimensions must not change');
assert.notEqual(crownMesh.geometry,original);assert.notEqual(trunkMesh.geometry,trunk);
const c=trunkMesh.geometry.getAttribute('color');assert.ok(c.getX(0)>c.getY(0)&&c.getY(0)>c.getZ(0),'trunk uses brown rather than canopy green');
style.removeModel(model);assert.equal(crownMesh.geometry,original);assert.equal(trunkMesh.geometry,trunk);assert.equal(style.diagnostics().interpretedPrototypes,0);
console.log('Vegetation: retained source crown bounds, deterministic clumps, unchanged source/instance transforms, brown trunks, reversible lifecycle passed.');
