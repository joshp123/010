import { clampViewSpan } from './view-limits.js';
import { createScene } from './scene.js';
import { createLiveTransit } from './live-transit.js';
import { watchWeather, rotterdamTime } from './weather.js';

export const PUBLIC_DOMAIN = '010.jjpcodes.com';
const INITIAL_VIEW = { lat: 51.9105, lon: 4.4875, span: 1700, bearing: 35 };
const byId = id => document.getElementById(id);
const url = new URL(location.href);
const municipalityData = fetch('./data/municipality.json').then(response => {
  if (!response.ok) throw new Error('Municipality outline could not load.');
  return response.json();
});
let lightingMode = ['live', 'day', 'golden', 'night'].includes(url.searchParams.get('light')) ? url.searchParams.get('light') : 'live';
let weather = null;
let scene;
let destinations = [];
let locationLabel = 'Erasmusbrug';
let selectedDestination = { ...INITIAL_VIEW, name: 'Erasmusbrug' };
let updateUrlTimer;
let toastTimer;
let minimapProjection;
let currentView = { ...INITIAL_VIEW };
let searchAbort;
let searchTimer;
let activeSearchIndex = -1;
let liveTransit, latestTransitSnapshot, selectedVehicle;
function observationTime(seconds) {
  return seconds == null ? 'Not supplied' : new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Amsterdam', hour: '2-digit', minute: '2-digit', second: '2-digit', day: '2-digit', month: 'short' }).format(new Date(seconds * 1000)) + ' · Rotterdam';
}
function ageLabel(seconds) {
  if (seconds == null) return 'Observation time unknown';
  if (seconds < 0) return 'Observation time is in the future';
  return seconds < 60 ? `${Math.floor(seconds)} seconds old` : `${Math.floor(seconds / 60)} minutes old`;
}
function showVehicle(report) {
  const selectionChanged = selectedVehicle?.id !== report?.id;
  selectedVehicle = report;
  if (selectionChanged || !report) byId('vehicle-source-details').open = false;
  byId('vehicle-card').hidden = !report;
  if (!report) return;
  const fresh = report.freshness === 'fresh' && report.sourceConnected;
  byId('vehicle-title').textContent = `${report.mode[0].toUpperCase() + report.mode.slice(1)} ${report.label || '· route unknown'}`;
  byId('vehicle-state').textContent = `${report.sourceConnected ? fresh ? 'Fresh report' : report.freshness === 'stale' ? 'Stale report' : 'Unverified time' : 'Source disconnected'} · ${ageLabel(report.ageSeconds)}`;
  byId('vehicle-card').dataset.fresh = fresh;
  byId('vehicle-operator').textContent = report.operator || '';
  byId('vehicle-operator').hidden = !report.operator;
  const presentation = report.presentation || {};
  const represented = presentation.representedPosition;
  byId('vehicle-position-note').textContent = represented ? 'Position shown approximately on the track.' : '';
  byId('vehicle-position-note').hidden = !represented;
  const coordinates = point => Number.isFinite(point?.latitude) && Number.isFinite(point?.longitude) ? `${point.latitude.toFixed(6)}, ${point.longitude.toFixed(6)}` : 'Not supplied';
  const details = byId('vehicle-observation'); details.replaceChildren();
  const observationDetails = [['Observed', observationTime(report.observedAt)], ['Source', report.source === 'ns' ? 'NS · NL Trains Live' : 'OVapi / NDOV'], ['Reported position', coordinates(report)]];
  if (represented) observationDetails.push(['Shown position · approximate', coordinates(represented)]);
  for (const [title, value] of observationDetails) {
    const term = document.createElement('dt'), description = document.createElement('dd'); term.textContent = title; description.textContent = value; details.append(term, description);
  }
  const positionDescription = represented ? `Approximate track position, ${represented.offsetMetres.toFixed(1)} m from the report. No movement is inferred between reports.` : 'Reported position.';
  byId('vehicle-presentation').textContent = `${presentation.physicalForm === 'tunnel' ? 'Underground section · 12 m depth is illustrated, not surveyed. ' : ''}${positionDescription} Height: ${presentation.surfacePlacement || 'graphic surface height'}. Size illustrated. ${presentation.orientation === 'reported-bearing' ? 'Reported bearing: ' + Math.round(report.bearing) + '°.' : presentation.orientation === 'source-track-axis' || presentation.orientation === 'source-route-axis' ? 'Aligned with source route; direction unreported.' : 'Heading unreported; camera-facing symbol.'}`;
}
function showTransit(snapshot) {
  latestTransitSnapshot = snapshot;
  scene?.updateTransit(snapshot);
  showMetroViewStatus();
  const sources = Object.entries(snapshot.sources), fresh = snapshot.vehicles.filter(vehicle => vehicle.freshness === 'fresh' && vehicle.sourceConnected).length;
  byId('transit-count').textContent = `${fresh} fresh · ${snapshot.vehicles.length} reported`;
  byId('transit-health').textContent = sources.map(([name, source]) => {
    const label = name === 'ns' ? 'Trains' : 'Bus, tram & metro';
    return `${label}: ${source.status === 'error' ? 'disconnected' : source.status !== 'ready' ? 'connecting' : source.publicationFreshness === 'stale' ? 'feed stale' : 'connected'}`;
  }).join(' · ') + (snapshot.map.status === 'error' ? ' · Route names unavailable' : '');
  if (selectedVehicle) {
    const current = snapshot.vehicles.find(vehicle => vehicle.id === selectedVehicle.id);
    if (current) showVehicle(scene?.getTransitReport(current.id) || current);
    else { byId('vehicle-state').textContent = 'No longer in the latest report'; byId('vehicle-card').dataset.fresh = false; }
  }
}

