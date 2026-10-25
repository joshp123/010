// Written by AI on 2026-10-26 by model Claude Opus 5.5.
// Sites serves every file with max-age=0, so without this a returning visitor
// re-asks the server about every tile. Tiles and code are immutable within a
// deploy: serve them from a cache named after the deploy, and drop older
// caches when a new deploy's worker takes over. Pages always come from the network.
const CACHE = 'miniature-__BUILD__';
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => {
  event.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== location.origin) return;
  if (!/\/(pyramids|scene|compare|miniature)\/|\.(js|css|webp|jpg)$/.test(url.pathname) || url.pathname.endsWith('/sw.js')) return;
  event.respondWith(caches.open(CACHE).then(async (cache) => {
    const cached = await cache.match(event.request);
    if (cached) return cached;
    const response = await fetch(event.request);
    if (response.ok) cache.put(event.request, response.clone());
    return response;
  }));
});
