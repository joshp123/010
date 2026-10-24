// Actual production GLTFLoader parse + local-server requests; no GPU claims.
import assert from 'node:assert/strict';
import {registerHooks} from 'node:module';
import sharp from 'sharp';
import {spawn} from 'node:child_process';
let server;
if(process.argv.includes('--start-built-server')){
 server=spawn(process.execPath,['--import','./scripts/sites-env.mjs','./node_modules/wrangler/bin/wrangler.js','dev','--config','dist/server/wrangler.json','--local','--persist-to','.wrangler/state','--ip','127.0.0.1','--inspector-port','0','--port','8795'],{cwd:new URL('..',import.meta.url),stdio:['ignore','pipe','pipe']});
 process.on('exit',()=>server.kill('SIGTERM'));
 await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('Wrangler did not become ready')),60000);const handle=b=>{const text=b.toString();if(text.includes('Ready on')){clearTimeout(timer);console.log(text.trim());resolve();}};server.stdout.on('data',handle);server.stderr.on('data',handle);server.on('exit',code=>{clearTimeout(timer);reject(new Error('Wrangler exited '+code));});});
 process.env.APPEARANCE_TEST_ORIGIN='http://127.0.0.1:8795';
}
registerHooks({resolve(specifier,context,next){return next(specifier==='three'?new URL('../public/vendor/three/build/three.module.js',import.meta.url).href:specifier,context);}});
const base=process.env.APPEARANCE_TEST_ORIGIN||'http://127.0.0.1:8794';
const uri=base+'/data/current-building-appearance/18-268679-55479-0-bag0599100000753300.glb';
globalThis.location=new URL(base);globalThis.self=globalThis;
globalThis.ProgressEvent=class{constructor(type,init){Object.assign(this,{type},init);}};
// Decode actual downloaded PNG bytes. GPU upload/render remains manager review.
globalThis.createImageBitmap=async blob=>{const buffer=Buffer.from(await blob.arrayBuffer());const {data,info}=await sharp(buffer).raw().toBuffer({resolveWithObject:true});return {width:info.width,height:info.height,data,close(){}};};
const requests=[],originalFetch=globalThis.fetch;
globalThis.fetch=async(input,options)=>{const response=await originalFetch(input,options);requests.push({url:typeof input==='string'?input:input.url||String(input),status:response.status});return response;};
const {createCompressedModelsPlugin}=await import('../public/compressed-models.js');
const plugin=createCompressedModelsPlugin();
assert.equal(plugin.fetchData(uri,{}),null,'appearance currently follows standard GLB path, not gzip/blob interception');
const {GLTFLoader}=await import('../public/vendor/three/examples/jsm/loaders/GLTFLoader.js');
const response=await fetch(uri);assert.equal(response.status,200);const bytes=await response.arrayBuffer();
// 3d-tiles-renderer passes the original model-directory URL as parse resourcePath.
const scene=await new GLTFLoader().parseAsync(bytes,new URL('.',uri).href);
let meshes=0,triangles=0;const maps=new Set();scene.scene.traverse(o=>{if(!o.isMesh)return;meshes++;triangles+=o.geometry.index.count/3;for(const m of Array.isArray(o.material)?o.material:[o.material])if(m.map){assert.ok(m.map.image.width>0&&m.map.image.height>0);maps.add(m.map);}});
const pngs=requests.filter(r=>r.url.endsWith('.png'));assert.equal(pngs.length,23);assert.equal(maps.size,23);assert.equal(triangles,1394);assert.ok(pngs.every(r=>r.status===200&&r.url.startsWith(base+'/data/current-building-appearance/texture-')));assert.ok(!requests.some(r=>r.url.startsWith('blob:')));
console.log(JSON.stringify({meshes,triangles,decodedTextureMaps:maps.size,requests,scope:'Actual production GLTFLoader and compressed-model plugin, served built assets; CPU image decode, not GPU visual acceptance'},null,2));

if(server)server.kill('SIGTERM');