let focusedMetroId = null;
function nextMetroReport(statistics) {
  const candidates = (statistics?.metroFocusCandidates || (statistics?.metroFocus ? [statistics.metroFocus] : []))
    .filter(report => Number.isFinite(report.latitude) && Number.isFinite(report.longitude));
  if (!candidates.length) return null;
  const previous = candidates.findIndex(report => report.id === focusedMetroId);
  if (previous >= 0) return candidates[(previous + 1) % candidates.length];
  return candidates.find(report => !report.inSection && report.freshness === 'fresh' && report.sourceConnected)
    || candidates.find(report => !report.inSection) || candidates[0];
}

function showMetroViewStatus() {
  const statistics = scene?.getTransitStatistics();
  const message = statistics?.cutawayMessage;
  byId('metro-map-status').hidden = !message || !byId('view-panel').hidden;
  byId('metro-view-status').hidden = !message;
  document.body.dataset.metroCutaway = statistics?.sectionEnabled ? 'true' : 'false';
  byId('metro-section-label').hidden = !statistics?.sectionEnabled;
  byId('metro-view-status').textContent = message ? `Metro cutaway · ${message}` : '';
  // Keep the map edge short; the full source-status wording remains in View.
  const offTrack = message?.includes('from mapped track');
  const state = offTrack ? (message.startsWith('Fresh') ? 'fresh, off track' : 'unverified, off track')
    : statistics?.visibleFreshUndergroundObservations ? `${statistics.visibleFreshUndergroundObservations} fresh report${statistics.visibleFreshUndergroundObservations === 1 ? '' : 's'}`
    : statistics?.visibleUndergroundObservations ? (message?.includes('older') ? 'older report' : 'unverified report')
    : 'no report here';
  byId('metro-status-brief').textContent = statistics?.cutawayShortMessage || `Metro · ${state}`;
  byId('metro-summary').setAttribute('aria-label', `${message || 'Metro cutaway'}. Open metro details.`);
  byId('metro-summary').title = message || '';
  const target = nextMetroReport(statistics);
  const targetFresh = target?.freshness === 'fresh' && target.sourceConnected;
  const candidates = statistics?.metroFocusCandidates || [];
  const next = candidates.length > 1 && (focusedMetroId !== null || candidates.some(report => report.inSection));
  const action = next ? 'Next' : 'Find';
  const label = target ? `${action} ${targetFresh ? 'reported metro' : 'older metro report, not live'}` : 'No metro reports available';
  for (const id of ['metro-find', 'metro-find-detail']) {
    const button = byId(id);
    button.disabled = !target || statistics?.metroState !== 'ready';
    button.setAttribute('aria-label', label);
    button.title = target ? `${label} · ${target.label || 'Metro'} · observed ${observationTime(target.observedAt)}` : label;
    button.textContent = id === 'metro-find' ? action : target ? `${action} ${targetFresh ? 'reported metro' : 'older metro report'} ↗` : 'No metro reports available';
  }
  byId('metro-find').hidden = !message;

}

