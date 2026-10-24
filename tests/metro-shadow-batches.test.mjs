import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import * as THREE from '../public/vendor/three/build/three.module.js';
async function load(name) {
 const code=(await readFile(new URL(`../public/${name}.js`,import.meta.url),'utf8')).replace("'three'",JSON.stringify(new URL('../public/vendor/three/build/three.module.js',import.meta.url).href));
 return import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
}
const {createBuildingBatches}=await load('building-batches');
const {createTreeBatches}=await load('tree-batches');
const material=new THREE.MeshBasicMaterial(), clippedDepth=new THREE.MeshDepthMaterial();
const model=new THREE.Group();
for(let i=0;i<2;i++) {
 const mesh=new THREE.Mesh(new THREE.BoxGeometry().toNonIndexed(),material);
 mesh.geometry.clearGroups();mesh.castShadow=true;mesh.customDepthMaterial=clippedDepth;model.add(mesh);
}
const buildings=createBuildingBatches();buildings.addModel(model);
assert.equal(model.children.length,1);assert.equal(model.children[0].customDepthMaterial,clippedDepth,'merged buildings keep the same cutaway depth shader');
buildings.dispose();assert.equal(model.children.length,2);
const treeScene=new THREE.Scene(),treeModel=new THREE.Group();
const tree=new THREE.InstancedMesh(new THREE.BoxGeometry(),material,2);tree.castShadow=true;tree.customDepthMaterial=clippedDepth;treeModel.add(tree);
const trees=createTreeBatches(treeScene);trees.addModel(treeModel);trees.update(new Set([treeModel]));
assert.ok(treeScene.children.some(mesh=>mesh.isInstancedMesh&&mesh.customDepthMaterial===clippedDepth),'instanced tree batches retain cutaway depth shader');
trees.dispose();material.dispose();clippedDepth.dispose();
console.log('Cutaway shadow material survives building and tree batching.');
