// Written by AI on 2026-10-24 by model GPT-6.1 Sol.
// Surveyed fixture anchors, explicitly illustrative emitted light.
import * as THREE from 'three';

const TILE_METRES = 1024;
const CELL_METRES = 8;
const TILE_PIXELS = TILE_METRES / CELL_METRES;
const ATLAS_TILES = 4;
const ATLAS_PIXELS = TILE_PIXELS * ATLAS_TILES;

const fragmentDeclarations = `
  uniform sampler2D fixtureHeadFirst;
  uniform sampler2D fixtureHeadSecond;
  uniform vec2 fixtureAtlasOrigin;
  uniform float fixtureFieldStrength;
  uniform float fixtureNight;
  float fixtureIllumination(vec4 head, vec2 cellCentre, vec3 surfaceNormal) {
    if (head.w <= 0.0) return 0.0;
    vec3 toHead = vec3(cellCentre.x + head.x, head.y, cellCentre.y + head.z) - cityWorldPosition;
    float distanceToHead = length(toHead);
    float normalizedDistance = distanceToHead / head.w;
    float downward = smoothstep(-1.0, 2.0, toHead.y);
    float facing = max(0.0, dot(surfaceNormal, toHead / max(distanceToHead, 0.1)));
    float falloff = exp(-2.0 * normalizedDistance * normalizedDistance)
      * (1.0 - smoothstep(0.75, 1.0, normalizedDistance));
    return falloff * downward * facing;
  }
`;

const fragmentLighting = `
  if (fixtureNight > 0.001 && fixtureFieldStrength > 0.001) {
    vec2 fixtureLocal = cityWorldPosition.xz - fixtureAtlasOrigin;
    vec2 fixtureCell = floor(fixtureLocal / 8.0);
    vec2 fixtureUV = (fixtureCell + 0.5) / 512.0;
    if (all(greaterThanEqual(fixtureUV, vec2(0.0))) && all(lessThan(fixtureUV, vec2(1.0)))) {
      vec2 fixtureCellCentre = fixtureAtlasOrigin + (fixtureCell + 0.5) * 8.0;
      vec3 fixtureNormal = inverseTransformDirection(normal, viewMatrix);
      float fixtureLight = fixtureIllumination(texture2D(fixtureHeadFirst, fixtureUV), fixtureCellCentre, fixtureNormal)
        + fixtureIllumination(texture2D(fixtureHeadSecond, fixtureUV), fixtureCellCentre, fixtureNormal);
      vec2 fixtureEdge = min(fixtureLocal, vec2(4096.0) - fixtureLocal);
      float fixtureEdgeFade = smoothstep(0.0, 64.0, min(fixtureEdge.x, fixtureEdge.y));
      totalEmissiveRadiance += diffuseColor.rgb * vec3(1.0, 0.62, 0.29)
        * min(fixtureLight, 1.2) * fixtureNight * fixtureFieldStrength * fixtureEdgeFade * 0.55;
    }
  }
`;

function groundFootprint(camera) {
  const points = [];
  for (const x of [-1, 1]) for (const y of [-1, 1]) {
    const near = new THREE.Vector3(x, y, -1).unproject(camera);
    const far = new THREE.Vector3(x, y, 1).unproject(camera);
    const direction = far.sub(near);
    points.push(near.addScaledVector(direction, -near.y / direction.y));
  }
  return new THREE.Box2().setFromPoints(points.map(point => new THREE.Vector2(point.x, point.z)));
}

