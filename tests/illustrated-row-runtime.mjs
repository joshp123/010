// Production GLTFLoader requests and decoded painted images; no GPU art claim.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {createServer} from 'node:http';
import {registerHooks} from 'node:module';
import sharp from 'sharp';
registerHooks({resolve(s,c,next){return next(s==='three'?new URL('../public/vendor/three/build/three.module.js',import.meta.url).href:s,c);}});
globalThis.self=globalThis;globalThis.ProgressEvent=class{constructor(type,init){Object.assign(this,{type},init);}};
globalThis.createImageBitmap=async blob=>{const {data,info}=await sharp(Buffer.from(await blob.arrayBuffer())).raw().toBuffer({resolveWithObject:true});return {width:info.width,height:info.height,data,close(){}};};
const requests=[];const server=createServer(async(req,res)=>{try{assert.ok(req.url.startsWith('/data/illustrated-row/'));const data=await readFile(new URL('../public'+req.url,import.meta.url));requests.push({url:req.url,status:200,bytes:data.length});res.writeHead(200,{'Content-Type':req.url.endsWith('.png')?'image/png':'model/gltf-binary'});res.end(data);}catch(e){requests.push({url:req.url,status:404});res.writeHead(404);res.end();}});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
try{
 const {GLTFLoader}=await import('../public/vendor/three/examples/jsm/loaders/GLTFLoader.js');const gltf=await new GLTFLoader().loadAsync(`http://127.0.0.1:${server.address().port}/data/illustrated-row/row.glb`);const ids=new Set(),maps=new Set();let triangles=0,meshes=0;
 gltf.scene.traverse(mesh=>{if(!mesh.isMesh)return;meshes++;assert.match(mesh.userData.bagId,/^\d{16}$/);ids.add(mesh.userData.bagId);triangles+=mesh.geometry.index.count/3;for(const mat of Array.isArray(mesh.material)?mesh.material:[mesh.material])if(mat.map){maps.add(mat.map);assert.equal(mat.map.image.width,2048);assert.equal(mat.map.image.height,2048);}});
 assert.equal(ids.size,8);assert.equal(triangles,678);assert.equal(maps.size,10);assert.equal(requests.filter(x=>x.url.endsWith('.png')).length,10);assert.ok(requests.every(x=>x.status===200));console.log(JSON.stringify({meshes,triangles,bags:ids.size,paintedTextureMaps:maps.size,requests,scope:'actual GLTFLoader HTTP requests and CPU PNG decode; manager owns GPU visual acceptance'},null,2));
}finally{server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
