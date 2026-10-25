// Written by AI on 2026-10-25 by model GPT-6 Astra.
// Reversible whole-city comparison; the normal preview remains unchanged.
import http from 'node:http';
import { readFile } from 'node:fs/promises';
const source = new URL('../source-data/vegetation-drawing/', import.meta.url);
http.createServer(async (request, response) => {
  try {
    const path = new URL(request.url, 'http://localhost:8788').pathname;
    const file = path === '/crown-structured-contours.js' ? 'crown-structured-contours.js' : path === '/vegetation-style.js' ? 'vegetation-structured.candidate.js' : null;
    if (file) {
      response.writeHead(200, { 'Content-Type': 'text/javascript', 'Cache-Control': 'no-store' });
      response.end(await readFile(new URL(file, source)));
      return;
    }
    const upstream = await fetch('http://localhost:8785' + request.url);
    response.writeHead(upstream.status, Object.fromEntries(upstream.headers));
    response.end(Buffer.from(await upstream.arrayBuffer()));
  } catch (error) {
    response.writeHead(500);
    response.end(String(error));
  }
}).listen(8788, '127.0.0.1', () => console.log('Connected crown comparison http://localhost:8788'));
