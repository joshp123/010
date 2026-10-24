import { decodeTransitMap, decodeVehiclePositions, municipalVehicleReports, withinTransitMunicipality } from './transit-feed.js';

const MODES = { 0: 'tram', 1: 'metro', 2: 'train', 3: 'bus', 4: 'ferry' };
const unixTime = () => Date.now() / 1000;
const reportedBearing = value => Number.isFinite(value) && value >= 0 && value <= 360 ? value % 360 : null;
const timestamp = value => {
  if (typeof value === 'number') return Number.isFinite(value) && value > 0 ? value : null;
  const parsed = typeof value === 'string' ? Date.parse(value) / 1000 : NaN;
  return Number.isFinite(parsed) ? parsed : null;
};

// All coordinates remain source reports. This layer neither moves vehicles
// between reports nor interprets the NS bridge's ambiguous speed field.
export function createLiveTransit({
  onUpdate = () => {},
  mapUrl = './data/transit/map.pb.gz',
  vehicleUrl = '/api/transit/vehicles',
  trainUrl = '/api/transit/ns',
  fetch: fetchSource = globalThis.fetch.bind(globalThis),
  now = unixTime,
  maximumAgeSeconds = 90,
  vehicleIntervalSeconds = 15,
  trainIntervalSeconds = 15,
} = {}) {
  let map = null, mapPromise = null, mapError = null, running = false, disposed = false, timer = null;
  const controllers = new Set();
  const sources = {
    ndov: { url: vehicleUrl, interval: vehicleIntervalSeconds, next: 0, pending: null, status: 'idle', reports: [], receivedAt: null, publishedAt: null, error: null },
    ns: { url: trainUrl, interval: trainIntervalSeconds, next: 0, pending: null, status: 'idle', reports: [], receivedAt: null, publishedAt: null, error: null },
  };

  function freshness(observedAt, at) {
    if (observedAt === null) return 'unknown';
    const age = at - observedAt;
    return age < 0 ? 'future' : age > maximumAgeSeconds ? 'stale' : 'fresh';
  }

  function snapshot() {
    const at = now(), vehicles = [], health = {};
    for (const [name, source] of Object.entries(sources)) {
      let freshCount = 0, staleCount = 0;
      for (const report of source.reports) {
        const state = freshness(report.observedAt, at);
        if (state === 'fresh') freshCount++; else staleCount++;
        vehicles.push({ ...report, freshness: state, ageSeconds: report.observedAt === null ? null : at - report.observedAt, sourceConnected: source.status === 'ready' });
      }
      health[name] = { status: source.status, connected: source.status === 'ready', receivedAt: source.receivedAt, publishedAt: source.publishedAt, publicationAgeSeconds: source.publishedAt === null ? null : at - source.publishedAt, publicationFreshness: freshness(source.publishedAt, at), error: source.error, freshCount, staleCount };
    }
    return { updatedAt: at, maximumAgeSeconds, map: { status: map ? 'ready' : mapError ? 'error' : mapPromise ? 'loading' : 'idle', error: mapError }, sources: health, vehicles };
  }

  function emit() { const state = snapshot(); if (!disposed) onUpdate(state); return state; }

  async function request(url, consume) {
    const controller = new AbortController();
    controllers.add(controller);
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetchSource(url, { signal: controller.signal, credentials: 'omit', cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await consume(response);
    } finally { clearTimeout(timeout); controllers.delete(controller); }
  }

  async function loadMap() {
    if (map) return map;
    if (!mapPromise) {
      mapError = null;
      mapPromise = request(mapUrl, async response => {
        let bytes = new Uint8Array(await response.arrayBuffer());
        // Servers may already have applied Content-Encoding: gzip.
        if (bytes[0] === 31 && bytes[1] === 139) bytes = new Uint8Array(await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer());
        return decodeTransitMap(bytes);
      }).then(value => { map = value; return value; }).catch(error => { mapError = error.message; throw error; }).finally(() => { mapPromise = null; });
    }
    return mapPromise;
  }

  function readUrban(bytes) {
    const feed = decodeVehiclePositions(bytes);
    if (!feed.header.version) throw new Error('GTFS-Realtime header is missing');
    // This endpoint is a complete snapshot. Incremental feeds need retained
    // entity state and cannot safely replace the previously observed dataset.
    if (feed.header.incrementality === 1) throw new Error('Incremental vehicle feed is unsupported');
    return {
      publishedAt: timestamp(feed.header.timestamp),
      reports: municipalVehicleReports(feed, map).map(report => ({
        id: `ndov:${report.entityId}`, source: 'ndov', latitude: report.position.latitude, longitude: report.position.longitude,
        bearing: reportedBearing(report.position.bearing), routeShape: report.shape?.lines || null,
        observedAt: timestamp(report.observationTimestamp), positionSource: 'upstream-report',
        mode: MODES[report.route?.type] || 'unknown', routeType: report.route?.type ?? null,
        label: report.route?.shortName || report.route?.longName || null, operator: report.route?.agencyName || null,
        tripId: report.trip?.id || null, routeId: report.route?.id || report.trip?.routeId || null,
        vehicleLabel: report.vehicle?.label || null,
      })),
    };
  }

  function readTrains(feed) {
    if (!Array.isArray(feed.trains) || typeof feed.served_at !== 'string') throw new Error('Invalid NS bridge response');
    const reports = [];
    for (const train of feed.trains) {
      if (!train.train_number || !Number.isFinite(train.lat) || !Number.isFinite(train.lon) || !withinTransitMunicipality(train.lon, train.lat, map.municipality)) continue;
      reports.push({ id: `ns:${train.train_number}`, source: 'ns', latitude: train.lat, longitude: train.lon,
        bearing: reportedBearing(train.bearing),
        observedAt: timestamp(train.observed_at), positionSource: 'upstream-report', reportedFixSource: train.source || null,
        mode: 'train', routeType: 2, label: String(train.train_number), operator: 'NS', tripId: null, routeId: null, vehicleLabel: null });
    }
    return { publishedAt: timestamp(feed.served_at), reports };
  }

  function updateSource(name) {
    const source = sources[name];
    if (source.pending) return source.pending;
    source.next = now() + source.interval;
    // Keep a prior successful connection while refreshing; a failed fetch will
    // explicitly disconnect it without destroying the last observed positions.
    if (source.status !== 'ready') source.status = 'loading';
    source.pending = request(source.url, async response => name === 'ndov' ? readUrban(new Uint8Array(await response.arrayBuffer())) : readTrains(await response.json()))
      .then(result => {
        if (disposed) return;
        source.reports = result.reports; source.publishedAt = result.publishedAt; source.receivedAt = now(); source.status = 'ready'; source.error = null;
      }).catch(error => {
        if (!disposed) { source.status = 'error'; source.error = error.message; }
      }).finally(() => { source.pending = null; emit(); });
    return source.pending;
  }

  async function refresh({ dueOnly = false } = {}) {
    if (disposed) return snapshot();
    try { await loadMap(); } catch { return emit(); }
    if (disposed) return snapshot();
    await Promise.all(Object.keys(sources).filter(name => !dueOnly || now() >= sources[name].next).map(updateSource));
    return emit();
  }

  function tick() {
    if (!running || disposed) return;
    refresh({ dueOnly: true });
    // Freshness continues ageing even when a source disconnects.
    timer = setTimeout(tick, 5000);
  }
  function start() { if (!disposed && !running) { running = true; tick(); } return refresh({ dueOnly: true }); }
  function stop() { running = false; clearTimeout(timer); timer = null; }
  function dispose() { stop(); disposed = true; for (const controller of controllers) controller.abort(); controllers.clear(); }
  return { start, stop, refresh, snapshot, dispose };
}
