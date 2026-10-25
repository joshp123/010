// Written by AI on 2026-10-25 by model GPT-6 Astra.
// One exact immutable tile range, never a whole-pack fetch or an image codec.
export function createMunicipalDeliveryProxy({ manifest, fetchAsset = null, cache = null, waitUntil = null }) {
  return async request => {
    const url = new URL(request.url), prefix = '/api/municipal-delivery/';
    if (!url.pathname.startsWith(prefix)) return null;
    if (request.method !== 'GET') return new Response('Method not allowed', { status: 405 });
    const key = url.pathname.slice(prefix.length), tile = manifest.tiles[key];
    if (!tile) return new Response('Source tile not compiled', { status: 404 });
    const cacheKey = new Request(`${url.origin}${prefix}${tile.gzipSha256}.b3dm`);
    const hit = cache ? await cache.match(cacheKey) : null;
    if (hit) return hit;
    const range = `bytes=${tile.offset}-${tile.offset + tile.length - 1}`;
    const assetUrl = manifest.releaseTag ? `https://github.com/joshp123/010/releases/download/${manifest.releaseTag}/${tile.pack}` : null;
    if (!fetchAsset && !assetUrl) return new Response('Derived source is not published', { status: 503 });
    const upstream = await (fetchAsset ? fetchAsset(tile.pack, { headers: { Range: range }, signal: request.signal }) : fetch(assetUrl, { headers: { Range: range }, signal: request.signal }));
    const expected = `bytes ${tile.offset}-${tile.offset + tile.length - 1}/${manifest.packs[tile.pack].bytes}`;
    if (upstream.status !== 206 || upstream.headers.get('Content-Range') !== expected || Number(upstream.headers.get('Content-Length')) !== tile.length) {
      await upstream.body?.cancel();
      return new Response('Derived source range unavailable', { status: 502 });
    }
    const response = new Response(upstream.body, { status: 200, headers: { 'Content-Type': 'application/octet-stream', 'Content-Encoding': 'gzip', 'Content-Length': String(tile.length), 'Cache-Control': 'public,max-age=31536000,immutable', ETag: `"${tile.gzipSha256}"`, 'X-Source-SHA256': tile.sourceSha256 } });
    if (cache) {
      const store = cache.put(cacheKey, response.clone());
      if (waitUntil) waitUntil(store); else await store;
    }
    return response;
  };
}
