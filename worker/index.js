// Written by AI on 2026-10-26 by model GPT-6. Pyramid tile serving added by
// Claude Opus 5.5 on 2026-10-26.
import { createLiveFeed } from './live.js';
const live = createLiveFeed();
const BUILD = globalThis.SITE_BUILD ?? 'dev';

// Pyramid tiles are stored 4 x 4 to a pack (tools/pack-tiles.py). Serve the
// original tile URL from its pack, cached at the edge per deploy.
async function pyramidTile(request, env, ctx, match) {
  const [, base, column, row] = match;
  const cacheKey = new Request(`${new URL(request.url).origin}/__tile/${BUILD}${new URL(request.url).pathname}`);
  const cache = caches.default;
  const hit = await cache.match(cacheKey);
  if (hit) return hit;
  const c = Number(column), r = Number(row);
  const pack = await env.ASSETS.fetch(new Request(new URL(`${base}/p${c >> 2}_${r >> 2}.pack`, request.url)));
  if (!pack.ok) return env.ASSETS.fetch(request); // not packed (local development)
  const bytes = new Uint8Array(await pack.arrayBuffer());
  const view = new DataView(bytes.buffer);
  const i = (r & 3) * 4 + (c & 3);
  const offset = view.getUint32(8 + i * 8, true), length = view.getUint32(12 + i * 8, true);
  if (!length) return new Response('Not found', { status: 404 });
  const response = new Response(bytes.slice(offset, offset + length), {
    headers: { 'Content-Type': 'image/webp', 'Cache-Control': 'public, max-age=604800' },
  });
  ctx.waitUntil(cache.put(cacheKey, response.clone()));
  return response;
}

export default {
  fetch(request, env, ctx) {
    const path = new URL(request.url).pathname;
    if (path === '/api/live') return live(request);
    const tile = path.match(/^(\/pyramids\/[^/]+\/b\d+\/\d+)\/(\d+)_(\d+)\.webp$/);
    if (tile) return pyramidTile(request, env, ctx, tile);
    return env.ASSETS.fetch(request);
  },
};
