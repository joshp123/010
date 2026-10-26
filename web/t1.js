// Written by AI on 2026-10-25 by model Claude Opus 5.5.
// T1: the city scene rendered live in the browser as pixel art.
// Also the offline renderer for T2: ?capture=1 renders one exact window.

import { Miniature, screenAxes } from './miniature/renderer.js';
import { rdFromWgs84, wgs84FromRd } from './miniature/rd.js';

const params = new URLSearchParams(location.search);
const sceneBase = params.get('scene') ?? './scene';
const canvas = document.getElementById('map');
const zoomLevels = [
  { metresPerPixel: 2.4, cssPerArt: 1 },
  { metresPerPixel: 1.2, cssPerArt: 1 },
  { metresPerPixel: 0.6, cssPerArt: 1 },
  { metresPerPixel: 0.3, cssPerArt: 1 },
  { metresPerPixel: 0.3, cssPerArt: 2 },
  { metresPerPixel: 0.3, cssPerArt: 3 },
];

const manifest = await fetch(`${sceneBase}/manifest.json`).then((r) => r.json());
const style = {};
if (params.has('elevation')) style.elevationDegrees = Number(params.get('elevation'));
if (params.get('style') === 'photo') Object.assign(style, { pixelArt: false, outlines: false });
if (params.has('detail')) style.groundPhotoDetail = Number(params.get('detail'));
if (params.get('light') === 'night') style.night = 1;
for (const key of ['facadeRadius', 'roofRadius', 'ambient', 'sun', 'dither', 'elevationDegrees', 'saturation']) if (params.has(key)) style[key] = Number(params.get(key));
if (params.get('roofs') === 'model') style.orthoRoofs = false;
const miniature = new Miniature(canvas, { sceneBase, manifest, area: params.get('area') ?? 'core', style });
window.miniature = miniature;

if (params.get('capture') === '1') {
  // Offline renderer for the pyramid builder: load once, then render any
  // exact window on the global art-pixel grid and hand back a PNG.
  await miniature.loadAll();
  window.renderWindow = (left, top, width, height, bearing, metresPerPixel, dataOverlay = false) => {
    miniature.style.dataOverlay = dataOverlay;
    miniature.setScreenWindow(left, top, width, height, bearing, metresPerPixel);
    miniature.render();
    return canvas.toDataURL('image/png');
  };
  window.screenBounds = (bearing, metresPerPixel) => miniature.screenBounds(bearing, metresPerPixel);
  window.captureReady = true;
} else {
  await runInteractive();
}

async function runInteractive() {
  const start = params.has('lat')
    ? rdFromWgs84(Number(params.get('lat')), Number(params.get('lon')))
    : { x: Number(params.get('x') ?? 90341), y: Number(params.get('y') ?? 436174) };
  const state = {
    x: start.x,
    y: start.y,
    bearing: Number(params.get('bearing') ?? 35),
    zoom: Number(params.get('z') ?? (innerWidth < 700 ? 3 : 2)),
  };
  let pending = false;

  function draw() {
    pending = false;
    const level = zoomLevels[state.zoom];
    // Pixel art draws one canvas pixel per art pixel and lets CSS enlarge it.
    // The photo variant draws at the screen's full resolution instead.
    const scale = miniature.style.pixelArt ? 1 / level.cssPerArt : devicePixelRatio;
    const width = Math.ceil(innerWidth * scale);
    const height = Math.ceil(innerHeight * scale);
    canvas.style.width = `${width / scale}px`;
    canvas.style.height = `${height / scale}px`;
    canvas.style.imageRendering = miniature.style.pixelArt ? 'pixelated' : 'auto';
    const metresPerPixel = miniature.style.pixelArt ? level.metresPerPixel : level.metresPerPixel / level.cssPerArt / devicePixelRatio;
    miniature.setView({ x: state.x, y: state.y, bearing: state.bearing, metresPerPixel, width, height });
    miniature.render();
  }
  const requestDraw = () => { if (!pending) { pending = true; requestAnimationFrame(draw); } };

  function writeUrl() {
    const { lat, lon } = wgs84FromRd(state.x, state.y);
    const next = new URLSearchParams(params);
    for (const k of ['x', 'y']) next.delete(k);
    next.set('lat', lat.toFixed(5)); next.set('lon', lon.toFixed(5));
    next.set('bearing', String(Math.round(state.bearing))); next.set('z', String(state.zoom));
    history.replaceState(null, '', `?${next}`);
  }

  function panByCss(dx, dy) {
    const level = zoomLevels[state.zoom];
    const b = state.bearing * Math.PI / 180;
    const e = miniature.style.elevationDegrees * Math.PI / 180;
    const right = dx / level.cssPerArt * level.metresPerPixel;
    const forward = dy / level.cssPerArt * level.metresPerPixel / Math.sin(e);
    state.x += -right * Math.cos(b) + forward * Math.sin(b);
    state.y += right * Math.sin(b) + forward * Math.cos(b);
    requestDraw();
  }

  function zoomBy(step) {
    state.zoom = Math.min(zoomLevels.length - 1, Math.max(0, state.zoom + step));
    requestDraw(); writeUrl();
  }

  function rotateBy(degrees) {
    state.bearing = (state.bearing + degrees + 360) % 360;
    requestDraw(); writeUrl();
  }

  const pointers = new Map();
  let pinch = null;
  canvas.addEventListener('pointerdown', (event) => {
    canvas.setPointerCapture(event.pointerId);
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
  });
  canvas.addEventListener('pointermove', (event) => {
    const previous = pointers.get(event.pointerId);
    if (!previous) return;
    const current = { x: event.clientX, y: event.clientY };
    pointers.set(event.pointerId, current);
    if (pointers.size === 1) {
      panByCss(current.x - previous.x, current.y - previous.y);
    } else if (pointers.size === 2) {
      const [a, b] = [...pointers.values()];
      const distance = Math.hypot(a.x - b.x, a.y - b.y);
      const angle = Math.atan2(b.y - a.y, b.x - a.x) * 180 / Math.PI;
      if (!pinch) pinch = { distance, angle };
      if (distance / pinch.distance > 1.5) { zoomBy(1); pinch.distance = distance; }
      if (distance / pinch.distance < 0.67) { zoomBy(-1); pinch.distance = distance; }
      if (Math.abs(angle - pinch.angle) > 3) { rotateBy(-(angle - pinch.angle)); pinch.angle = angle; }
    }
  });
  const release = (event) => { pointers.delete(event.pointerId); if (pointers.size < 2) pinch = null; writeUrl(); };
  canvas.addEventListener('pointerup', release);
  canvas.addEventListener('pointercancel', release);
  canvas.addEventListener('wheel', (event) => { event.preventDefault(); zoomBy(event.deltaY < 0 ? 1 : -1); }, { passive: false });
  canvas.addEventListener('dblclick', () => zoomBy(1));
  document.getElementById('rotate-left').onclick = () => rotateBy(-15);
  document.getElementById('rotate-right').onclick = () => rotateBy(15);
  document.getElementById('style').onclick = () => {
    miniature.style.pixelArt = !miniature.style.pixelArt;
    miniature.style.outlines = miniature.style.pixelArt;
    requestDraw();
  };
  addEventListener('resize', requestDraw);

  draw();
  const centreTile = miniature.tileAt(state.x, state.y);
  await miniature.loadAll((tile) => {
    if (tile === centreTile) { draw(); performance.mark('map-first-view'); }
    else requestDraw();
  });
  draw();
  performance.mark('map-complete');
  window.mapReady = true;
}
