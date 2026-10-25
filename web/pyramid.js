// Written by AI on 2026-10-25 by model Claude Opus 5.5.
// T2 and T3: show a pre-rendered pixel-art pyramid. No WebGL, no 3D: plain
// image tiles on the same art-pixel grid as the live view, one pyramid per
// bearing. Rotating swaps to the next bearing around the same street.

import { rdFromWgs84, wgs84FromRd } from './miniature/rd.js';

const params = new URLSearchParams(location.search);
const base = params.get('pyramid') ?? './pyramids/t2';
const bearings = (params.get('bearings') ?? '35,125,215,305').split(',').map(Number);
const STREET_HEIGHT = 3; // NAP metres; the point under the screen centre is at street level
const zoomLevels = [
  { level: 3, cssPerArt: 1 },
  { level: 2, cssPerArt: 1 },
  { level: 1, cssPerArt: 1 },
  { level: 0, cssPerArt: 1 },
  { level: 0, cssPerArt: 2 },
  { level: 0, cssPerArt: 3 },
];

const container = document.getElementById('map');
const world = document.createElement('div');
world.style.cssText = 'position:absolute;left:0;top:0;transform-origin:0 0;will-change:transform;image-rendering:pixelated;';
container.appendChild(world);

const start = params.has('lat')
  ? rdFromWgs84(Number(params.get('lat')), Number(params.get('lon')))
  : { x: Number(params.get('x') ?? 90341), y: Number(params.get('y') ?? 436174) };
const state = {
  x: start.x,
  y: start.y,
  bearingIndex: Math.max(0, bearings.indexOf(Number(params.get('bearing') ?? bearings[0]))),
  zoom: Number(params.get('z') ?? (innerWidth < 700 ? 3 : 2)),
};

const metas = new Map();
async function meta(bearing) {
  if (!metas.has(bearing)) metas.set(bearing, fetch(`${base}/b${bearing}/meta.json`).then((r) => r.json()));
  return metas.get(bearing);
}

function axes(bearingDegrees, elevationDegrees) {
  const b = bearingDegrees * Math.PI / 180, e = elevationDegrees * Math.PI / 180;
  const forward = [Math.sin(b), 0, -Math.cos(b)];
  return {
    right: [Math.cos(b), 0, Math.sin(b)],
    up: [forward[0] * Math.sin(e), Math.cos(e), forward[2] * Math.sin(e)],
  };
}

function screenPoint(m, levelInfo, x, y, z) {
  const p = [x - m.origin_rd[0], z, -(y - m.origin_rd[1])];
  const { right, up } = axes(m.bearing, m.elevation_degrees);
  const dot = (a) => a[0] * p[0] + a[1] * p[1] + a[2] * p[2];
  return { sx: dot(right) / levelInfo.metres_per_pixel, sy: dot(up) / levelInfo.metres_per_pixel };
}

const tiles = new Map();
let drawn = 0, firstViewMarked = false, generation = 0;

async function draw() {
  const thisGeneration = ++generation;
  const bearing = bearings[state.bearingIndex];
  const m = await meta(bearing);
  if (thisGeneration !== generation) return;
  const zoom = zoomLevels[state.zoom];
  const levelInfo = m.levels[zoom.level];
  const scale = zoom.cssPerArt;
  const centre = screenPoint(m, levelInfo, state.x, state.y, STREET_HEIGHT);
  const viewLeft = Math.round(centre.sx - innerWidth / 2 / scale);
  const viewTop = Math.round(centre.sy + innerHeight / 2 / scale);
  world.style.transform = `scale(${scale}) translate(${-(viewLeft - levelInfo.left)}px, ${viewTop - levelInfo.top}px)`;

  const tile = m.tile;
  const firstColumn = Math.max(0, Math.floor((viewLeft - levelInfo.left) / tile));
  const lastColumn = Math.min(levelInfo.columns - 1, Math.floor((viewLeft + innerWidth / scale - levelInfo.left) / tile));
  const firstRow = Math.max(0, Math.floor((levelInfo.top - viewTop) / tile));
  const lastRow = Math.min(levelInfo.rows - 1, Math.floor((levelInfo.top - viewTop + innerHeight / scale) / tile));
  const wanted = new Set();
  const pending = [];
  for (let row = firstRow; row <= lastRow; row++) {
    for (let column = firstColumn; column <= lastColumn; column++) {
      const key = `${bearing}/${zoom.level}/${column}_${row}`;
      wanted.add(key);
      let image = tiles.get(key);
      if (!image) {
        image = new Image(tile, tile);
        image.decoding = 'async';
        image.style.cssText = `position:absolute;left:${column * tile}px;top:${row * tile}px;width:${tile}px;height:${tile}px;`;
        image.src = `${base}/b${bearing}/${zoom.level}/${column}_${row}.webp`;
        tiles.set(key, image);
      }
      if (image.parentNode !== world) world.appendChild(image);
      if (!image.complete) pending.push(image.decode().catch(() => {}));
    }
  }
  for (const [key, image] of tiles) if (!wanted.has(key) && image.parentNode === world) world.removeChild(image);
  await Promise.all(pending);
  if (thisGeneration !== generation) return;
  if (!firstViewMarked) {
    firstViewMarked = true;
    performance.mark('map-first-view');
    performance.mark('map-complete');
    window.mapReady = true;
  }
  drawn++;
}

