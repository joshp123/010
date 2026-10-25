// Written by AI on2026-10-25 by modelGPT-6Astra.
// One reversible whole-city comparison against the unchanged main preview.
import http from 'node:http';
import {readFile} from 'node:fs/promises';
const source=new URL('../source-data/vegetation-drawing/',import.meta.url);
const files={'/vegetation-style.js':'vegetation-isometric.candidate.js','/crown-isometric-hull.js':'crown-isometric-hull.js','/data/vegetation-drawing/crown-fields.png':'isometric-pigment-extended.png'};
http.createServer(async(request,response)=>{
 try {
  const path=new URL(request.url,'http://localhost:8788').pathname;
  if(path==='/object-detail.js'){
   const raw=await readFile(new URL('../public/object-detail.js',import.meta.url),'utf8');
   response.writeHead(200,{'Content-Type':'text/javascript','Cache-Control':'no-store'});
   response.end(raw.replace('if (!fullDetail) {','if (!fullDetail && !record.source.userData.preserveTextureProjection) {'));return;
  }
  const file=files[path];
  if(file){response.writeHead(200,{'Content-Type':file.endsWith('.png')?'image/png':'text/javascript','Cache-Control':'no-store'});response.end(await readFile(new URL(file,source)));return;}
  const upstream=await fetch('http://localhost:8785'+request.url);response.writeHead(upstream.status,Object.fromEntries(upstream.headers));response.end(Buffer.from(await upstream.arrayBuffer()));
 }catch(error){response.writeHead(500);response.end(String(error));}
}).listen(8788,'127.0.0.1');
