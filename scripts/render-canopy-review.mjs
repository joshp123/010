// Export actual source/candidate geometry for the CPU review; no scene substitute.
import fs from 'node:fs/promises';import zlib from 'node:zlib';import {execFileSync} from 'node:child_process';
await fs.mkdir('work/canopy-review',{recursive:true});
import * as THREE from '../public/vendor/three/build/three.module.js';
const glb=zlib.gunzipSync(await fs.readFile('source-data/vegetation-style/proto_8.glb.gz'));
const jsonLength=glb.readUInt32LE(12),doc=JSON.parse(glb.subarray(20,20+jsonLength).toString());
const bin=glb.subarray(28+jsonLength),accessor=doc.accessors[doc.meshes[0].primitives[0].attributes.POSITION],view=doc.bufferViews[accessor.bufferView];
const points=[];for(let i=0;i<accessor.count;i++)for(let j=0;j<3;j++)points.push(bin.readFloatLE((view.byteOffset||0)+(accessor.byteOffset||0)+i*(view.byteStride||12)+j*4));
const source=new THREE.BufferGeometry();source.setAttribute('position',new THREE.Float32BufferAttribute(points,3));
const outputs=[];
for(const [name,file] of [['before','work/canopy-review/before.mjs'],['candidate','public/vegetation-style.js']]) {
 const code=(name==='before' ? execFileSync('git',['show','06279703d4e40e3b829bdc5424e8a28bb5d963a4:public/vegetation-style.js'],{encoding:'utf8'}) : await fs.readFile(file,'utf8')).replace("'three'",JSON.stringify(new URL('../public/vendor/three/build/three.module.js',import.meta.url).href));
 const {createCrownGeometry}=await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
 const geometry=createCrownGeometry(source);outputs.push({name,positions:Array.from(geometry.attributes.position.array),colors:Array.from(geometry.attributes.color.array)});
}
await fs.writeFile('work/canopy-review/geometry.json',JSON.stringify(outputs));
