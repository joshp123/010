// Written by AI on 2026-10-26 by model GPT-6.
import lookup from '../source-data/transit/worker-lookup.json' with { type: 'json' };
import { decodeVehiclePositions } from '../web/transit-feed.js';
import { rdFromWgs84 } from '../web/miniature/rd.js';

const userAgent = '010 Rotterdam miniature https://010.jjpcodes.com';
const interval = 10_000;
const routeById = new Map(lookup.routes.map((route, index) => [route[0], index]));
const modeByType = new Map([[0, 'tram'], [1, 'metro'], [2, 'train'], [3, 'bus'], [4, 'ferry']]);

function positionInsideBounds(latitude, longitude) {
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return null;
  const { x, y } = rdFromWgs84(latitude, longitude);
  const [minX, minY, maxX, maxY] = lookup.bounds;
  return x >= minX && x <= maxX && y >= minY && y <= maxY
    ? [Math.round(x * 10) / 10, Math.round(y * 10) / 10] : null;
}

function vehicleId(entity, vehicle) {
  const operator = entity.id?.split(':')[1];
  const label = vehicle.vehicle?.id || vehicle.vehicle?.label;
  return label && operator ? `${operator}:${label}` : entity.id;
}

// Shared per warm isolate; Cache API also shares snapshots across warm isolates
// in a Cloudflare location. Neither mechanism is a global cross-region lock.
export function createLiveFeed({ fetchSource = fetch, now = Date.now, cache = () => globalThis.caches?.default } = {}) {
  const sources = [
    { name: 'ovapi', url: 'https://gtfs.ovapi.nl/nl/vehiclePositions.pb' },
    { name: 'ns', url: `https://treinen.ai-tigers.com/v1/trains?bbox=51.8,3.9,52.1,4.7` },
  ];
  let snapshot;
  let nextUpdate = 0;
  let pending;
  let lastError;
  const cacheKey = new Request('https://010.jjpcodes.com/__worker-cache/live-v1');

  async function fetchUpstream(source) {
    const headers = { 'User-Agent': userAgent, 'Accept-Encoding': 'gzip' };
    if (source.lastModified) headers['If-Modified-Since'] = source.lastModified;
    if (source.etag) headers['If-None-Match'] = source.etag;
    console.log(JSON.stringify({ event: 'transit-upstream', source: source.name }));
    const response = await fetchSource(source.url, { headers, signal: AbortSignal.timeout(8000) });
    if (response.status !== 304) {
      if (!response.ok) throw new Error(`${source.name}: HTTP ${response.status}`);
      source.data = source.name === 'ovapi'
        ? decodeVehiclePositions(new Uint8Array(await response.arrayBuffer()))
        : await response.json();
      source.etag = response.headers.get('etag');
      source.lastModified = response.headers.get('last-modified');
      // Sources without validators can still be polled conditionally.
      source.lastModified ||= response.headers.get('date');
    }
    if (!source.data) throw new Error(`${source.name}: no initial data`);
    return source.data;
  }

  async function update() {
    const cached = await cache()?.match(cacheKey);
    if (cached) {
      const shared = await cached.json();
      if (now() < shared.nextUpdate) {
        snapshot = shared.body;
        nextUpdate = shared.nextUpdate;
        return;
      }
    }
    // Failed requests also respect the polling interval.
    nextUpdate = now() + interval;
    const [ovapi, ns] = await Promise.allSettled(sources.map(fetchUpstream));
    if (ovapi.status === 'rejected') throw ovapi.reason;
    if (ovapi.value.header.incrementality === 1) throw new Error('OVapi differential feed unsupported');
    const vehicles = [];
    const lines = [];
    const lineIndices = new Map();
    const headsigns = [];
    const headsignIndices = new Map();
    const unmatched = { ovapi: 0, ns: 0 };
    const seen = new Set();
    function append(id, link, position, bearing, observedAt) {
      const route = lookup.routes[link?.[0]];
      const mode = route ? modeByType.get(route[1]) ?? null : id.startsWith('NS:') ? 'train' : null;
      if (seen.has(id)) return true;
      seen.add(id);
      const line = route?.[2] || null;
      const lineKey = `${mode}:${line}`;
      if (!lineIndices.has(lineKey)) {
        lineIndices.set(lineKey, lines.length);
        lines.push([mode, line]);
      }
      const headsign = lookup.headsigns[link?.[1]] || null;
      if (!headsignIndices.has(headsign)) {
        headsignIndices.set(headsign, headsigns.length);
        headsigns.push(headsign);
      }
      vehicles.push([id, lineIndices.get(lineKey), headsignIndices.get(headsign), ...position,
        Number.isFinite(bearing) ? bearing : null, observedAt ?? null]);
      return !!route;
    }
    for (const entity of ovapi.value.entities) {
      const vehicle = entity.vehicle;
      if (entity.deleted || !vehicle?.position) continue;
      const position = positionInsideBounds(vehicle.position.latitude, vehicle.position.longitude);
      if (!position) continue;
      let link = lookup.trips[vehicle.trip?.id];
      if (!link && routeById.has(vehicle.trip?.routeId)) link = [routeById.get(vehicle.trip.routeId), 0];
      if (!append(vehicleId(entity, vehicle), link, position, vehicle.position.bearing, vehicle.timestamp)) unmatched.ovapi++;
    }
    if (ns.status === 'fulfilled') {
      for (const train of ns.value.trains) {
        const position = positionInsideBounds(train.lat, train.lon);
        if (!position) continue;
        const observedAt = Date.parse(train.observed_at) / 1000;
        if (!append(`NS:${train.train_number}`, lookup.trains[train.train_number], position,
          train.bearing, Number.isFinite(observedAt) ? observedAt : null)) unmatched.ns++;
      }
    }
    const body = {
      feedTimestamp: ovapi.value.header.timestamp ?? null,
      nsFeedTimestamp: ns.status === 'fulfilled' ? Date.parse(ns.value.served_at) / 1000 : null,
      fields: ['id', 'line', 'headsign', 'x', 'y', 'bearing', 'observedAt'],
      lines, headsigns, vehicles, unmatched,
      sources: { ovapi: 'ok', ns: ns.status === 'fulfilled' ? 'ok' : 'unavailable' },
    };
    snapshot = JSON.stringify(body);
    // Keep the envelope private to the edge cache; clients get the compact body.
    await cache()?.put(cacheKey, new Response(JSON.stringify({ body: snapshot, nextUpdate }), {
      headers: { 'Cache-Control': 'public, max-age=10', 'Content-Type': 'application/json' },
    }));
  }

  return async function live(request) {
    if (request.method !== 'GET') return new Response('Method not allowed', { status: 405, headers: { Allow: 'GET' } });
    try {
      if (pending) await pending;
      else if (now() >= nextUpdate) {
        pending = update().then(() => { lastError = null; }, error => { lastError = error; throw error; })
          .finally(() => { pending = null; });
        await pending;
      }
      if (lastError) throw lastError;
      if (!snapshot) throw new Error('Live feed unavailable');
      return new Response(snapshot, { headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Cache-Control': 'public, max-age=5',
      } });
    } catch (error) {
      console.error('transit-error', error.message);
      return Response.json({ error: 'Live feed unavailable' }, { status: 502, headers: { 'Cache-Control': 'no-store' } });
    }
  };
}
