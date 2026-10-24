// Private, reversible comparison; the normal source preview stays unchanged.
import http from 'node:http';
import { readFile } from 'node:fs/promises';
const source = new URL('../source-data/vegetation-drawing/', import.meta.url);
http.createServer(async (request, response) => {
  try {
    const path = new URL(request.url, 'http://localhost:8787').pathname;
    const file = path === '/vegetation-style.js' ? 'vegetation-style.candidate.js' : path === '/data/vegetation-drawing/crown-fields.png' ? 'model-drawn-six-views.png' : null;
    if (file) {
      response.writeHead(200, { 'Content-Type': file.endsWith('.png') ? 'image/png' : 'text/javascript', 'Cache-Control': 'no-store' });
      response.end(await readFile(new URL(file, source)));
      return;
    }
    if (path === '/object-detail.js') {
      const code = await readFile(new URL('../public/object-detail.js', import.meta.url), 'utf8');
      response.writeHead(200, { 'Content-Type': 'text/javascript', 'Cache-Control': 'no-store' });
      response.end(code.replace('      if (!fullDetail) {\n        const pixelsPerSourceUnit', '      if (!fullDetail && !record.source.userData.preserveTextureProjection) {\n        const pixelsPerSourceUnit'));
      return;
    }
    const upstream = await fetch('http://localhost:8785' + request.url);
    response.writeHead(upstream.status, Object.fromEntries(upstream.headers));
    response.end(Buffer.from(await upstream.arrayBuffer()));
  } catch (error) {
    response.writeHead(500);
    response.end(String(error));
  }
}).listen(8787, '127.0.0.1', () => console.log('Source-bound foliage comparison http://localhost:8787'));