function say(message) {
  byId('toast').textContent = message;
  byId('toast').hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { byId('toast').hidden = true; }, 3500);
}

function encodeView(base = location.href) {
  const result = new URL(base);
  result.search = '';
  const view = scene?.getView() || currentView;
  result.searchParams.set('lat', view.lat.toFixed(5));
  result.searchParams.set('lon', view.lon.toFixed(5));
  result.searchParams.set('span', Math.round(view.span));
  result.searchParams.set('bearing', Math.round(view.bearing));
  result.searchParams.set('light', lightingMode);
  // These modes are read once when the scene starts. Keep the active rendition
  // in copied links and history without propagating unrelated URL parameters.
  for (const [key, allowed] of Object.entries({ appearance: ['current', 'illustrated-row', 'illustrated-neighbourhood', 'off'], vegetation: ['native'], tanks: ['current', 'illustrated'], ground: ['illustrated'], source: ['municipal', 'prepared'] })) {
    const value = url.searchParams.get(key);
    if (allowed.includes(value)) result.searchParams.set(key, value);
  }
  return result.href;
}

function updateView(view) {
  currentView = view;
  byId('compass').style.transform = `rotate(${-view.bearing}deg)`;
  if (selectedDestination && Math.hypot((view.lon - selectedDestination.lon) * 69000, (view.lat - selectedDestination.lat) * 111000) > 700) {
    selectedDestination = null;
    locationLabel = 'Rotterdam';
  }
  updateMinimap(view);
  showMetroViewStatus();
  clearTimeout(updateUrlTimer);
  updateUrlTimer = setTimeout(() => history.replaceState(null, '', encodeView()), 350);
}

function updateMinimap(view) {
  if (!minimapProjection) return;
  const { point, horizontalScale, verticalScale } = minimapProjection;
  const [x, y] = point([view.lon, view.lat]);
  const width = Math.max(4, view.span / 69000 * horizontalScale);
  const height = Math.max(3, view.span / 111000 * verticalScale * .6);
  const marker = byId('minimap-view');
  marker.setAttribute('x', x - width / 2);
  marker.setAttribute('y', y - height / 2);
  marker.setAttribute('width', Math.min(175, width));
  marker.setAttribute('height', Math.min(75, height));
}

function navigateTo(destination) {
  const view = { lat: destination.latitude ?? destination.lat, lon: destination.longitude ?? destination.lon, span: destination.span || 1800, bearing: destination.bearing ?? currentView.bearing };
  selectedDestination = { ...view, name: destination.name };
  locationLabel = destination.name || 'Rotterdam';
  scene?.setView(view);
  closeSearch();
}

function showMunicipality() {
  const bounds = byId('city').getBoundingClientRect();
  const aspect = bounds.width / bounds.height;
  const portrait = aspect < 1;
  const extent = minimapProjection || { minX: 3.942, maxX: 4.603, minY: 51.842, maxY: 52.002 };
  const eastWest = (extent.maxX - extent.minX) * 69000;
  const northSouth = (extent.maxY - extent.minY) * 111000;
  const horizontal = portrait ? northSouth : eastWest;
  const vertical = (portrait ? eastWest : northSouth) / Math.sqrt(3);
  navigateTo({
    lon: (extent.minX + extent.maxX) / 2, lat: (extent.minY + extent.maxY) / 2,
    span: Math.max(horizontal / aspect, vertical) * 1.18,
    bearing: portrait ? 90 : 0, name: 'Gemeente Rotterdam',
  });
}

