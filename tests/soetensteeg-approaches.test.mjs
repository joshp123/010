import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import * as THREE from '../public/vendor/three/build/three.module.js';
const source=await readFile(new URL('../public/source-fusion.js',import.meta.url),'utf8');
const {createSourceFusion}=await import(`data:text/javascript;base64,${Buffer.from(source.replace("'three'",JSON.stringify(new URL('../public/vendor/three/build/three.module.js',import.meta.url).href))).toString('base64')}`);
const data=JSON.parse(await readFile(new URL('../public/data/ground-corrections/soetensteeg.json',import.meta.url)));
assert.equal(data.triangles.length,5);
assert.deepEqual([...new Set(data.triangles.map(p=>p.featureId))].sort(),['15486948','16299950']);
const position=[],batch=[],indices=[];
for(const patch of data.triangles){const first=position.length/3;for(const point of patch.expectedWorldPositions){position.push(...point);batch.push(patch.featureId==='16299950'?0:1);}indices.push(first,first+1,first+2);}
// An adjacent quay wall shares two native vertices with the corrected footway.
const last=position.length/3;position.push(position[0],-1.2,position[2]+.5);batch.push(0);indices.push(0,1,last);
const pierFirst=position.length/3;position.push(-485,-1.23,-460,-484,-1.23,-460,-485,-1.23,-459);batch.push(2,2,2);indices.push(pierFirst,pierFirst+1,pierFirst+2);
const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(position,3));geometry.setAttribute('_batchid',new THREE.Float32BufferAttribute(batch,1));geometry.setAttribute('normal',new THREE.Float32BufferAttribute(position.map((_,i)=>+(i%3===1)),3));geometry.setIndex(indices);
const mesh=new THREE.Mesh(geometry),group=new THREE.Group();group.add(mesh);group.batchTable={getDataFromId:id=>({attributes:{DGDT_ID:['16299950','15486948','16063621'][id],KLASSE_IMG:id===2?'Overbruggingsdeel':'Wegdeel',FYSIEKVK:'open verharding'}})};
const fusion=createSourceFusion();fusion.addGround(group);fusion.update();assert.equal(mesh.geometry,geometry);
fusion.setGroundCorrections(data);fusion.update();assert.equal(fusion.getDiagnostics().correctedApproachTriangles,5);assert.equal(mesh.geometry.index.count,indices.length);
const output=mesh.geometry,points=output.getAttribute('position');
for(let t=0;t<5;t++)for(let c=0;c<3;c++){
 const j=output.index.getX(t*3+c),expected=data.triangles[t];assert.ok(j>=position.length/3,'corrected vertices must be independent');assert.ok(Math.abs(points.getY(j)-expected.replacementWorldY[c])<1e-5);assert.ok(Math.abs(points.getX(j)-expected.expectedWorldPositions[c][0])<.0001);assert.ok(Math.abs(points.getZ(j)-expected.expectedWorldPositions[c][2])<.0001);
}
assert.deepEqual(Array.from(output.index.array).slice(15),indices.slice(15),'quay wall and registered pier retain original indices');
assert.deepEqual(Array.from(points.array).slice(0,position.length),Array.from(geometry.getAttribute('position').array),'all shared native vertices retained unchanged');
assert.equal(fusion.update(),false,'no per-frame geometry churn');
fusion.setGroundCorrections({...data,triangles:[]});fusion.update();assert.equal(mesh.geometry,geometry,'disabling restores retained original');
const wrong=structuredClone(data);for(const patch of wrong.triangles)patch.expectedWorldPositions[0][0]+=.1;fusion.setGroundCorrections(wrong);fusion.update();assert.equal(mesh.geometry,geometry,'changed source coordinates must reject correction');
fusion.dispose();console.log('PASS: five actual-source triangles corrected; shared quay vertices, registered pier, source-coordinate guard and restore preserved');
