import assert from 'node:assert/strict';
import {registerHooks} from 'node:module';
registerHooks({resolve(s,c,next){if(s==='three')return {url:new URL('../public/vendor/three/build/three.module.js',import.meta.url).href,shortCircuit:true};return next(s,c);}});
const THREE=await import('three');
const {publicSpaceClass,preparePublicSpaceGeometry,createPublicSpaceStyle,applyPublicSpaceMaterial}=await import('../public/public-space-style.js');
assert.equal(publicSpaceClass({FYSIEKVK:'open verharding',KLASSE_IMG:'Wegdeel'}),3);
assert.equal(publicSpaceClass({},'road'),0,'a road classification is not evidence of its material');
assert.equal(publicSpaceClass({KLASSE_IMG:'Pand'}),0);
// Two adjacent surveyed squares, independently duplicated vertices. Each has
// one internal triangulation edge; only their shared semantic edge is outlined.
const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute([0,0,0,1,0,0,1,0,1,0,0,1,1,0,0,2,0,0,2,0,1,1,0,1],3));
g.setAttribute('_batchid',new THREE.Float32BufferAttribute([0,0,0,0,1,1,1,1],1));g.setIndex([0,1,2,0,2,3,4,5,6,4,6,7]);
const data=[{KLASSE_IMG:'Wegdeel',FYSIEKVK:'gesloten verharding',FUNCTIE:'rijbaan lokale weg'},{KLASSE_IMG:'Wegdeel',FYSIEKVK:'open verharding',FUNCTIE:'voetpad'}];
const model=new THREE.Group();model.batchTable={getDataFromId:i=>({attributes:data[i]})};const mesh=new THREE.Mesh(g);model.add(mesh);
const old=g.getAttribute('position').array.slice(),indices=g.index.array.slice();const border=preparePublicSpaceGeometry(mesh);
assert.equal(border.userData.sourceBoundarySegments,1);assert.deepEqual(g.getAttribute('position').array,old);assert.deepEqual(g.index.array,indices);assert.equal(border.getAttribute('position').count,6);
for(let i=0;i<6;i++){const p=border.getAttribute('position');assert.ok(p.getX(i)>=.89999&&p.getX(i)<=1.00001);assert.equal(p.getY(i),0);}
const material=new THREE.MeshStandardMaterial();applyPublicSpaceMaterial(material);assert.equal(material.defaultAttributeValues._surfaceClass[0],0);
const geometry2=g.clone();geometry2.userData={};const mesh2=new THREE.Mesh(geometry2);const model2=new THREE.Group();model2.batchTable=model.batchTable;model2.add(mesh2);
const style=createPublicSpaceStyle();style.addModel(model2);assert.equal(style.diagnostics().boundarySegments,1);style.addModel(model2);assert.equal(style.diagnostics().boundarySegments,1);style.removeModel(model2);assert.equal(mesh2.children.length,0);style.dispose();
console.log('Public-space source semantics, shared boundary only, exact retained coordinates/index, bounded seam and reversible lifecycle passed.');