function applyLighting() {
  const now = new Date();
  const hour = Number(new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Amsterdam', hour: '2-digit', hourCycle: 'h23' }).format(now));
  const night = lightingMode === 'night' || lightingMode === 'live' && (hour < 7 || hour >= 19);
  document.body.dataset.theme = night ? 'night' : 'day';
  document.querySelector('meta[name="theme-color"]').content = night ? '#192c24' : '#e9ede7';
  scene?.setLighting({ mode: lightingMode, date: now, cloudCover: weather?.available ? weather.cloudCover : 0, rain: weather?.available ? weather.rain : 0, snow: weather?.available ? weather.snow : 0 });
  document.querySelectorAll('[data-light]').forEach(button => {
    const selected = button.dataset.light === lightingMode;
    button.classList.toggle('selected', selected);
    button.setAttribute('aria-pressed', selected);
  });
}

function clockTick() {
  byId('city-time').textContent = rotterdamTime(new Date());
  byId('city-time').dateTime = new Date().toISOString();
  byId('city-time').title = 'Local time in Rotterdam';
  if (lightingMode === 'live') applyLighting();
}

function showWeather(current) {
  weather = current;
  if (current.available) {
    byId('weather-summary').textContent = `${Math.round(current.temperature)}° · ${current.description}`;
    byId('weather-description').textContent = `${current.description}, ${Math.round(current.temperature)}°C`;
    byId('weather-measures').replaceChildren();
    [`Wind ${Math.round(current.wind)} km/h`, `Cloud ${Math.round(current.cloudCover)}%`, `Rain ${current.rain} mm`, `Snow ${current.snow} cm`].forEach(text => {
      const item = document.createElement('span'); item.textContent = text; byId('weather-measures').append(item);
    });
    byId('weather-source').textContent = `Open-Meteo model · ${rotterdamTime(current.date)} Rotterdam time. Updated every 15 minutes.`;
    byId('weather-toggle').title = `${current.description}, ${Math.round(current.temperature)}°C. Model time ${rotterdamTime(current.date)} in Rotterdam.`;
  } else {
    byId('weather-summary').textContent = 'Weather unavailable';
    byId('weather-description').textContent = 'Weather unavailable';
    byId('weather-measures').replaceChildren();
    byId('weather-source').textContent = 'The weather feed could not be reached. Local time and the map still work. We will try again automatically.';
  }
  applyLighting();
}

function showSceneStatus(status) {
  const notice = byId('scene-notice');
  notice.classList.toggle('settled', status.state === 'ready');
  notice.dataset.error = status.state === 'error' ? 'true' : 'false';
  byId('scene-status').textContent = status.state === 'error' ? status.message || 'Some buildings could not be loaded.' : status.message || 'Drawing the buildings…';
}

function closeSearch() {
  clearTimeout(searchTimer);
  searchAbort?.abort();
  byId('search-results').hidden = true;
  byId('place-search').setAttribute('aria-expanded', 'false');
  byId('place-search').removeAttribute('aria-activedescendant');
  activeSearchIndex = -1;
}

function showSearchResults(items, note) {
  const list = byId('search-results');
  list.replaceChildren();
  activeSearchIndex = -1;
  if (note) { const p = document.createElement('p'); p.className = 'search-note'; p.textContent = note; list.append(p); }
  items.forEach((item, index) => {
    const button = document.createElement('button');
    button.className = 'search-result'; button.id = `place-result-${index}`; button.setAttribute('role', 'option'); button.setAttribute('aria-selected', 'false');
    const name = document.createElement('span'); name.textContent = item.name;
    const kind = document.createElement('small'); kind.textContent = item.category || 'Street in Rotterdam';
    button.append(name, kind);
    button.addEventListener('click', () => chooseSearchResult(item));
    list.append(button);
  });
  list.hidden = false;
  byId('place-search').setAttribute('aria-expanded', 'true');
}

async function chooseSearchResult(item) {
  if (Number.isFinite(item.latitude)) {
    navigateTo(item);
  } else {
    try {
      showSearchResults([], 'Finding that street…');
      const response = await fetch(`https://api.pdok.nl/bzk/locatieserver/search/v3_1/lookup?id=${encodeURIComponent(item.id)}`);
      if (!response.ok) throw new Error('Place lookup failed');
      const data = await response.json();
      const centroid = data.response?.docs?.[0]?.centroide_ll;
      const match = /^POINT\s*\(\s*([\d.-]+)\s+([\d.-]+)\s*\)$/.exec(centroid || '');
      if (!match) throw new Error('Place coordinates unavailable');
      navigateTo({ name: item.name, longitude: Number(match[1]), latitude: Number(match[2]), span: 1600 });
    } catch { showSearchResults([], 'Could not find that street. Try another name.'); return; }
  }
  byId('place-search').value = item.name;
  byId('search-clear').hidden = false;
  byId('place-search').blur();
}

async function searchPlaces(query) {
  searchAbort?.abort();
  searchAbort = new AbortController();
  const local = destinations.filter(place => place.name.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  if (!query.trim()) { showSearchResults(destinations); return; }
  if (query.trim().length < 2) { showSearchResults(local, local.length ? null : 'Type a place or street name.'); return; }
  showSearchResults(local, local.length ? null : 'Looking for places…');
  try {
    const params = new URLSearchParams({ q: query, rows: '6' });
    params.append('fq', 'gemeentecode:0599');
    params.append('fq', 'type:(weg OR woonplaats OR gemeente OR buurt OR wijk)');
    const response = await fetch(`https://api.pdok.nl/bzk/locatieserver/search/v3_1/suggest?${params}`, { signal: searchAbort.signal });
    if (!response.ok) throw new Error('Search request failed');
    const result = await response.json();
    const remote = (result.response?.docs || []).map(place => ({ id: place.id, name: place.weergavenaam, category: place.type === 'weg' ? 'Street' : 'Place' }));
    const combined = [...local, ...remote].slice(0, 8);
    showSearchResults(combined, combined.length ? null : 'No match inside Rotterdam. Try a street or place name.');
  } catch (error) {
    if (error.name !== 'AbortError') showSearchResults(local, local.length ? null : 'Street search is unavailable. The places below still work.');
  }
}

async function loadPlaces() {
  try {
    const response = await fetch('./data/destinations.json');
    if (!response.ok) throw new Error('Destinations are unavailable');
    destinations = await response.json();
  } catch (error) { console.warn(error.message); }
}

async function loadMinimap() {
  try {
    const data = await municipalityData;
    const geometry = data.features[0].geometry;
    const polygons = geometry.type === 'MultiPolygon' ? geometry.coordinates : [geometry.coordinates];
    const points = polygons.flat(2);
    const minX = Math.min(...points.map(p => p[0])), maxX = Math.max(...points.map(p => p[0]));
    const minY = Math.min(...points.map(p => p[1])), maxY = Math.max(...points.map(p => p[1]));
    const horizontalScale = 170 / (maxX - minX), verticalScale = 65 / (maxY - minY);
    const point = ([lon, lat]) => [5 + (lon - minX) * horizontalScale, 72 - (lat - minY) * verticalScale];
    minimapProjection = { point, minX, maxX, minY, maxY, horizontalScale, verticalScale };
    for (const polygon of polygons) {
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', polygon.map(ring => ring.map((p, index) => `${index ? 'L' : 'M'}${point(p).map(n => n.toFixed(2)).join(',')}`).join(' ') + 'Z').join(' '));
      path.setAttribute('fill-rule', 'evenodd');
      byId('minimap-land').append(path);
    }
    updateMinimap(currentView);
  } catch (error) { console.warn('Overview map could not be loaded.', error); }
}

function setViewPanel(open, restoreFocus = false) {
  byId('view-panel').hidden = !open;
  byId('view-toggle').setAttribute('aria-expanded', String(open));
  if (open) closeSearch();
  if (restoreFocus) byId('view-toggle').focus();
  showMetroViewStatus();
}
byId('view-toggle').addEventListener('click', () => setViewPanel(byId('view-panel').hidden));
byId('view-close').addEventListener('click', () => setViewPanel(false, true));

document.querySelectorAll('[data-light]').forEach(button => button.addEventListener('click', () => {
  lightingMode = button.dataset.light; applyLighting(); history.replaceState(null, '', encodeView());
}));
byId('transit-toggle').addEventListener('click', () => {
  const open = byId('transit-details').hidden;
  byId('transit-details').hidden = !open;
  byId('transit-toggle').setAttribute('aria-expanded', open);
});
byId('vehicle-close').addEventListener('click', () => showVehicle(null));
byId('metro-cutaway').addEventListener('change', event => { scene?.setMetroCutaway(event.target.checked); showMetroViewStatus(); });
byId('metro-summary').addEventListener('click', () => {
  setViewPanel(true);
  byId('transit-details').hidden = false;
  byId('transit-toggle').setAttribute('aria-expanded', 'true');
  byId('metro-cutaway').focus();
});
byId('metro-close').addEventListener('click', () => {
  byId('metro-cutaway').checked = false;
  scene?.setMetroCutaway(false);
  showMetroViewStatus();
});
function focusNextMetro() {
  const target = nextMetroReport(scene?.getTransitStatistics());
  if (!target) return say('No metro report is currently available.');
  focusedMetroId = target.id;
  byId('metro-cutaway').checked = true;
  scene.setMetroCutaway(true);
  setViewPanel(false);
  navigateTo({ lat: target.latitude, lon: target.longitude, span: 170, name: `Metro ${target.label || ''}`.trim() });
  showMetroViewStatus();
}
byId('metro-find').addEventListener('click', focusNextMetro);
byId('metro-find-detail').addEventListener('click', focusNextMetro);
byId('zoom-in').addEventListener('click', () => scene?.zoom(1.4));
byId('zoom-out').addEventListener('click', () => scene?.zoom(.7));
byId('rotate').addEventListener('click', () => scene?.setView({ ...currentView, bearing: currentView.bearing + 45 }));
byId('home').addEventListener('click', () => navigateTo({ ...INITIAL_VIEW, name: 'Erasmusbrug' }));
byId('whole-city').addEventListener('click', showMunicipality);
byId('minimap').addEventListener('click', event => {
  if (!minimapProjection) return showMunicipality();
  const bounds = byId('minimap-svg').getBoundingClientRect();
  const x = (event.clientX - bounds.left) / bounds.width * 180, y = (event.clientY - bounds.top) / bounds.height * 80;
  const { minX, minY, horizontalScale, verticalScale } = minimapProjection;
  navigateTo({ lon: minX + (x - 5) / horizontalScale, lat: minY + (72 - y) / verticalScale, span: Math.min(currentView.span, 4500), name: 'Rotterdam' });
});
byId('weather-toggle').addEventListener('click', () => {
  const open = byId('weather-details').hidden;
  byId('weather-details').hidden = !open;
  byId('weather-toggle').setAttribute('aria-expanded', open);
});
byId('place-search').addEventListener('input', event => {
  const query = event.target.value;
  byId('search-clear').hidden = !query;
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => searchPlaces(query), 200);
});
byId('place-search').addEventListener('focus', event => { setViewPanel(false); searchPlaces(event.target.value); });
byId('search-clear').addEventListener('click', () => {
  byId('place-search').value = ''; byId('search-clear').hidden = true; byId('place-search').focus(); searchPlaces('');
});
byId('place-search').addEventListener('keydown', event => {
  const results = [...byId('search-results').querySelectorAll('.search-result')];
  if (event.key === 'Escape') { closeSearch(); byId('place-search').blur(); }
  if (['ArrowDown', 'ArrowUp'].includes(event.key) && results.length) {
    event.preventDefault();
    activeSearchIndex = (activeSearchIndex + (event.key === 'ArrowDown' ? 1 : -1) + results.length) % results.length;
    results.forEach((result, index) => { result.classList.toggle('highlighted', index === activeSearchIndex); result.setAttribute('aria-selected', index === activeSearchIndex); });
    byId('place-search').setAttribute('aria-activedescendant', results[activeSearchIndex].id);
    results[activeSearchIndex].scrollIntoView({ block: 'nearest' });
  }
  if (event.key === 'Enter' && results.length) { event.preventDefault(); results[Math.max(activeSearchIndex, 0)].click(); }
});
document.addEventListener('pointerdown', event => {
  if (!event.target.closest('.search-wrap')) closeSearch();
  if (!event.target.closest('#view-panel,#view-toggle')) setViewPanel(false);
  if (!event.target.closest('#weather-details,#weather-toggle')) { byId('weather-details').hidden = true; byId('weather-toggle').setAttribute('aria-expanded', 'false'); }
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && !byId('view-panel').hidden) { setViewPanel(false, true); return; }
  if (document.querySelector('dialog[open]') || event.target.matches('input,textarea')) return;
  if (event.key === '/') { event.preventDefault(); byId('place-search').focus(); }
  if (!scene) return;
  if (['+', '='].includes(event.key)) scene.zoom(1.4);
  if (event.key === '-') scene.zoom(.7);
  if (event.key === '[' || event.key === ']') scene.setView({ ...currentView, bearing: currentView.bearing + (event.key === ']' ? 15 : -15) });
  if (event.key.startsWith('Arrow')) {
    event.preventDefault();
    const delta = currentView.span * .2;
    scene.setView({ ...currentView, lon: currentView.lon + (event.key === 'ArrowRight' ? delta / 69000 : event.key === 'ArrowLeft' ? -delta / 69000 : 0), lat: currentView.lat + (event.key === 'ArrowUp' ? delta / 111000 : event.key === 'ArrowDown' ? -delta / 111000 : 0) });
  }
});
byId('about-open').addEventListener('click', () => { setViewPanel(false); byId('about-dialog').showModal(); });
byId('about-dialog').addEventListener('close', () => byId('view-toggle').focus());
byId('about-dialog').querySelector('[data-close]').addEventListener('click', () => byId('about-dialog').close());
byId('about-dialog').addEventListener('click', event => { if (event.target === byId('about-dialog')) { const box = event.target.getBoundingClientRect(); if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) event.target.close(); } });
byId('share-open').addEventListener('click', async () => {
  setViewPanel(false);
  closeSearch();
  if (!scene) return say('The map is still loading.');
  try {
    const { openShareDialog } = await import('./share.js');
    await openShareDialog({ scene, domain: PUBLIC_DOMAIN, locationLabel, lightingMode, link: encodeView(`https://${PUBLIC_DOMAIN}/`) });
  } catch (error) { console.error(error); say('Could not prepare a screenshot. Please try again.'); }
});

