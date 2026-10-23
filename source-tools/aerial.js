import * as THREE from 'three';

const EARTH_CIRCUMFERENCE = 2 * Math.PI * 6378137;
const TILE_SIZE = 256;
const TILE_URL = 'https://service.pdok.nl/hwh/luchtfotorgb/wmts/v1_0/2026_orthoHR/EPSG:3857/';
export function mercatorPosition(lat, lon) {
  return new THREE.Vector2(6378137 * lon * Math.PI / 180, 6378137 * Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360)));
}

export function createAerialImagery({ renderer, origin, geographicPosition, onUpdate }) {
  const uniforms = { map: { value: null }, rectangle: { value: new THREE.Vector4(0, 0, 1, 1) }, enabled: { value: 0 } };
  const imageCache = new Map();
  let active = null, pendingKey = '', pending = Promise.resolve(), controller = null, disposed = false;
  const state = { loading: false, zoom: null, tiles: 0, error: null };

  async function tileImage(z, x, y, signal) {
    const key = `${z}/${x}/${y}`;
    if (imageCache.has(key)) return imageCache.get(key);
    const response = await fetch(`${TILE_URL}${key}.jpeg`, { signal });
    if (response.status === 404) return null;
    if (!response.ok) throw new Error(`Aerial imagery returned ${response.status}.`);
    const bitmap = await createImageBitmap(await response.blob());
    imageCache.set(key, bitmap);
    while (imageCache.size > 192) { const oldest = imageCache.keys().next().value; imageCache.get(oldest).close(); imageCache.delete(oldest); }
    return bitmap;
  }

  function update(camera, width, height, highResolution = false) {
    if (disposed) return Promise.reject(new Error('The imagery layer has closed.'));
    const rays = new THREE.Raycaster(), plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
    const bounds = new THREE.Box2();
    for (const x of [-1, 1]) for (const y of [-1, 1]) {
      rays.setFromCamera(new THREE.Vector2(x, y), camera);
      const point = rays.ray.intersectPlane(plane, new THREE.Vector3());
      if (point) { const geo = geographicPosition(point); bounds.expandByPoint(mercatorPosition(geo.lat, geo.lon)); }
    }
    bounds.expandByScalar(40);
    const size = bounds.getSize(new THREE.Vector2());
    const pixelSize = Math.max(size.x / width, size.y / height);
    let zoom = Math.min(21, Math.max(10, Math.ceil(Math.log2(EARTH_CIRCUMFERENCE / (TILE_SIZE * pixelSize)))));
    const maximumAtlasSize = Math.min(highResolution ? 8192 : 4096, renderer.capabilities.maxTextureSize);
    let tileSpan, left, right, top, bottom;
    do {
      tileSpan = EARTH_CIRCUMFERENCE / 2 ** zoom;
      left = Math.floor((bounds.min.x + EARTH_CIRCUMFERENCE / 2) / tileSpan);
      right = Math.floor((bounds.max.x + EARTH_CIRCUMFERENCE / 2) / tileSpan);
      top = Math.floor((EARTH_CIRCUMFERENCE / 2 - bounds.max.y) / tileSpan);
      bottom = Math.floor((EARTH_CIRCUMFERENCE / 2 - bounds.min.y) / tileSpan);
      if ((right - left + 1) * TILE_SIZE <= maximumAtlasSize && (bottom - top + 1) * TILE_SIZE <= maximumAtlasSize) break;
      zoom--;
    } while (zoom > 9);
    if (active && active.zoom >= zoom && active.bounds.containsBox(bounds)) { uniforms.enabled.value = 1; return Promise.resolve(); }
    const key = `${zoom}/${left}/${top}/${right}/${bottom}`;
    if (pendingKey === key) return pending;
    controller?.abort(); controller = new AbortController();
    const signal = controller.signal;
    pendingKey = key; state.loading = true; state.error = null;
    pending = (async () => {
      const atlas = document.createElement('canvas');
      atlas.width = (right - left + 1) * TILE_SIZE; atlas.height = (bottom - top + 1) * TILE_SIZE;
      const context = atlas.getContext('2d');
      const tiles = [];
      for (let y = top; y <= bottom; y++) for (let x = left; x <= right; x++) tiles.push({ x, y });
      let next = 0, count = 0;
      await Promise.all(Array.from({ length: Math.min(6, tiles.length) }, async () => {
        while (next < tiles.length) {
          const tile = tiles[next++], bitmap = await tileImage(zoom, tile.x, tile.y, signal);
          if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
          if (bitmap) { context.drawImage(bitmap, (tile.x - left) * TILE_SIZE, (tile.y - top) * TILE_SIZE); count++; }
        }
      }));
      if (!count) throw new Error('No aerial imagery is available for this view.');
      const west = left * tileSpan - EARTH_CIRCUMFERENCE / 2;
      const north = EARTH_CIRCUMFERENCE / 2 - top * tileSpan;
      const atlasWidth = (right - left + 1) * tileSpan, atlasHeight = (bottom - top + 1) * tileSpan;
      const texture = new THREE.CanvasTexture(atlas);
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
      uniforms.map.value?.dispose(); uniforms.map.value = texture;
      uniforms.rectangle.value.set(west - origin.x, north - atlasHeight - origin.y, atlasWidth, atlasHeight);
      uniforms.enabled.value = 1;
      active = { zoom, bounds: new THREE.Box2(new THREE.Vector2(west, north - atlasHeight), new THREE.Vector2(west + atlasWidth, north)) };
      state.zoom = zoom; state.tiles = count; state.loading = false;
      onUpdate();
    })().catch(error => {
      if (signal.aborted) return;
      state.loading = false; state.error = error.message; pendingKey = '';
      throw error;
    });
    return pending;
  }
  return { uniforms, update, getDiagnostics: () => ({ ...state }), dispose() { disposed = true; controller?.abort(); uniforms.map.value?.dispose(); for (const bitmap of imageCache.values()) bitmap.close(); imageCache.clear(); } };
}
