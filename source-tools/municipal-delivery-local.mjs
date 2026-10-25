// Written by AI on 2026-10-25 by model GPT-6 Astra.
// Local adapter for the same fixed pack/range contract used by the Worker.
import { readFile, stat } from 'node:fs/promises';
import { createReadStream } from 'node:fs';
import { Readable } from 'node:stream';
import path from 'node:path';
import { createMunicipalDeliveryProxy } from './municipal-delivery-worker.js';

export async function createLocalMunicipalDelivery(directory, { remote = false } = {}) {
  const root = path.resolve(directory), text = await readFile(path.join(root, 'manifest.json'), 'utf8');
  const manifest = JSON.parse(text);
  const fetchAsset = async (pack, options) => {
    if (!Object.hasOwn(manifest.packs, pack) || path.basename(pack) !== pack) return new Response('Unknown source pack', { status: 404 });
    const match = /^bytes=(\d+)-(\d+)$/.exec(options.headers.Range);
    const start = Number(match[1]), end = Number(match[2]), file = path.join(root, pack), size = (await stat(file)).size;
    return new Response(Readable.toWeb(createReadStream(file, { start, end, signal: options.signal })), { status: 206, headers: { 'Content-Range': `bytes ${start}-${end}/${size}`, 'Content-Length': String(end-start+1) } });
  };
  const proxy = createMunicipalDeliveryProxy({ manifest, fetchAsset: remote ? undefined : fetchAsset });
  return request => new URL(request.url).pathname === '/data/municipal-delivery/manifest.json' ? new Response(text, { headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-cache' } }) : proxy(request);
}