clockTick();
setInterval(clockTick, 60000);
watchWeather(showWeather);
loadPlaces();
loadMinimap();

try {
  scene = await createScene({ canvas: byId('city'), municipalityData, onViewChange: updateView, onStatus: showSceneStatus, onTransitSelect: showVehicle });
  const params = url.searchParams;
  if (['lat', 'lon', 'span'].every(key => params.has(key) && Number.isFinite(Number(params.get(key))))) {
    const lat = Number(params.get('lat')), lon = Number(params.get('lon'));
    if (lat > 51.7 && lat < 52.1 && lon > 3.8 && lon < 4.7) {
      locationLabel = 'Rotterdam'; selectedDestination = null;
      scene.setView({ lat, lon, span: clampViewSpan(params.get('span'), currentView.span), bearing: Number(params.get('bearing')) || 0 });
    }
  }
  applyLighting();
  liveTransit = createLiveTransit({ onUpdate: showTransit });
  liveTransit.start();
  Promise.allSettled([scene.trafficReady(), scene.cyclistsReady()]).then(([cars, cyclists]) => {
    const carsReady = cars.status === 'fulfilled', cyclistsReady = cyclists.status === 'fulfilled';
    byId('traffic-status').textContent = carsReady && cyclistsReady
      ? 'Cars and cyclists are simulated · not live traffic'
      : carsReady ? 'Cars are simulated · cyclists unavailable · not live traffic'
      : cyclistsReady ? 'Cyclists are simulated · cars unavailable · not live traffic'
      : 'Simulated cars and cyclists unavailable';
  });
  scene.metroReady().then(() => {
    byId('metro-cutaway').disabled = false;
    byId('metro-source-status').textContent = 'Source tunnel plan · surface routes stay above ground';
    showMetroViewStatus();
  }).catch(() => { byId('metro-source-status').textContent = 'Metro plan unavailable · live vehicles still work'; });
  window.addEventListener('pagehide', () => { liveTransit.stop(); });
  window.addEventListener('pageshow', event => { if (event.persisted) liveTransit.start(); });
  window.__010 = { reviewAppearanceSampling: preset => scene.reviewAppearanceSampling(preset), getView: () => scene.getView(), getDiagnostics: () => scene.getDiagnostics?.(), getTransit: () => latestTransitSnapshot, inspectTrafficSurfaces: options => scene.inspectTrafficSurfaces(options) };
} catch (error) {
  console.error('Rotterdam could not be drawn.', error);
  showSceneStatus({ state: 'error', message: 'The map could not start. Reload to try again.' });
}