let scheduled = false;
const requestDraw = () => { if (!scheduled) { scheduled = true; requestAnimationFrame(() => { scheduled = false; draw(); }); } };

function writeUrl() {
  const { lat, lon } = wgs84FromRd(state.x, state.y);
  const next = new URLSearchParams(params);
  for (const k of ['x', 'y']) next.delete(k);
  next.set('lat', lat.toFixed(5)); next.set('lon', lon.toFixed(5));
  next.set('bearing', String(bearings[state.bearingIndex])); next.set('z', String(state.zoom));
  history.replaceState(null, '', `?${next}`);
}

async function panByCss(dx, dy) {
  const m = await meta(bearings[state.bearingIndex]);
  const zoom = zoomLevels[state.zoom];
  const metresPerCss = m.levels[zoom.level].metres_per_pixel / zoom.cssPerArt;
  const b = m.bearing * Math.PI / 180, e = m.elevation_degrees * Math.PI / 180;
  const right = dx * metresPerCss, forward = dy * metresPerCss / Math.sin(e);
  state.x += -right * Math.cos(b) + forward * Math.sin(b);
  state.y += right * Math.sin(b) + forward * Math.cos(b);
  requestDraw();
}
const zoomBy = (step) => { state.zoom = Math.min(zoomLevels.length - 1, Math.max(0, state.zoom + step)); requestDraw(); writeUrl(); };
const rotateBy = (step) => { state.bearingIndex = (state.bearingIndex + step + bearings.length) % bearings.length; requestDraw(); writeUrl(); };

const pointers = new Map();
let pinch = null;
container.addEventListener('pointerdown', (event) => { container.setPointerCapture(event.pointerId); pointers.set(event.pointerId, { x: event.clientX, y: event.clientY }); });
container.addEventListener('pointermove', (event) => {
  const previous = pointers.get(event.pointerId);
  if (!previous) return;
  const current = { x: event.clientX, y: event.clientY };
  pointers.set(event.pointerId, current);
  if (pointers.size === 1) panByCss(current.x - previous.x, current.y - previous.y);
  else if (pointers.size === 2) {
    const [a, b] = [...pointers.values()];
    const distance = Math.hypot(a.x - b.x, a.y - b.y);
    if (!pinch) pinch = { distance };
    if (distance / pinch.distance > 1.5) { zoomBy(1); pinch.distance = distance; }
    if (distance / pinch.distance < 0.67) { zoomBy(-1); pinch.distance = distance; }
  }
});
const release = (event) => { pointers.delete(event.pointerId); if (pointers.size < 2) pinch = null; writeUrl(); };
container.addEventListener('pointerup', release);
container.addEventListener('pointercancel', release);
container.addEventListener('wheel', (event) => { event.preventDefault(); zoomBy(event.deltaY < 0 ? 1 : -1); }, { passive: false });
container.addEventListener('dblclick', () => zoomBy(1));
document.getElementById('rotate-left').onclick = () => rotateBy(-1);
document.getElementById('rotate-right').onclick = () => rotateBy(1);
addEventListener('resize', requestDraw);
draw();