export function createFixtureSurfaceLighting({ enabled, night, requestRender, baseUrl = './data/lamp-surface-lighting/' }) {
  if (!enabled) return { apply() {}, setView() {}, async prepareView() {}, dispose() {}, strengthUniform: { value: 0 }, diagnostics: () => ({ enabled: false }) };
  const fields = [0, 1].map(() => new Uint16Array(ATLAS_PIXELS * ATLAS_PIXELS * 4));
  const textures = fields.map(data => {
    const texture = new THREE.DataTexture(data, ATLAS_PIXELS, ATLAS_PIXELS, THREE.RGBAFormat, THREE.HalfFloatType);
    texture.minFilter = texture.magFilter = THREE.NearestFilter;
    texture.generateMipmaps = false;
    texture.needsUpdate = true;
    return texture;
  });
  const uniforms = {
    fixtureHeadFirst: { value: textures[0] }, fixtureHeadSecond: { value: textures[1] },
    fixtureAtlasOrigin: { value: new THREE.Vector2() }, fixtureFieldStrength: { value: 0 }, fixtureNight: night,
  };
  const stats = { enabled: true, gpuBytes: fields.reduce((sum, field) => sum + field.byteLength, 0),
    compressedBytes: 0, decodedBytes: 0, atlasUpdates: 0, loadedTiles: 0, pending: false, errors: [],
    missingPreparedTiles: [], emptyTiles: [], groundFootprintMetres: null, lookupCpuMilliseconds: 0 };
  let disposed = false;
  let timer;
  let generation = 0;
  let currentKey = '';
  let committedKey = '';
  let selectedView;
  let activeRequest;
  let manifestPromise;

  async function updateAtlas(view) {
    const requestGeneration = ++generation;
    activeRequest?.abort();
    activeRequest = new AbortController();
    const signal = activeRequest.signal;
    stats.pending = true;
    try {
      manifestPromise ??= fetch(new URL('manifest.json', new URL(baseUrl, document.baseURI)))
        .then(response => { if (!response.ok) throw Error(`Fixture field manifest: HTTP ${response.status}`); return response.json(); });
      const manifest = await manifestPromise;
      const available = new Map(manifest.tiles.map(tile => [`${tile.x}_${tile.z}`, tile]));
      const records = [];
      const missing = [];
      const empty = [];
      const prepared = new Set(manifest.preparedTiles.map(tile => `${tile[0]}_${tile[1]}`));
      for (let row = 0; row < ATLAS_TILES; row++) for (let column = 0; column < ATLAS_TILES; column++) {
        const x = view.tileX + column, z = view.tileZ + row;
        const tile = available.get(`${x}_${z}`);
        if (tile) records.push({ ...tile, row, column });
        else if (manifest.coverage === 'all-source-influence' || prepared.has(`${x}_${z}`)) empty.push(`${x}_${z}`);
        else missing.push(`${x}_${z}`);
      }
      const loaded = await Promise.all(records.map(async tile => {
        const response = await fetch(new URL(tile.uri, new URL(baseUrl, document.baseURI)), { signal });
        if (!response.ok) throw Error(`Fixture field ${tile.uri}: HTTP ${response.status}`);
        const compressed = await response.arrayBuffer();
        const stream = new Blob([compressed]).stream().pipeThrough(new DecompressionStream('gzip'));
        const decoded = await new Response(stream).arrayBuffer();
        if (decoded.byteLength !== 2 * TILE_PIXELS * TILE_PIXELS * 4 * 2) throw Error(`Fixture field ${tile.uri}: invalid length`);
        return { ...tile, data: new Uint16Array(decoded), compressedBytes: compressed.byteLength };
      }));
      if (disposed || requestGeneration !== generation) return;
      const started = performance.now();
      for (const field of fields) field.fill(0);
      for (const tile of loaded) for (let rank = 0; rank < 2; rank++) for (let row = 0; row < TILE_PIXELS; row++) {
        const sourceOffset = (rank * TILE_PIXELS * TILE_PIXELS + row * TILE_PIXELS) * 4;
        const destinationOffset = ((tile.row * TILE_PIXELS + row) * ATLAS_PIXELS + tile.column * TILE_PIXELS) * 4;
        fields[rank].set(tile.data.subarray(sourceOffset, sourceOffset + TILE_PIXELS * 4), destinationOffset);
      }
      for (const texture of textures) texture.needsUpdate = true;
      uniforms.fixtureAtlasOrigin.value.set(view.tileX * TILE_METRES, view.tileZ * TILE_METRES);
      uniforms.fixtureFieldStrength.value = selectedView.strength;
      stats.compressedBytes += loaded.reduce((sum, tile) => sum + tile.compressedBytes, 0);
      stats.decodedBytes = loaded.length * 262144;
      stats.loadedTiles = loaded.length;
      stats.missingPreparedTiles = missing;
      stats.emptyTiles = empty;
      stats.atlasUpdates++;
      stats.lookupCpuMilliseconds = performance.now() - started;
      stats.atlasOrigin = uniforms.fixtureAtlasOrigin.value.toArray();
      committedKey = `${view.tileX}_${view.tileZ}`;
      requestRender();
    } catch (error) {
      if (!disposed && error.name !== 'AbortError') { stats.errors = [...stats.errors.slice(-7), error.message]; console.warn('010 fixture lighting:', error); }
    } finally {
      if (requestGeneration === generation) { stats.pending = false; requestRender(); }
    }
  }

  const api = {
    strengthUniform: uniforms.fixtureFieldStrength,
    apply(material) {
      const previousCompile = material.onBeforeCompile;
      const previousKey = material.customProgramCacheKey();
      material.onBeforeCompile = function(shader, renderer) {
        previousCompile.call(this, shader, renderer);
        Object.assign(shader.uniforms, uniforms);
        // cityWorldPosition is declared by the existing shared city material.
        shader.fragmentShader = shader.fragmentShader.replace('void main() {', `${fragmentDeclarations}\nvoid main() {`);
        shader.fragmentShader = shader.fragmentShader.replace('#include <emissivemap_fragment>', `#include <emissivemap_fragment>\n${fragmentLighting}`);
      };
      material.customProgramCacheKey = () => `${previousKey}-fixture-surface-v1`;
      material.needsUpdate = true;
    },
    setView(camera) {
      if (night.value <= 0.001) {
        clearTimeout(timer);
        activeRequest?.abort();
        generation++;
        stats.pending = false;
        stats.viewStrength = 0;
        currentKey = committedKey;
        uniforms.fixtureFieldStrength.value = 0;
        return;
      }
      const footprint = groundFootprint(camera);
      const extent = footprint.getSize(new THREE.Vector2());
      const centre = footprint.getCenter(new THREE.Vector2());
      // Fade surface illumination before its fixed atlas cannot cover the view.
      const strength = 1 - THREE.MathUtils.smoothstep(Math.max(extent.x, extent.y), 2800, 3500);
      const tileX = Math.floor((centre.x - 2048) / TILE_METRES + 0.5);
      const tileZ = Math.floor((centre.y - 2048) / TILE_METRES + 0.5);
      stats.groundFootprintMetres = extent.toArray();
      stats.viewStrength = strength;
      selectedView = { tileX, tileZ, strength };
      if (stats.atlasUpdates) uniforms.fixtureFieldStrength.value = strength;
      const key = `${tileX}_${tileZ}`;
      clearTimeout(timer);
      if (key !== currentKey && strength > 0) {
        timer = setTimeout(() => { currentKey = key; updateAtlas(selectedView); }, 150);
      }
    },
    async prepareView(camera) {
      api.setView(camera);
      clearTimeout(timer);
      if (night.value <= 0.001 || selectedView.strength <= 0) return;
      const key = `${selectedView.tileX}_${selectedView.tileZ}`;
      if (key === committedKey && !stats.pending) return;
      currentKey = key;
      await updateAtlas(selectedView);
    },
    diagnostics: () => ({ ...stats }),
    dispose() {
      disposed = true;
      generation++;
      clearTimeout(timer);
      activeRequest?.abort();
      for (const texture of textures) texture.dispose();
    },
  };
  return api;
}
