// Optional same-origin adapter for the Sites backend. Create once at module
// scope, then call handle(request); null means this handler does not own the URL.
// Cached bytes retain upstream observation/publication timestamps unchanged.
export function createTransitProxy({ fetch: fetchSource = globalThis.fetch.bind(globalThis), now = Date.now } = {}) {
  const feeds = {
    '/api/transit/vehicles': { name: 'ndov', url: 'https://gtfs.ovapi.nl/nl/vehiclePositions.pb', type: 'application/x-protobuf', interval: 15000 },
    '/api/transit/ns': { name: 'ns', url: 'https://treinen.ai-tigers.com/v1/trains?bbox=51.84,3.94,52.01,4.61', type: 'application/json', interval: 15000 },
  };

  async function update(feed) {
    const checkedAt = now();
    const headers = { 'User-Agent': '010 Rotterdam miniature https://010.jjpcodes.com @jjpcodes', 'Accept-Encoding': 'gzip' };
    if (feed.etag) headers['If-None-Match'] = feed.etag;
    if (feed.lastModified) headers['If-Modified-Since'] = feed.lastModified;
    const response = await fetchSource(feed.url, { headers, signal: AbortSignal.timeout(8000) });
    if (response.status !== 304) {
      if (!response.ok) throw new Error(`Upstream HTTP ${response.status}`);
      feed.bytes = new Uint8Array(await response.arrayBuffer());
      feed.etag = response.headers.get('etag'); feed.lastModified = response.headers.get('last-modified');
    }
    if (!feed.bytes) throw new Error('Upstream returned no initial data');
    feed.fetchedAt = now();
    feed.nextUpdateAt = checkedAt + feed.interval;
  }

  return async function handle(request) {
    const feed = feeds[new URL(request.url).pathname];
    if (!feed) return null;
    if (request.method !== 'GET') return new Response('Method not allowed', { status: 405, headers: { Allow: 'GET' } });
    try {
      if (!feed.bytes || now() >= feed.nextUpdateAt) {
        // Worker I/O belongs to this request. Reusing an unfinished fetch from
        // a cancelled earlier request can leave every later refresh waiting.
        await update(feed);
      }
      return new Response(feed.bytes, { headers: { 'Content-Type': feed.type, 'Cache-Control': 'no-store', 'X-Transit-Source': feed.name, 'X-Transit-Fetched-At': new Date(feed.fetchedAt).toISOString() } });
    } catch (error) {
      return new Response(JSON.stringify({ source: feed.name, error: error.message }), { status: 502, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' } });
    }
  };
}
