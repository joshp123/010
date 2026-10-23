import { createScene } from './scene.js';
import { watchWeather, rotterdamTime } from './weather.js';

export const PUBLIC_DOMAIN = '010.jjpcodes.com';
const INITIAL_VIEW = { lat: 51.9105, lon: 4.4875, span: 1700, bearing: 35 };
const byId = id => document.getElementById(id);
const url = new URL(location.href);
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
  return result.href;
}

function updateView(view) {
  currentView = view;
  byId('compass').style.transform = `rotate(${-view.bearing}deg)`;
  if (selectedDestination && Math.hypot((view.lon - selectedDestination.lon) * 69000, (view.lat - selectedDestination.lat) * 111000) > 700) {
    selectedDestination = null;
    locationLabel = 'Rotterdam';
    document.querySelectorAll('.destination-row button').forEach(button => button.classList.remove('active'));
  }
  updateMinimap(view);
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
  document.querySelectorAll('.destination-row button').forEach(button => button.classList.toggle('active', button.dataset.destination === destination.id));
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
  if (!query.trim()) { showSearchResults(destinations.slice(0, 8)); return; }
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
    const priorities = [/Erasmusbrug/i, /Delfshaven/i, /Hoek van Holland/i, /Maasvlakte/i, /Centraal/i];
    const featured = priorities.map(pattern => destinations.find(item => pattern.test(item.name))).filter(Boolean);
    for (const place of featured) {
      const button = document.createElement('button');
      button.dataset.destination = place.id;
      button.textContent = place.name.replace('Rotterdam Centraal', 'Centraal');
      button.addEventListener('click', () => navigateTo(place));
      byId('destinations').append(button);
    }
  } catch (error) { console.warn(error.message); }
}

async function loadMinimap() {
  try {
    const response = await fetch('./data/municipality.geojson');
    if (!response.ok) return;
    const data = await response.json();
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

document.querySelectorAll('[data-light]').forEach(button => button.addEventListener('click', () => {
  lightingMode = button.dataset.light; applyLighting(); history.replaceState(null, '', encodeView());
}));
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
byId('place-search').addEventListener('focus', event => searchPlaces(event.target.value));
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
  if (!event.target.closest('#weather-details,#weather-toggle')) { byId('weather-details').hidden = true; byId('weather-toggle').setAttribute('aria-expanded', 'false'); }
});
document.addEventListener('keydown', event => {
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
byId('about-open').addEventListener('click', () => byId('about-dialog').showModal());
byId('about-dialog').querySelector('[data-close]').addEventListener('click', () => byId('about-dialog').close());
byId('about-dialog').addEventListener('click', event => { if (event.target === byId('about-dialog')) { const box = event.target.getBoundingClientRect(); if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) event.target.close(); } });
byId('share-open').addEventListener('click', async () => {
  if (!scene) return say('The map is still loading.');
  try {
    const { openShareDialog } = await import('./share.js');
    openShareDialog({ scene, domain: PUBLIC_DOMAIN, locationLabel, lightingMode, link: encodeView(`https://${PUBLIC_DOMAIN}/`) });
  } catch (error) { console.error(error); say('Could not prepare a screenshot. Please try again.'); }
});

clockTick();
setInterval(clockTick, 60000);
watchWeather(showWeather);
loadPlaces();
loadMinimap();

try {
  scene = await createScene({ canvas: byId('city'), onViewChange: updateView, onStatus: showSceneStatus });
  const params = url.searchParams;
  if (['lat', 'lon', 'span'].every(key => params.has(key) && Number.isFinite(Number(params.get(key))))) {
    const lat = Number(params.get('lat')), lon = Number(params.get('lon'));
    if (lat > 51.7 && lat < 52.1 && lon > 3.8 && lon < 4.7) {
      locationLabel = 'Rotterdam'; selectedDestination = null;
      scene.setView({ lat, lon, span: Math.max(200, Math.min(65000, Number(params.get('span')))), bearing: Number(params.get('bearing')) || 0 });
    }
  }
  applyLighting();
  window.__010 = { getView: () => scene.getView(), getDiagnostics: () => scene.getDiagnostics?.() };
} catch (error) {
  console.error('Rotterdam could not be drawn.', error);
  showSceneStatus({ state: 'error', message: 'The map could not start. Reload to try again.' });
}
