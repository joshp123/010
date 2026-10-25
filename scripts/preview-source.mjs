// Written by AI on 2026-10-24 by model GPT-6. Local source preview.
import http from 'node:http';
import {readFile,stat} from 'node:fs/promises';
import path from 'node:path';
import {createTransitProxy} from '../source-tools/transit-worker.js';
import {createLocalMunicipalDelivery} from '../source-tools/municipal-delivery-local.mjs';
const root=path.resolve('public'); const transit=createTransitProxy();
const municipal=await createLocalMunicipalDelivery('/Users/josh/code/010-municipal-delivery/central-256/release',{remote:true});
const types={'.html':'text/html','.js':'text/javascript','.css':'text/css','.json':'application/json','.png':'image/png','.jpg':'image/jpeg','.glb':'model/gltf-binary','.wasm':'application/wasm'};
http.createServer(async(req,res)=>{try{const url=new URL(req.url,'http://localhost:8785');const response=await municipal(new Request(url))??await transit(new Request(url));if(response){res.writeHead(response.status,Object.fromEntries(response.headers));res.end(Buffer.from(await response.arrayBuffer()));return;}let file=path.resolve(root,'.'+decodeURIComponent(url.pathname));if(!file.startsWith(root+'/')&&file!==root){res.writeHead(403);res.end();return;}if((await stat(file)).isDirectory())file=path.join(file,'index.html');const bytes=await readFile(file);res.writeHead(200,{'Content-Type':types[path.extname(file)]||'application/octet-stream','Cache-Control':'no-cache'});res.end(bytes);}catch(e){res.writeHead(e.code==='ENOENT'?404:500);res.end(e.message);}}).listen(8785,'127.0.0.1',()=>console.log('Internal source preview http://localhost:8785'));
