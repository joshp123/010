// Retained-source CPU geometry export; no screenshot simulation claim.
import fs from 'node:fs';
import {registerHooks} from 'node:module';
import {execFileSync} from 'node:child_process';
registerHooks({resolve(s,c,next){if(s==='three')return {url:new URL('../public/vendor/three/build/three.module.js',import.meta.url).href,shortCircuit:true};return next(s,c);}});
const THREE=await import('three');
const {preparePublicSpaceGeometry}=await import('../public/public-space-style.js');
const {featureColor}=await import('../public/miniature-style.js');
const {createCrownGeometry}=await import('../public/vegetation-style.js');
const baseline=execFileSync('git',['show','8ea60494c9ae362db750df3cfbef6dbd5f57679d:public/vegetation-style.js'],{encoding:'utf8'}).replace("'three'",JSON.stringify(new URL('../public/vendor/three/build/three.module.js',import.meta.url).href));
const before=await import(`data:text/javascript;base64,${Buffer.from(baseline).toString('base64')}`);
const input=JSON.parse(fs.readFileSync(process.argv[2]));
const output={ground:[],trees:[]};
for(const item of input.meshes){
 const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(item.positions,3));geometry.setAttribute('_batchid',new THREE.Float32BufferAttribute(item.batch,1));geometry.setIndex(item.indices);
 const colors=[];for(const id of item.batch)colors.push(...featureColor('ground',input.attributes[id],id).toArray());geometry.setAttribute('color',new THREE.Float32BufferAttribute(colors,3));
 const model=new THREE.Group();model.batchTable={getDataFromId:id=>({attributes:input.attributes[id]})};const mesh=new THREE.Mesh(geometry);model.add(mesh);
 const boundary=preparePublicSpaceGeometry(mesh);
 output.ground.push({...item,colors,classes:Array.from(geometry.getAttribute('_surfaceClass').array),boundaries:boundary?Array.from(boundary.getAttribute('position').array):[],boundaryColors:boundary?Array.from(boundary.getAttribute('color').array):[]});
}
for(const name of ['proto_6','proto_7']){
 const data=JSON.parse(fs.readFileSync(new URL(`../source-data/vegetation-style/${name}-positions.json`,import.meta.url)));const original=new THREE.BufferGeometry();original.setAttribute('position',new THREE.Float32BufferAttribute(data.positions,3));
 for(const [label,fn] of [['before',before.createCrownGeometry],['after',createCrownGeometry]]){const geometry=fn(original);output.trees.push({name,label,positions:Array.from(geometry.getAttribute('position').array),colors:Array.from(geometry.getAttribute('color').array)});}
}
fs.writeFileSync(process.argv[3],JSON.stringify(output));
