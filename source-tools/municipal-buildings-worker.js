// Written by AI on 2026-10-24 by model GPT-6 Astra.
// Same-origin delivery of one public municipal 3D Tiles source. Relative tile
// links resolve beneath this prefix, including the source's nested tilesets.
export const MUNICIPAL_BUILDINGS_PATH = '/api/municipal-buildings/';
const SOURCE = 'https://www.3drotterdam.nl/datasource-data/3adbe5af-d05c-475a-b34c-59e69ba8dadc/';

export function createMunicipalBuildingsProxy({ fetch: fetchSource = globalThis.fetch.bind(globalThis) } = {}) {
  return async function handle(request) {
    const url = new URL(request.url);
    if (!url.pathname.startsWith(MUNICIPAL_BUILDINGS_PATH)) return null;
    if (!['GET', 'HEAD'].includes(request.method)) return new Response('Method not allowed', { status: 405, headers: { Allow: 'GET, HEAD' } });
    const path = url.pathname.slice(MUNICIPAL_BUILDINGS_PATH.length);
    if (url.search || !/^(tileset\.json|\d+\/\d+\/\d+\.(json|b3dm))$/.test(path)) return new Response('Unknown municipal tile', { status: 404 });
    try {
      const upstream = await fetchSource(SOURCE + path, { signal: AbortSignal.timeout(30000), cf: { cacheEverything: true, cacheTtl: 3600 } });
      if (!upstream.ok) return new Response('Municipal tile unavailable', { status: upstream.status === 404 ? 404 : 502 });
      // Fetch implementations differ in whether Content-Encoding survives
      // automatic decoding. Inspect bytes, then deliver one unambiguous body.
      let bytes = new Uint8Array(await upstream.arrayBuffer());
      if (bytes[0] === 31 && bytes[1] === 139) bytes = new Uint8Array(await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer());
      const headers = new Headers({ 'Content-Type': path.endsWith('.json') ? 'application/json' : 'application/octet-stream', 'Cache-Control': 'public, max-age=3600', 'Content-Length': String(bytes.byteLength) });
      for (const name of ['ETag', 'Last-Modified']) if (upstream.headers.has(name)) headers.set(name, upstream.headers.get(name));
      return new Response(request.method === 'HEAD' ? null : bytes, { headers });
    } catch {
      return new Response('Municipal source unavailable', { status: 502, headers: { 'Cache-Control': 'no-store' } });
    }
  };
}
