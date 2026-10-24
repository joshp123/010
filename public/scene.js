import { clampViewSpan } from './view-limits.js';
import { createFixtureSurfaceLighting } from './fixture-surface-lighting.js';
import * as THREE from 'three';
import { createCityMaterial, featureColor, streetColor, yardColor, createLampPoolMaterial, applyMetroCutaway } from './miniature-style.js';
import { createSourceFusion } from './source-fusion.js';
import { omitInvalidGroundTriangles } from './ground-height-filter.js';
import { createSurfaceQuery } from './surface-query.js';
import { createCompressedModelsPlugin } from './compressed-models.js';
import { createObjectDetail } from './object-detail.js';
import { createSimulatedTraffic } from './simulated-traffic.js';
import { inspectTrafficSurfaces } from './traffic-surface-audit.js';
import { createTransitView } from './transit-view.js';
import { createMetroCityCut } from './metro-city-cut.js';
import { createBuildingBatches } from './building-batches.js';
import { createTreeBatches } from './tree-batches.js';
import { createVegetationStyle } from './vegetation-style.js';
import { applyPublicSpaceMaterial, createPublicSpaceStyle } from './public-space-style.js';
import { applyMiniatureLighting } from './miniature-lighting.js';
import { setAppearanceSampling } from './appearance-sampling.js';
import { createBuildingAppearanceReconciliation, createTankAppearanceReconciliation, prepareAppearanceModel, appearanceTextureDiagnostics } from './building-appearance.js';
import { TilesRenderer } from '3d-tiles-renderer';
import { LRUCache, unifiedPriorityCallback, FAILED, LOADED } from './vendor/3d-tiles-renderer/build/index.core.js';

const ORIGIN = { lat: 51.915, lon: 4.49 };
const DEFAULT_VIEW = { lat: 51.9105, lon: 4.4875, span: 1700, bearing: 35 };
const DEGREES = Math.PI / 180;
const DATA_BASE = 'https://www.3drotterdam.nl/datasource-data/';
const LAYERS = [
  ['streets', './data/streets/tileset.json'],
  ['greenTerrain', './data/green-terrain/tileset.json'],
  ['industrialStructures', './data/industrial-structures/tileset.json'],
  ['yards', './data/industrial-ground/tileset.json'],
  ['industrialTerrain', './data/industrial-terrain/tileset.json'],
  ['lamps', './data/lamps/tileset.json'],
  ['lamps', './data/supplementary-lamps/tileset.json'],
  ['buildings', './data/building-index/tileset.json'],
  ['appearanceBuildings', './data/building-appearance/tileset.json'],
  ['ground', './data/native-ground-bounds/tileset.json'],
  ['bridges', '06595036-c78e-4081-ab25-e8f88b66bc19'],
  ['bridgeSurfaces', './data/bridge-surfaces/tileset.json'],
  ['tanks', 'c70023a7-2878-41e9-bb81-a7c454bc310a'],
  ['appearanceTanks', './data/current-tank-appearance/tileset.json'],
  ['trees', 'b9294d5b-79e0-4744-ac88-b61e3e90d5bc'],
  ['lights', '2602863a-3d22-44c2-8c95-bbf88a20bf37'],
];

function earthPosition(lat, lon, height = 0) {
  const latitude = lat * DEGREES, longitude = lon * DEGREES;
  const radius = 6378137 / Math.sqrt(1 - 0.00669437999014 * Math.sin(latitude) ** 2);
  return new THREE.Vector3((radius + height) * Math.cos(latitude) * Math.cos(longitude), (radius + height) * Math.cos(latitude) * Math.sin(longitude), (radius * (1 - 0.00669437999014) + height) * Math.sin(latitude));
}
const originEarth = earthPosition(ORIGIN.lat, ORIGIN.lon);
const latRadians = ORIGIN.lat * DEGREES, lonRadians = ORIGIN.lon * DEGREES;
const east = new THREE.Vector3(-Math.sin(lonRadians), Math.cos(lonRadians), 0);
const up = new THREE.Vector3(Math.cos(latRadians) * Math.cos(lonRadians), Math.cos(latRadians) * Math.sin(lonRadians), Math.sin(latRadians));
const south = new THREE.Vector3(Math.sin(latRadians) * Math.cos(lonRadians), Math.sin(latRadians) * Math.sin(lonRadians), -Math.cos(latRadians));
const earthToLocal = new THREE.Matrix4().set(east.x, east.y, east.z, -east.dot(originEarth), up.x, up.y, up.z, -up.dot(originEarth), south.x, south.y, south.z, -south.dot(originEarth), 0, 0, 0, 1);
const localToEarth = earthToLocal.clone().invert();
function localPosition(lat, lon, height = 0) { return earthPosition(lat, lon, height).applyMatrix4(earthToLocal); }
function geographicPosition(local) {
  const earth = local.clone().applyMatrix4(localToEarth);
  const p = Math.hypot(earth.x, earth.y);
  let latitude = Math.atan2(earth.z, p * (1 - 0.00669437999014));
  for (let i = 0; i < 4; i++) {
    const radius = 6378137 / Math.sqrt(1 - 0.00669437999014 * Math.sin(latitude) ** 2);
    latitude = Math.atan2(earth.z + 0.00669437999014 * radius * Math.sin(latitude), p);
  }
  return { lat: latitude / DEGREES, lon: Math.atan2(earth.y, earth.x) / DEGREES };
}

function batchTableFor(mesh) { let parent = mesh; while (parent && !parent.batchTable) parent = parent.parent; return parent?.batchTable; }



function solarDirection(date, lat, lon) {
  const day = (date.getTime() / 86400000) - 10957.5;
  const anomaly = (357.5291 + 0.98560028 * day) * DEGREES;
  const ecliptic = anomaly + (1.9148 * Math.sin(anomaly) + 0.02 * Math.sin(2 * anomaly) + 0.0003 * Math.sin(3 * anomaly) + 102.9372) * DEGREES + Math.PI;
  const declination = Math.asin(Math.sin(ecliptic) * Math.sin(23.4397 * DEGREES));
  const rightAscension = Math.atan2(Math.sin(ecliptic) * Math.cos(23.4397 * DEGREES), Math.cos(ecliptic));
  const hourAngle = (280.16 + 360.9856235 * day + lon) * DEGREES - rightAscension;
  const latitude = lat * DEGREES;
  const altitude = Math.asin(Math.sin(latitude) * Math.sin(declination) + Math.cos(latitude) * Math.cos(declination) * Math.cos(hourAngle));
  const azimuth = Math.atan2(Math.sin(hourAngle), Math.cos(hourAngle) * Math.sin(latitude) - Math.tan(declination) * Math.cos(latitude));
  return { altitude, direction: new THREE.Vector3(-Math.cos(altitude) * Math.sin(azimuth), Math.sin(altitude), Math.cos(altitude) * Math.cos(azimuth)) };
}

export async function createScene({ canvas, municipalityData, onViewChange = () => {}, onStatus = () => {}, onTransitSelect = () => {} }) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
  const shaderErrors = [];
  renderer.debug.onShaderError = (gl, program, vertexShader, fragmentShader) => {
    const diagnostic = {
      program: (gl.getProgramInfoLog(program) || '').slice(0, 8192),
      vertex: (gl.getShaderInfoLog(vertexShader) || '').slice(0, 8192),
      fragment: (gl.getShaderInfoLog(fragmentShader) || '').slice(0, 8192),
    };
    shaderErrors.push(diagnostic);
    if (shaderErrors.length > 8) shaderErrors.shift();
    console.error('010: shader compilation failed', diagnostic);
  };
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.2;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.shadowMap.autoUpdate = false;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#b2cecd');
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 1, 150000);
  const target = localPosition(DEFAULT_VIEW.lat, DEFAULT_VIEW.lon);
  const view = { ...DEFAULT_VIEW };
  const sun = new THREE.DirectionalLight('#fff1d3', 3.2);
  sun.castShadow = true;
  sun.shadow.mapSize.set(4096, 4096);
  sun.shadow.bias = -0.00015;
  sun.shadow.normalBias = 0.8;
  sun.shadow.camera.near = 1;
  sun.shadow.camera.far = 50000;
  scene.add(sun, sun.target);
  const sky = new THREE.HemisphereLight('#cfe9ff', '#8f7761', 1.25);
  scene.add(sky);
  const reflectionTarget = new THREE.WebGLRenderTarget(512, 512, { minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter, type: THREE.HalfFloatType });
  const reflectionCamera = camera.clone();
  const cityTarget = new THREE.WebGLRenderTarget(512, 512, { type: THREE.HalfFloatType, samples: Math.min(4, renderer.capabilities.maxSamples) });
  const weatherUniforms = { city: { value: cityTarget.texture }, time: { value: 0 }, resolution: { value: new THREE.Vector2(512, 512) }, rain: { value: 0 }, snow: { value: 0 } };
  const presentationScene = new THREE.Scene();
  const presentationCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  const presentationMaterial = new THREE.ShaderMaterial({
    uniforms: weatherUniforms, depthTest: false, depthWrite: false,
    vertexShader: `varying vec2 weatherUV; void main() { weatherUV = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`,
    fragmentShader: `
      uniform sampler2D city; uniform float time; uniform vec2 resolution; uniform float rain; uniform float snow; varying vec2 weatherUV;
      float weatherHash(vec2 p) { return fract(sin(dot(p,vec2(127.1,311.7))) * 43758.5453); }
      void main() {
        vec3 color = texture2D(city, weatherUV).rgb;
        if (rain > 0.0) {
          vec2 grid = weatherUV * resolution / vec2(18.0,32.0); grid.x += grid.y * 0.18; grid.y += time * 8.5;
          vec2 cell = fract(grid); float seed = weatherHash(floor(grid));
          float streakHalfLength = mix(2.5,7.0,weatherHash(floor(grid)+17.0)) / 32.0;
          float streak = (1.0-smoothstep(0.01,0.045,abs(cell.x-0.5))) * (1.0-smoothstep(streakHalfLength-0.02,streakHalfLength,abs(cell.y-0.5))) * step(1.0-rain*0.12,seed);
          color = mix(color, vec3(0.55,0.69,0.78), streak * 0.12);
        }
        if (snow > 0.0) {
          vec2 grid = weatherUV * resolution / 32.0; grid.y += time * 0.45; grid.x += sin(time*0.55+floor(grid.y))*0.22;
          float flake = (1.0-smoothstep(0.025,0.065,length(fract(grid)-0.5))) * step(1.0-snow*0.28,weatherHash(floor(grid)));
          color = mix(color,vec3(0.9,0.94,1.0),flake*0.7);
        }
        gl_FragColor = vec4(color, 1.0);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }`,
  });
  const presentationQuad = new THREE.Mesh(new THREE.PlaneGeometry(2,2), presentationMaterial); presentationScene.add(presentationQuad);
  const uniforms = { night: { value: 0 }, snow: { value: 0 }, reflection: { value: reflectionTarget.texture }, reflectionMatrix: { value: new THREE.Matrix4() }, reflectionTexel: { value: new THREE.Vector2(1 / 512, 1 / 512) } };
  const glowUniforms = { night: uniforms.night, size: { value: 4 } };
  const lampGlowMaterial = new THREE.ShaderMaterial({
    uniforms: glowUniforms, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false,
    vertexShader: `uniform float size; void main() { gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); gl_PointSize = size; }`,
    fragmentShader: `uniform float night; void main() { float radius = length(gl_PointCoord - 0.5) * 2.0; if(radius > 1.0) discard; float glow = exp(-radius * radius * 10.0) * 0.38 + exp(-radius * radius * 3.0) * 0.07; gl_FragColor = vec4(vec3(1.0, 0.61, 0.23), glow * night); }`,
  });
  const lampPixelsPerMetre = { value: 1 };
  const fixtureSurfaceLighting = createFixtureSurfaceLighting({ enabled: true, night: uniforms.night, requestRender });
  const lampPoolMaterial = createLampPoolMaterial(uniforms.night, lampPixelsPerMetre, fixtureSurfaceLighting.strengthUniform);
  const lampShaftMaterial = new THREE.LineBasicMaterial({ color: '#53666a', transparent: true, opacity: 0.55 });
  const materials = Object.fromEntries(LAYERS.map(([kind]) => [kind, createCityMaterial(['streets', 'bridgeSurfaces', 'greenTerrain', 'industrialTerrain'].includes(kind) ? 'ground' : kind, uniforms)]));
  for (const kind of ['buildings', 'industrialStructures', 'bridges', 'tanks', 'ground', 'streets', 'bridgeSurfaces', 'industrialTerrain', 'yards']) fixtureSurfaceLighting.apply(materials[kind]);
  const cartographicMaterial = createCityMaterial('ground', uniforms);
  cartographicMaterial.depthWrite = false;
  const contextLandMaterial = createCityMaterial('ground', uniforms);
  contextLandMaterial.depthWrite = false;
  materials.streets.depthWrite = materials.yards.depthWrite = false;
  const emptyCutawayTexture = new THREE.DataTexture(new Uint8Array([0]), 1, 1, THREE.RedFormat);
  emptyCutawayTexture.needsUpdate = true;
  const cutawayUniforms = { enabled: { value: 0 }, mask: { value: emptyCutawayTexture }, bounds: { value: new THREE.Vector4(0, 0, 1, 1) }, projection: { value: new THREE.Vector2() } };
  const metroCityCut = createMetroCityCut();
  scene.add(metroCityCut.group);
  const cutawayDepthMaterial = new THREE.MeshDepthMaterial({ depthPacking: THREE.RGBADepthPacking, side: THREE.DoubleSide });
  applyMetroCutaway(cutawayDepthMaterial, cutawayUniforms);
  function bindCutawayShadows(model) {
    model.traverse(mesh => { if (mesh.isMesh && mesh.castShadow) mesh.customDepthMaterial = cutawayDepthMaterial; });
  }
  // The tunnel section must not cut holes through unrelated overground bridges.
  for (const material of [...Object.entries(materials).filter(([kind]) => !['bridges', 'bridgeSurfaces'].includes(kind)).map(([, material]) => material), cartographicMaterial, contextLandMaterial, lampGlowMaterial, lampPoolMaterial, lampShaftMaterial]) applyMetroCutaway(material, cutawayUniforms);
  for (const material of [...['ground', 'streets', 'bridgeSurfaces', 'greenTerrain', 'industrialTerrain', 'yards'].map(kind => materials[kind]), cartographicMaterial, contextLandMaterial]) applyPublicSpaceMaterial(material);
  const publicSpaceStyle = createPublicSpaceStyle({ material: materials.ground });
  Object.assign(materials.bridgeSurfaces, { polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 });
  const seaGeometry = new THREE.PlaneGeometry(180000, 180000, 96, 96);
  const seaVertices = seaGeometry.getAttribute('position');
  for (let i = 0; i < seaVertices.count; i++) seaVertices.setZ(i, -((seaVertices.getX(i) ** 2 + seaVertices.getY(i) ** 2) / (2 * 6371000)));
  seaGeometry.computeVertexNormals();
  const seaColors = new Float32Array(seaVertices.count * 3);
  const waterColor = streetColor('water');
  for (let index = 0; index < seaColors.length; index += 3) waterColor.toArray(seaColors, index);
  seaGeometry.setAttribute('color', new THREE.BufferAttribute(seaColors, 3));
  const sea = new THREE.Mesh(seaGeometry, cartographicMaterial);
  sea.rotation.x = -Math.PI / 2;
  sea.position.y = -4;
  sea.receiveShadow = true; sea.renderOrder = -30;
  scene.add(sea);
  let needsRender = true, disposed = false, scheduledFrame = null, width = 1, height = 1;
  let loadErrors = 0, loadedTiles = 0, lighting = { mode: 'day', date: new Date(), cloudCover: 0, rain: 0, snow: 0 };
  let sunVector = new THREE.Vector3(-0.65, 0.8, 0.45).normalize();
  let lastStatus = '', lastPresentation = 0, lastCityRender = {};
  let latestInputTime = null;
  let gestureQuietUntil = 0, deferredUpdateTimer = null, viewUpdateDeferred = false;
  let overviewState = 'loading', contextState = 'loading';
  const loadMilestones = { firstBuildingsSubmittedMs: null, initialDetailSettledMs: null };
  const frameTimes = [], inputRenderTimes = [];
  function recordTiming(samples, value) { samples.push(value); if (samples.length > 240) samples.shift(); }
  function timingSummary(samples) { const sorted = [...samples].sort((a, b) => a - b); return { samples: sorted.length, median: sorted[Math.floor(sorted.length / 2)] ?? null, p95: sorted[Math.floor(sorted.length * 0.95)] ?? null }; }
  const failedTileRetries = new Map();
  const tilesets = [];
  const sourceFusion = createSourceFusion();
  const vegetationStyle = createVegetationStyle();
  const vegetationEnabled = new URLSearchParams(location.search).get('vegetation') !== 'native';
  const objectDetail = createObjectDetail({ maximumPixelError: 1 });
  const treeBatches = createTreeBatches(scene);
  const buildingBatches = createBuildingBatches();
  const buildingAppearance = createBuildingAppearanceReconciliation(buildingBatches);
  const tankAppearance = createTankAppearanceReconciliation();
  let appearanceSamplingPreset = 'baseline';
  const appearanceOption = new URLSearchParams(location.search).get('appearance');
  const appearanceEnabled = appearanceOption !== 'off';
  const appearanceEdition = ['current', 'illustrated-row'].includes(appearanceOption) ? appearanceOption : 'legacy';
  const tankAppearanceEnabled = appearanceEdition === 'current' && new URLSearchParams(location.search).get('tanks') === 'current';
  let capturingFullDetail = false;
  let transitSnapshot = { vehicles: [] }, transitSurfaceDirty = false;
  const transitSurfaceCache = new Map();
  const surfaceQueries = new Map(['bridgeSurfaces', 'industrialTerrain', 'ground', 'greenTerrain'].map(kind => [kind, createSurfaceQuery()]));
  function projectTransit(latitude, longitude, offsetMetres = 0, context = null) {
    // The road simulation prepares the municipality once. Only nearby source
    // surfaces are loaded, so avoid a second city-wide cache of its 192k points.
    if (context?.source === 'NWB') {
      const point = localPosition(latitude, longitude);
      if (Math.abs(point.x - target.x) > view.span * Math.max(1, width / height) * 1.5 || Math.abs(point.z - target.z) > view.span * 2) {
        point.y += offsetMetres;
        return point;
      }
    }
    const groundOnly = context?.preferGround === true;
    const key = `${groundOnly ? 'ground' : 'surface'}:${latitude}:${longitude}`;
    let surface = transitSurfaceCache.get(key);
    if (!surface) {
      const point = localPosition(latitude, longitude);
      let measured = null;
      // Reviewed deck surfaces exclude towers/cables; BGT supplies measured ground.
      const surfaceKinds = groundOnly ? ['ground', 'industrialTerrain', 'greenTerrain'] : ['bridgeSurfaces', 'industrialTerrain', 'ground', 'greenTerrain'];
      for (const kind of surfaceKinds) {
        const layer = tilesets.find(layer => layer.kind === kind);
        if (!layer?.group.visible) continue;
        const height = surfaceQueries.get(kind).heightAt(point.x, point.z, point.y - 80, point.y + 150);
        if (height !== null) { measured = { height, source: kind === 'bridgeSurfaces' ? 'surveyed bridge deck' : kind === 'industrialTerrain' ? 'survey-based reclaimed ground' : 'surveyed ground' }; break; }
      }
      surface = { point, ...(measured || { height: point.y, source: 'graphic surface height' }) };
      transitSurfaceCache.set(key, surface);
    }
    const projected = new THREE.Vector3(surface.point.x, surface.height + offsetMetres, surface.point.z);
    projected.userData = { surfaceSource: surface.source, measured: surface.source !== 'graphic surface height' };
    return projected;
  }
  const transit = createTransitView({ project: projectTransit, requestRender });
  scene.add(transit.group);
  const traffic = createSimulatedTraffic({ project: projectTransit, requestRender });
  const cyclists = createSimulatedTraffic({ project: projectTransit, requestRender, bicycles: true, maximumVehicles: 160, vehiclesPerKilometre: 20, maximumSpan: 2600 });
  const simulatedLayers = [traffic, cyclists];
  const simulationMaterials = new Set();
  for (const layer of simulatedLayers) {
    scene.add(layer.group);
    layer.group.traverse(object => {
      if (!object.isMesh) return;
      object.castShadow = false;
      for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
        // Bicycle frames and wheels share a material; wrap its shader only once.
        if (!simulationMaterials.has(material)) {
          simulationMaterials.add(material); applyMetroCutaway(material, cutawayUniforms);
        }
      }
    });
  }
  let trafficState = 'loading', cyclistsState = 'loading', lastTrafficFrame = 0, trafficProjectionDirty = false, lastTrafficProjection = 0;
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  function pauseTraffic() { for (const layer of simulatedLayers) layer.setPaused(document.hidden || reducedMotion.matches); }
  document.addEventListener('visibilitychange', pauseTraffic); reducedMotion.addEventListener('change', pauseTraffic); pauseTraffic();
  const trafficReady = traffic.load().then(() => { trafficState = 'ready'; requestRender(); }).catch(error => { trafficState = 'error'; console.warn('010: simulated road traffic unavailable', error); throw error; });
  trafficReady.catch(() => {});
  const cyclistsReady = cyclists.load('./data/traffic/cycleways-wkd.pb.gz').then(() => { cyclistsState = 'ready'; requestRender(); }).catch(error => { cyclistsState = 'error'; console.warn('010: simulated cyclists unavailable', error); throw error; });
  cyclistsReady.catch(() => {});
  let metroState = 'loading';
  const metroReady = transit.loadMetro().then(() => {
    metroState = 'ready';
    const corridor = transit.getCutaway();
    cutawayUniforms.mask.value = corridor.texture;
    cutawayUniforms.bounds.value = corridor.bounds;
    cutawayUniforms.projection.value = corridor.projection;
    requestRender();
  }).catch(error => { metroState = 'error'; console.warn('010: metro plan unavailable', error); throw error; });
  // UI consumes this rejection through the public method below.
  metroReady.catch(() => {});
  function updateTransit(snapshot) {
    if (disposed) return;
    const previous = transitSnapshot;
    transitSnapshot = snapshot;
    if (snapshot.sources?.ndov?.receivedAt !== previous.sources?.ndov?.receivedAt || snapshot.sources?.ns?.receivedAt !== previous.sources?.ns?.receivedAt) transitSurfaceCache.clear();
    transit.update(snapshot);
  }
  function setMetroCutaway(enabled) {
    if (metroState !== 'ready') return false;
    transit.setCutaway({ enabled });
    cutawayUniforms.enabled.value = enabled ? 1 : 0;
    renderer.shadowMap.needsUpdate = true;
    requestRender();
    return true;
  }
  const tileCaches = Object.fromEntries([['city', appearanceEdition === 'illustrated-row' ? 384 : 224], ['trees', 128], ['lights', 24]].map(([name, megabytes]) => {
    const cache = new LRUCache();
    cache.maxBytesSize = megabytes * 1024 * 1024;
    cache.minBytesSize = name === 'trees' ? 24 * 1024 * 1024 : cache.maxBytesSize * 0.8;
    return [name, cache];
  }));
  const overview = new THREE.Group();
  scene.add(overview);

  function requestRender() { needsRender = true; if (!scheduledFrame && !disposed) scheduledFrame = requestAnimationFrame(frame); }
  function scheduleDeferredUpdate(delay) {
    clearTimeout(deferredUpdateTimer);
    deferredUpdateTimer = setTimeout(() => { deferredUpdateTimer = null; requestRender(); }, delay);
  }
  function markGestureInput() {
    gestureQuietUntil = performance.now() + 120;
    scheduleDeferredUpdate(121);
  }
  function viewReadiness() {
    let pending = Number(overviewState === 'loading') + Number(contextState === 'loading') + Number(viewUpdateDeferred);
    let failed = overviewState === 'error' || contextState === 'error';
    let refused = 0;
    for (const tiles of tilesets) {
      if (!tiles.group.visible) continue;
      pending += tiles.stats.queued + tiles.stats.downloading + tiles.stats.parsing;
      refused += tiles.stats.refused;
      if (tiles.rootLoadingState !== LOADED) pending++;
      failed ||= tiles.rootLoadingState === FAILED;
      for (const tile of tiles.usedSet) {
        if (tile.traversal.inFrustum && tile.internal.loadingState === FAILED && (tile.traversal.isLeaf || tile.internal.hasUnrenderableContent)) failed = true;
      }
    }
    return { pending, refused, failed, ready: !pending && !refused && !failed };
  }
  function reportStatus() {
    const { pending, failed, ready } = viewReadiness();
    const state = failed ? 'error' : ready ? 'ready' : 'loading';
    const message = failed ? 'Some city detail is unavailable. You can keep exploring.' : ready ? 'Rotterdam, in miniature' : 'Bringing Rotterdam into view…';
    const key = `${state}:${loadedTiles}:${pending}`;
    if (key !== lastStatus) { lastStatus = key; onStatus({ state, message, loadedTiles, loadingTiles: pending }); }
  }
  function visibleTankAppearanceModels() {
    const layer = tilesets.find(tiles => tiles.kind === 'appearanceTanks');
    return layer?.group.visible ? [...layer.visibleTiles].map(tile => tile.engineData.scene).filter(Boolean) : [];
  }
  function colorModel(model, kind) {
    if (kind === 'appearanceBuildings' || kind === 'appearanceTanks') {
      prepareAppearanceModel(model, {
        night: uniforms.night,
        applyLighting: material => fixtureSurfaceLighting.apply(material),
        applyCutaway: material => applyMetroCutaway(material, cutawayUniforms),
      });
      setAppearanceSampling([model], { renderer, preset: appearanceSamplingPreset });
      bindCutawayShadows(model);
      return;
    }
    if (kind === 'ground') model.userData.groundHeightFilter = omitInvalidGroundTriangles(model);
    model.traverse(mesh => {
      if (kind === 'lamps') {
        if (mesh.isPoints) mesh.material = mesh.userData.objectKind === 'lampPools' ? lampPoolMaterial : lampGlowMaterial;
        if (mesh.isLineSegments) mesh.material = lampShaftMaterial;
        return;
      }
      if (!mesh.isMesh) return;
      if (kind === 'industrialStructures') {
        mesh.material = materials[kind]; mesh.castShadow = true; mesh.receiveShadow = true; return;
      }
      const position = mesh.geometry.getAttribute('position');
      const batchIds = mesh.geometry.getAttribute('_batchid');
      const table = batchTableFor(mesh);
      const colors = new Float32Array(position.count * 3);
      const cachedColors = new Map();
      for (let index = 0; index < position.count; index++) {
        const batchId = batchIds ? batchIds.getX(index) : 0;
        let color = cachedColors.get(batchId);
        if (!color) {
          let attributes = {};
          if (table && batchIds) { try { attributes = table.getDataFromId(batchId)?.attributes || {}; } catch {} }
          color = ['streets', 'bridgeSurfaces', 'greenTerrain'].includes(kind) ? streetColor(mesh.userData.surfaceKind) : ['yards', 'industrialTerrain'].includes(kind) ? yardColor(mesh.userData.surfaceKind) : featureColor(kind, attributes, `${batchId}:${Math.round(position.getX(index))}:${Math.round(position.getZ(index))}`);
          cachedColors.set(batchId, color);
        }
        color.toArray(colors, index * 3);
      }
      mesh.geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
      mesh.material = materials[kind];
      mesh.castShadow = !['ground', 'greenTerrain', 'industrialTerrain', 'streets', 'yards', 'bridgeSurfaces'].includes(kind);
      mesh.receiveShadow = true;
      if (kind === 'streets') mesh.renderOrder = -10;
      if (kind === 'yards') mesh.renderOrder = -11;
    });
    if (['ground', 'streets', 'bridgeSurfaces', 'greenTerrain', 'industrialTerrain', 'yards'].includes(kind)) publicSpaceStyle.addModel(model);
    if (!['bridges', 'bridgeSurfaces'].includes(kind)) bindCutawayShadows(model);
    if (kind === 'buildings') { buildingAppearance.addModel(model); buildingBatches.addModel(model); }
    if (kind === 'tanks' && tankAppearanceEnabled) tankAppearance.addModel(model);
    if (kind === 'trees' && vegetationEnabled) vegetationStyle.addModel(model);
    if (kind === 'trees' || kind === 'lights') objectDetail.addModel(model);
    if (kind === 'trees') treeBatches.addModel(model);
  }

  for (const [kind, id] of LAYERS) {
    if (kind === 'appearanceTanks' && !tankAppearanceEnabled) continue;
    const layerSource = kind === 'appearanceBuildings' && appearanceEdition === 'illustrated-row' ? './data/illustrated-row/tileset.json' : kind === 'appearanceBuildings' && appearanceEdition === 'current' ? './data/current-building-appearance/tileset.json' : id;
    const tiles = new TilesRenderer(layerSource.startsWith('./') ? layerSource : `${DATA_BASE}${layerSource}/tileset.json`);
    tiles.registerPlugin(createCompressedModelsPlugin());
    tiles.kind = kind;
    if (['buildings', 'appearanceBuildings', 'appearanceTanks'].includes(kind)) tiles.registerPlugin({
      name: 'Reach the first available building geometry',
      preprocessNode(tile) {
        if (!tile.internal.hasContent && tile.children?.length) tile.geometricError = Infinity;
      },
    });
    tiles.loadSiblings = false;
    tiles.loadAncestors = false;
    // Appearance levels encode source texel spacing in metres. Request detail
    // when its source samples would otherwise become larger than a screen pixel.
    tiles.errorTarget = ['appearanceBuildings', 'appearanceTanks'].includes(kind) ? 1 : ['buildings', 'industrialStructures'].includes(kind) ? 8 : 0;
    tiles.setCamera(camera);
    tiles.group.matrixAutoUpdate = false;
    tiles.group.matrix.copy(earthToLocal);
    if (tilesets.length) {
      tiles.downloadQueue = tilesets[0].downloadQueue;
      tiles.parseQueue = tilesets[0].parseQueue;
      tiles.processNodeQueue = tilesets[0].processNodeQueue;
    } else {
      tiles.downloadQueue.maxJobsPerOrigin = 10;
      tiles.parseQueue.maxJobs = 2;
    }
    const originalCache = tiles.lruCache;
    tiles.lruCache = tileCaches[kind] || tileCaches.city;
    tiles.lruCache.unloadPriorityCallback = originalCache.unloadPriorityCallback;
    tiles.addEventListener('load-model', event => { colorModel(event.scene, kind); if (['ground', 'bridgeSurfaces', 'greenTerrain', 'industrialTerrain'].includes(kind)) transitSurfaceDirty = true; if (kind === 'ground') sourceFusion.addGround(event.scene); loadedTiles++; renderer.shadowMap.needsUpdate = true; requestRender(); });
    if (['ground', 'bridgeSurfaces', 'greenTerrain', 'industrialTerrain'].includes(kind)) tiles.addEventListener('dispose-model', () => { transitSurfaceDirty = true; });
    if (kind === 'buildings') tiles.addEventListener('dispose-model', event => { buildingAppearance.removeModel(event.scene); buildingBatches.removeModel(event.scene); });
    if (kind === 'tanks') tiles.addEventListener('dispose-model', event => tankAppearance.removeModel(event.scene));
    if (kind === 'appearanceTanks') tiles.addEventListener('dispose-model', requestRender);
    if (kind === 'ground') tiles.addEventListener('dispose-model', event => sourceFusion.removeGround(event.scene));
    if (['ground', 'streets', 'bridgeSurfaces', 'greenTerrain', 'industrialTerrain', 'yards'].includes(kind)) tiles.addEventListener('dispose-model', event => publicSpaceStyle.removeModel(event.scene));
    if (kind === 'trees' || kind === 'lights') tiles.addEventListener('dispose-model', event => { if (kind === 'trees') treeBatches.removeModel(event.scene); objectDetail.removeModel(event.scene); if (kind === 'trees') vegetationStyle.removeModel(event.scene); });
    for (const event of ['load-tileset', 'needs-update', 'tile-visibility-change', 'tiles-load-end']) tiles.addEventListener(event, requestRender);
    tiles.addEventListener('load-error', event => {
      loadErrors++; console.warn(`010: ${kind} tile could not load`, event.error);
      const attempts = failedTileRetries.get(event.url) || 0;
      if (attempts < 2) { failedTileRetries.set(event.url, attempts + 1); setTimeout(() => { if (!disposed) { tiles.resetFailedTiles(); requestRender(); } }, 1500 * (attempts + 1)); }
      requestRender();
    });
    scene.add(tiles.group);
    tilesets.push(tiles);
  }
  // A source appearance is optional until its complete tile is resident. Load
  // the city underneath first so texture arrivals cannot starve its ground.
  const layerPriority = { buildings: 7, appearanceBuildings: -1, appearanceTanks: -1, lamps: 6, streets: 6, yards: 5, industrialTerrain: 5, ground: 5, greenTerrain: 5, industrialStructures: 3, bridges: 4, bridgeSurfaces: 3, tanks: 2, lights: 1, trees: 0 };
  const prioritizeCitySurfaces = (a, b) => {
    const firstLayer = a.internal?.renderer?.kind, secondLayer = b.internal?.renderer?.kind;
    if (firstLayer && secondLayer && firstLayer !== secondLayer) return layerPriority[firstLayer] - layerPriority[secondLayer];
    return unifiedPriorityCallback(a, b);
  };
  tilesets[0].downloadQueue.priorityCallback = prioritizeCitySurfaces;
  tilesets[0].parseQueue.priorityCallback = prioritizeCitySurfaces;
  async function loadOverview() {
    const palette = { context: '#b5bfad', water: '#367b86', farmland: '#a6af7b', forest: '#678368', grass: '#869c72', land: '#b7baa2', urban: '#b9b7a6', sand: '#d7c8a4' };
    const positionsByKind = new Map();
    const cartographicDrawOrder = { context: -29, land: -28, urban: -27, farmland: -26, grass: -25, forest: -24, sand: -23, water: -22 };
    function addPolygon(rings, kind, height) {
      const contours = rings.map(ring => ring.slice(0, -1).map(([lon, lat]) => localPosition(lat, lon, height)));
      if (!contours[0] || contours[0].length < 3) return;
      const polygon = contours[0].map(point => new THREE.Vector2(point.x, point.z));
      const holes = contours.slice(1).map(ring => ring.map(point => new THREE.Vector2(point.x, point.z)));
      const points = contours.flat();
      const faces = THREE.ShapeUtils.triangulateShape(polygon, holes);
      if (!positionsByKind.has(kind)) positionsByKind.set(kind, []);
      const positions = positionsByKind.get(kind);
      const pendingTriangles = faces.map(face => face.map(index => points[index]));
      while (pendingTriangles.length) {
        const triangle = pendingTriangles.pop();
        const edgeLengths = triangle.map((point, index) => point.distanceToSquared(triangle[(index + 1) % 3]));
        const longestEdge = edgeLengths.indexOf(Math.max(...edgeLengths));
        if (edgeLengths[longestEdge] > 1200 * 1200) {
          const a = triangle[longestEdge], b = triangle[(longestEdge + 1) % 3], c = triangle[(longestEdge + 2) % 3];
          const geographicMidpoint = geographicPosition(a.clone().add(b).multiplyScalar(0.5));
          const midpoint = localPosition(geographicMidpoint.lat, geographicMidpoint.lon, height);
          pendingTriangles.push([a, midpoint, c], [midpoint, b, c]);
        } else {
          for (const point of triangle) positions.push(point.x, point.y, point.z);
        }
      }
    }
    function addFeatures(collection, base = false, context = false) {
      for (const feature of collection.features) {
        const kind = context ? 'context' : base ? 'land' : feature.properties.kind || 'land';
        const heights = { land: -2.7, urban: -2.4, farmland: -2.1, grass: -1.8, forest: -1.5, sand: -1.2, water: -0.9 };
        const height = context ? -3.2 : base ? -3.0 : heights[kind] ?? -2.4;
        const polygons = feature.geometry.type === 'Polygon' ? [feature.geometry.coordinates] : feature.geometry.type === 'MultiPolygon' ? feature.geometry.coordinates : [];
        for (const polygon of polygons) addPolygon(polygon, kind, height);
      }
    }
    async function fetchCollection(name) {
      const response = await fetch(`./data/${name}`);
      if (!response.ok) throw new Error(`${name} could not load.`);
      return response.json();
    }
    function drawCollectedSurfaces() {
      for (const [kind, positions] of positionsByKind) {
        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
        geometry.computeVertexNormals();
        const color = new THREE.Color(palette[kind] || palette.land), vertexColors = new Float32Array(positions.length);
        for (let index = 0; index < vertexColors.length; index += 3) color.toArray(vertexColors, index);
        geometry.setAttribute('color', new THREE.BufferAttribute(vertexColors, 3));
        const mesh = new THREE.Mesh(geometry, kind === 'context' ? contextLandMaterial : cartographicMaterial); mesh.receiveShadow = true; mesh.renderOrder = cartographicDrawOrder[kind] ?? -28;
        overview.add(mesh);
      }
      positionsByKind.clear();
      renderer.shadowMap.needsUpdate = true;
      requestRender();
    }
    fetchCollection('context-land.json').then(collection => {
      if (disposed) return;
      addFeatures(collection, false, true);
      drawCollectedSurfaces();
      contextState = 'ready';
      requestRender();
    }).catch(error => { contextState = 'error'; console.warn('010: surrounding context could not load', error); requestRender(); });
    const collections = await Promise.all([municipalityData, fetchCollection('overview.json')]);
    if (disposed) return;
    addFeatures(collections[0], true);
    addFeatures(collections[1]);
    drawCollectedSurfaces();
    overviewState = 'ready';
    renderer.shadowMap.needsUpdate = true;
    requestRender();
  }
  loadOverview().catch(error => { overviewState = 'error'; console.warn('010: overview could not load', error); requestRender(); });

  function updateCamera() {
    const aspect = width / height;
    lampPixelsPerMetre.value = height * renderer.getPixelRatio() / view.span;
    glowUniforms.size.value = Math.max(1.5, Math.min(6, 6 * height / view.span));
    camera.left = -view.span * aspect / 2;
    camera.right = view.span * aspect / 2;
    camera.top = view.span / 2;
    camera.bottom = -view.span / 2;
    const bearing = view.bearing * DEGREES, distance = 40000;
    camera.position.copy(target).add(new THREE.Vector3(Math.sin(bearing), 1 / Math.sqrt(2), Math.cos(bearing)).normalize().multiplyScalar(distance));
    camera.lookAt(target);
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld();
    updateShadowCamera();
    fixtureSurfaceLighting.setView(camera);
    transit.setView({ camera, span: view.span, viewportHeight: height * renderer.getPixelRatio() });
    for (const layer of simulatedLayers) layer.setView({ camera, span: view.span, viewportHeight: height * renderer.getPixelRatio() });
    const drawingSize = renderer.getDrawingBufferSize(new THREE.Vector2());
    for (const tiles of tilesets) tiles.setResolution(camera, drawingSize.x, drawingSize.y);
    requestRender();
  }
  function updateShadowCamera() {
    const radius = Math.min(18000, view.span * Math.max(1.1, width / height) * 0.72);
    sun.target.position.copy(target);
    sun.position.copy(target).addScaledVector(sunVector, 20000);
    Object.assign(sun.shadow.camera, { left: -radius, right: radius, top: radius, bottom: -radius });
    sun.shadow.camera.updateProjectionMatrix();
    renderer.shadowMap.needsUpdate = true;
  }
  function frame() {
    scheduledFrame = null;
    const precipitation = weatherUniforms.rain.value > 0 || weatherUniforms.snow.value > 0;
    const animateTraffic = !capturingFullDetail && !capturePending && simulatedLayers.some(layer => {
      const stats = layer.statistics();
      return !stats.paused && layer.group.visible && stats.vehicles > 0;
    });
    if (disposed || !needsRender && !precipitation && !animateTraffic) return;
    const now = performance.now();
    if (animateTraffic && now - lastTrafficFrame >= 1000 / 30) {
      lastTrafficFrame = now;
      for (const layer of simulatedLayers) layer.advance(now / 1000);
    }
    if (!needsRender && !precipitation) { scheduledFrame = requestAnimationFrame(frame); return; }
    const renderingCity = needsRender;
    if (!needsRender && now - lastPresentation < 32) { scheduledFrame = requestAnimationFrame(frame); return; }
    if (needsRender) {
    needsRender = false;
    scene.updateMatrixWorld(true);
    const deferViewUpdates = !capturingFullDetail && !capturePending && (pointers.size > 0 || now < gestureQuietUntil);
    viewUpdateDeferred = deferViewUpdates;
    if (!deferViewUpdates) {
    for (const tiles of tilesets) {
      const visible = tiles.kind === 'appearanceTanks' ? tankAppearanceEnabled && view.span < 2400 : tiles.kind === 'appearanceBuildings' ? appearanceEnabled && view.span < 2400 : tiles.kind === 'streets' ? true : tiles.kind === 'lamps' ? uniforms.night.value > 0.1 : tiles.kind === 'ground' ? view.span < 1400 : tiles.kind === 'greenTerrain' ? view.span >= 1400 && view.span < 12000 : ['industrialStructures', 'industrialTerrain'].includes(tiles.kind) ? view.span < 18000 : tiles.kind === 'trees' ? view.span < 3500 : tiles.kind === 'lights' ? view.span < 700 && uniforms.night.value > 0.1 : ['bridges', 'bridgeSurfaces'].includes(tiles.kind) ? view.span < 12000 : tiles.kind === 'tanks' ? view.span < 18000 : true;
      if (!visible && tiles.group.visible) {
        for (const tile of tiles.usedSet) tiles.lruCache.markUnused(tile);
        tiles.lruCache.scheduleUnload();
      }
      tiles.group.visible = visible;
      if (visible) tiles.update();
    }
    const appearanceLayer = tilesets.find(tiles => tiles.kind === 'appearanceBuildings');
    if (buildingAppearance.setVisibleModels(appearanceLayer.group.visible ? [...appearanceLayer.visibleTiles].map(tile => tile.engineData.scene).filter(Boolean) : [])) renderer.shadowMap.needsUpdate = true;
    if (tankAppearance.setVisibleModels(visibleTankAppearanceModels())) renderer.shadowMap.needsUpdate = true;
    if (tilesets.find(tiles => tiles.kind === 'ground').group.visible) {
      sourceFusion.setVisibleBridges(tilesets.filter(tiles => tiles.kind === 'bridges' && tiles.group.visible).flatMap(tiles => [...tiles.visibleTiles].map(tile => tile.engineData.scene).filter(Boolean)));
      if (sourceFusion.update()) renderer.shadowMap.needsUpdate = true;
    }
    for (const [kind, query] of surfaceQueries) {
      const layer = tilesets.find(tiles => tiles.kind === kind);
      const models = layer.group.visible ? [...layer.visibleTiles].map(tile => tile.engineData.scene).filter(Boolean) : [];
      if (query.setModels(models)) transitSurfaceDirty = true;
    }
    if (transitSurfaceDirty) {
      transitSurfaceDirty = false;
      transitSurfaceCache.clear();
      transit.update(transitSnapshot);
      trafficProjectionDirty = true;
    }
    if (trafficProjectionDirty && viewReadiness().ready && now - lastTrafficProjection > 1500) {
      trafficProjectionDirty = false; lastTrafficProjection = now;
      for (const layer of simulatedLayers) layer.refreshProjection();
    } else if (trafficProjectionDirty && viewReadiness().ready) {
      scheduleDeferredUpdate(Math.max(1, 1501 - (now - lastTrafficProjection)));
    }
    }
    const sectionModels = tilesets.filter(layer => ['buildings', 'appearanceBuildings'].includes(layer.kind) && layer.group.visible).flatMap(layer => [...layer.visibleTiles].map(tile => tile.engineData.scene).filter(Boolean));
    if (metroCityCut.update(sectionModels, transit.getSectionGeometry())) renderer.shadowMap.needsUpdate = true;
    const reflectCity = uniforms.night.value > 0.1 && view.span < 6500;
    if (reflectCity) {
      reflectionCamera.copy(camera);
      const waterPlaneHeight = localPosition(view.lat, view.lon, -0.9).y;
      reflectionCamera.position.y = 2 * waterPlaneHeight - camera.position.y;
      reflectionCamera.up.set(0, -1, 0);
      reflectionCamera.lookAt(target.x, 2 * waterPlaneHeight - target.y, target.z);
      reflectionCamera.updateMatrixWorld();
      uniforms.reflectionMatrix.value.multiplyMatrices(reflectionCamera.projectionMatrix, reflectionCamera.matrixWorldInverse);
    }
    sun.shadow.updateMatrices(sun);
    const detail = objectDetail.update(camera, renderer.getDrawingBufferSize(new THREE.Vector2()).y, { fullDetail: capturingFullDetail, cullingCameras: reflectCity ? [camera, reflectionCamera, sun.shadow.camera] : [camera, sun.shadow.camera] });
    if (detail.changed) renderer.shadowMap.needsUpdate = true;
    if (detail.pending) requestRender();
    const treeLayer = tilesets.find(tiles => tiles.kind === 'trees');
    treeBatches.update(new Set(treeLayer.group.visible ? [...treeLayer.visibleTiles].map(tile => tile.engineData.scene) : []));
    for (const layer of tilesets.filter(tiles => tiles.kind === 'lamps')) for (const tile of layer.visibleTiles) tile.engineData.scene?.traverse(object => { if (object.isLineSegments) object.visible = (object.userData.illustratedPole || view.span >= 700) && view.span < 3500; });
    if (reflectCity) {
      const background = scene.background; scene.background = new THREE.Color(0x000000);
      const groundLayer = tilesets.find(layer => layer.kind === 'ground');
      const groundVisible = groundLayer.group.visible; groundLayer.group.visible = false; overview.visible = false; sea.visible = false;
      renderer.setRenderTarget(reflectionTarget); renderer.render(scene, reflectionCamera); renderer.setRenderTarget(null);
      groundLayer.group.visible = groundVisible; overview.visible = true; sea.visible = true; scene.background = background;
    }
    renderer.setRenderTarget(cityTarget); renderer.render(scene, camera); lastCityRender = { ...renderer.info.render }; renderer.setRenderTarget(null);
    if (loadMilestones.firstBuildingsSubmittedMs === null && tilesets.find(tiles => tiles.kind === 'buildings').visibleTiles.size) loadMilestones.firstBuildingsSubmittedMs = performance.now();
    if (loadMilestones.initialDetailSettledMs === null && viewReadiness().ready) loadMilestones.initialDetailSettledMs = performance.now();
    reportStatus();
    }
    weatherUniforms.time.value = now / 1000;
    renderer.render(presentationScene, presentationCamera); lastPresentation = now;
    const submitted = performance.now();
    if (renderingCity) recordTiming(frameTimes, submitted - now);
    if (latestInputTime !== null) { recordTiming(inputRenderTimes, submitted - latestInputTime); latestInputTime = null; }
    if ((needsRender || precipitation || animateTraffic) && !scheduledFrame) scheduledFrame = requestAnimationFrame(frame);
  }
  function setView(nextView, notify = true) {
    view.lat = THREE.MathUtils.clamp(Number(nextView.lat ?? view.lat), 51.80, 52.05);
    view.lon = THREE.MathUtils.clamp(Number(nextView.lon ?? view.lon), 3.88, 4.66);
    view.span = clampViewSpan(nextView.span ?? view.span, view.span);
    view.bearing = Number(nextView.bearing ?? view.bearing);
    target.copy(localPosition(view.lat, view.lon));
    updateCamera();
    if (notify) onViewChange({ ...view });
  }
  function setLighting(nextLighting) {
    lighting = { ...lighting, ...nextLighting };
    const mode = lighting.mode;
    const solar = solarDirection(new Date(lighting.date), view.lat, view.lon);
    const night = mode === 'night' ? 1 : mode === 'live' ? 1 - THREE.MathUtils.smoothstep(solar.altitude / DEGREES, -5, 8) : 0;
    const golden = mode === 'golden' || mode === 'live' && solar.altitude > 0 && solar.altitude < 13 * DEGREES;
    const cloud = Math.min(1, Math.max(0, Number(lighting.cloudCover) / 100));
    uniforms.night.value = night;
    fixtureSurfaceLighting.setView(camera);
    uniforms.snow.value = Math.min(1, Number(lighting.snow) || 0);
    sunVector = mode === 'live' && night < 0.9 ? solar.direction : golden ? new THREE.Vector3(-0.9, 0.24, 0.34).normalize() : night ? new THREE.Vector3(-0.5, 0.75, -0.45).normalize() : new THREE.Vector3(-0.65, 0.8, 0.45).normalize();
    applyMiniatureLighting({ sun, sky, background: scene.background }, { night, golden, cloud });
    const wetness = Math.min(1, Number(lighting.rain) || 0);
    weatherUniforms.rain.value = wetness > 0 ? Math.max(0.2, wetness) : 0;
    weatherUniforms.snow.value = Math.min(1, Number(lighting.snow) || 0);
    materials.ground.roughness = 0.94 - wetness * 0.35;
    materials.ground.color.setScalar(1 - wetness * 0.13);
    cartographicMaterial.color.copy(materials.ground.color); cartographicMaterial.roughness = materials.ground.roughness;
    contextLandMaterial.color.copy(cartographicMaterial.color).multiplyScalar(0.72 - night * 0.27);
    contextLandMaterial.roughness = cartographicMaterial.roughness;
    renderer.toneMappingExposure = night > 0.5 ? 1.35 : 1.12;
    updateShadowCamera();
    requestRender();
  }
  function setRenderDimensions(nextWidth, nextHeight, pixelRatio) {
    width = nextWidth; height = nextHeight;
    renderer.setPixelRatio(pixelRatio);
    renderer.setSize(Math.round(width), Math.round(height), false);
    const drawingSize = renderer.getDrawingBufferSize(new THREE.Vector2());
    reflectionTarget.setSize(Math.round(drawingSize.x / 2), Math.round(drawingSize.y / 2));
    uniforms.reflectionTexel.value.set(1 / reflectionTarget.width, 1 / reflectionTarget.height);
    cityTarget.setSize(drawingSize.x, drawingSize.y);
    weatherUniforms.resolution.value.set(width, height);
    updateCamera();
  }
  function resize() {
    const bounds = canvas.getBoundingClientRect();
    setRenderDimensions(Math.max(1, bounds.width), Math.max(1, bounds.height), Math.min(window.devicePixelRatio || 1, 2));
  }
  let capturePending = false;
  async function captureCanvas(captureWidth, captureHeight) {
    if (capturePending) throw new Error('An image is already being rendered.');
    if (disposed) throw new Error('The city view has closed.');
    if (!Number.isInteger(captureWidth) || !Number.isInteger(captureHeight) || captureWidth < 1 || captureHeight < 1 || Math.max(captureWidth, captureHeight) > renderer.capabilities.maxTextureSize) throw new Error('The requested image size is not supported by this device.');
    capturePending = true;
    const previousTreeCacheLimit = tileCaches.trees.maxBytesSize;
    const previousLightCacheLimit = tileCaches.lights.maxBytesSize;
    tileCaches.trees.maxBytesSize = Math.max(previousTreeCacheLimit, 64 * 1024 * 1024);
    tileCaches.lights.maxBytesSize = Math.max(previousLightCacheLimit, 64 * 1024 * 1024);
    const captureView = { ...view }, captureTarget = target.clone(), captureCamera = camera.clone();
    const captureAspect = captureWidth / captureHeight;
    captureCamera.left = -captureView.span * captureAspect / 2;
    captureCamera.right = captureView.span * captureAspect / 2;
    captureCamera.updateProjectionMatrix(); captureCamera.updateMatrixWorld();
    for (const tiles of tilesets) { tiles.setCamera(captureCamera); tiles.setResolution(captureCamera, captureWidth, captureHeight); }
    try {
      const started = performance.now();
      let settledFrames = 0;
      while (settledFrames < 3) {
        if (disposed) throw new Error('The city view has closed.');
        scene.updateMatrixWorld(true);
        for (const tiles of tilesets) if (tiles.group.visible) tiles.update();
        settledFrames = viewReadiness().ready && loadedTiles > 0 ? settledFrames + 1 : 0;
        if (performance.now() - started > 20000) throw new Error('City detail is still loading. Please try exporting again shortly.');
        await new Promise(resolve => requestAnimationFrame(resolve));
      }
      await fixtureSurfaceLighting.prepareView(captureCamera);
      const liveView = { ...view }, liveTarget = target.clone();
      try {
        Object.assign(view, captureView); target.copy(captureTarget);
        setRenderDimensions(captureWidth, captureHeight, 1);
        capturingFullDetail = true;
        if (scheduledFrame) cancelAnimationFrame(scheduledFrame);
        scheduledFrame = null; needsRender = true; frame();
        const output = document.createElement('canvas');
        output.width = captureWidth; output.height = captureHeight;
        const context = output.getContext('2d');
        if (!context) throw new Error('The image canvas could not be created.');
        context.drawImage(canvas, 0, 0);
        return output;
      } finally {
        capturingFullDetail = false;
        Object.assign(view, liveView); target.copy(liveTarget);
        for (const tiles of tilesets) tiles.deleteCamera(captureCamera);
        resize();
        if (scheduledFrame) cancelAnimationFrame(scheduledFrame);
        scheduledFrame = null; needsRender = true; frame();
      }
    } finally {
      for (const tiles of tilesets) tiles.deleteCamera(captureCamera);
      tileCaches.trees.maxBytesSize = previousTreeCacheLimit;
      tileCaches.lights.maxBytesSize = previousLightCacheLimit;
      tileCaches.trees.scheduleUnload();
      tileCaches.lights.scheduleUnload();
      capturePending = false;
      requestRender();
    }
  }
  const pointers = new Map();
  let drag = null, pointerStart = null;
  function groundAt(clientX, clientY) {
    const bounds = canvas.getBoundingClientRect();
    const ray = new THREE.Raycaster();
    ray.setFromCamera(new THREE.Vector2((clientX - bounds.left) / bounds.width * 2 - 1, 1 - (clientY - bounds.top) / bounds.height * 2), camera);
    return ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), 0), new THREE.Vector3());
  }
  function pointerDown(event) {
    if (![0, 2].includes(event.button) && event.pointerType !== 'touch') return;
    markGestureInput();
    pointerStart = pointers.size ? null : { x: event.clientX, y: event.clientY, button: event.button };
    canvas.setPointerCapture(event.pointerId);
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    drag = { rotating: event.button === 2, startX: event.clientX, bearing: view.bearing, point: groundAt(event.clientX, event.clientY), target: target.clone(), distance: pointers.size === 2 ? pointerDistance() : null, span: view.span };
    canvas.style.cursor = 'grabbing';
  }
  function pointerDistance() { const [a, b] = [...pointers.values()]; return Math.hypot(a.x - b.x, a.y - b.y); }
  function pointerMove(event) {
    if (!pointers.has(event.pointerId)) return;
    markGestureInput();
    latestInputTime = event.timeStamp;
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (drag.rotating) { setView({ bearing: drag.bearing + (event.clientX - drag.startX) * 0.25 });
    } else if (pointers.size === 2 && drag.distance) {
      setView({ span: drag.span * drag.distance / pointerDistance() });
    } else if (drag.point) {
      const point = groundAt(event.clientX, event.clientY);
      if (point) { target.add(drag.point.clone().sub(point)); const geo = geographicPosition(target); setView(geo); }
    }
  }
  function pointerUp(event) {
    if (event.type === 'pointerup' && pointerStart && pointerStart.button === 0 && Math.hypot(event.clientX - pointerStart.x, event.clientY - pointerStart.y) < 6) {
      const bounds = canvas.getBoundingClientRect(), ray = new THREE.Raycaster();
      ray.setFromCamera(new THREE.Vector2((event.clientX - bounds.left) / bounds.width * 2 - 1, 1 - (event.clientY - bounds.top) / bounds.height * 2), camera);
      const report = transit.pick(ray);
      if (report) report.presentation.surfacePlacement = transitSurfaceCache.get(`${report.latitude}:${report.longitude}`)?.source || 'graphic surface height';
      onTransitSelect(report);
    }
    pointerStart = null;
    pointers.delete(event.pointerId); drag = null; pointers.clear(); canvas.style.cursor = 'grab'; markGestureInput(); }
  function wheel(event) {
    markGestureInput();
    latestInputTime = event.timeStamp;
    event.preventDefault();
    const anchor = groundAt(event.clientX, event.clientY);
    setView({ span: view.span * Math.exp(Math.max(-200, Math.min(200, event.deltaY)) * 0.0022) }, false);
    const shifted = groundAt(event.clientX, event.clientY);
    if (anchor && shifted) target.add(anchor.sub(shifted));
    setView(geographicPosition(target));
  }
  function doubleClick(event) { const point = groundAt(event.clientX, event.clientY); if (point) setView({ ...geographicPosition(point), span: view.span / 1.8 }); }
  canvas.style.touchAction = 'none'; canvas.style.cursor = 'grab'; canvas.style.imageRendering = 'pixelated';
  canvas.addEventListener('pointerdown', pointerDown);
  canvas.addEventListener('pointermove', pointerMove);
  canvas.addEventListener('pointerup', pointerUp);
  canvas.addEventListener('pointercancel', pointerUp);
  canvas.addEventListener('wheel', wheel, { passive: false });
  canvas.addEventListener('dblclick', doubleClick);
  const contextMenu = event => event.preventDefault(); canvas.addEventListener('contextmenu', contextMenu);
  const observer = new ResizeObserver(resize); observer.observe(canvas);
  resize(); setLighting(lighting); reportStatus();
  function groundHeightDiagnostics(tiles) {
    if (tiles.kind !== 'ground') return undefined;
    const counts = { models: 0, parentedModels: 0, sourceTriangles: 0, missingHeightTriangles: 0, interpolatedMissingHeightTriangles: 0, verticalSkirtTriangles: 0, sourceHeightRangeMetres: [Infinity, -Infinity] };
    tiles.traverse(tile => {
      const filtered = tile.engineData?.scene?.userData.groundHeightFilter;
      if (!filtered) return;
      counts.models++; counts.parentedModels += Number(filtered.sourceHadParent);
      for (const name of ['sourceTriangles', 'missingHeightTriangles', 'interpolatedMissingHeightTriangles', 'verticalSkirtTriangles']) counts[name] += filtered[name];
      counts.sourceHeightRangeMetres[0] = Math.min(counts.sourceHeightRangeMetres[0], filtered.sourceHeightRangeMetres[0]);
      counts.sourceHeightRangeMetres[1] = Math.max(counts.sourceHeightRangeMetres[1], filtered.sourceHeightRangeMetres[1]);
    }, null, false);
    return counts;
  }
  function reviewAppearanceSampling(preset) {
    const models = [];
    for (const layer of tilesets.filter(layer => ['appearanceBuildings', 'appearanceTanks'].includes(layer.kind))) {
      layer.traverse(tile => { if (tile.engineData?.scene) models.push(tile.engineData.scene); }, null, false);
    }
    const result = setAppearanceSampling(models, { renderer, preset });
    appearanceSamplingPreset = preset;
    requestRender();
    return { ...result, view: { ...view }, drawingSize: renderer.getDrawingBufferSize(new THREE.Vector2()).toArray(), cssSize: [canvas.clientWidth, canvas.clientHeight] };
  }
  return {
    reviewAppearanceSampling,
    trafficReady: () => trafficReady, cyclistsReady: () => cyclistsReady,
    inspectTrafficSurfaces: (options = {}) => inspectTrafficSurfaces({ samples: [...traffic.sampleVehicles(options), ...cyclists.sampleVehicles(options)], tilesets, camera, width: canvas.clientWidth, height: canvas.clientHeight }),
    updateTransit, getTransitReport: id => transit.getReport(id), setMetroCutaway, metroReady: () => metroReady, getTransitStatistics: () => ({ ...transit.statistics(), metroState }),
    setView, getView: () => ({ ...view }), setLighting, captureCanvas,
    zoom: factor => setView({ span: view.span / factor }), reset: () => setView(DEFAULT_VIEW),
    render: () => { needsRender = true; frame(); }, getCanvas: () => canvas, resize,
    getDiagnostics: () => ({ publicSpace: publicSpaceStyle.diagnostics(), tankAppearance: { enabled: tankAppearanceEnabled, ...tankAppearance.diagnostics(), textures: appearanceTextureDiagnostics(visibleTankAppearanceModels()) }, vegetation: { mode: vegetationEnabled ? 'clustered' : 'native', ...vegetationStyle.diagnostics() }, shaderErrors: shaderErrors.slice(), buildingAppearance: { edition: appearanceEdition, ...buildingAppearance.diagnostics(), textures: appearanceTextureDiagnostics([...tilesets.find(layer => layer.kind === 'appearanceBuildings').visibleTiles].map(tile => tile.engineData.scene)) }, fixtureSurfaceLighting: fixtureSurfaceLighting.diagnostics(), readiness: viewReadiness(), loadMilestones, timings: { frameSubmissionMs: timingSummary(frameTimes), inputToRenderSubmissionMs: timingSummary(inputRenderTimes) }, buildingBatches: buildingBatches.diagnostics(), treeBatches: treeBatches.diagnostics(), objectDetail: objectDetail.diagnostics(), traffic: { ...traffic.statistics(), state: trafficState }, cyclists: { ...cyclists.statistics(), state: cyclistsState }, transit: { ...transit.statistics(), metroState, cityCut: metroCityCut.diagnostics() }, sourceFusion: sourceFusion.getDiagnostics(), surfaceQueries: Object.fromEntries([...surfaceQueries].map(([kind, query]) => [kind, query.diagnostics()])), loadedTiles, loadErrors, drawingSize: renderer.getDrawingBufferSize(new THREE.Vector2()).toArray(), cacheBytes: Object.values(tileCaches).reduce((sum, cache) => sum + cache.cachedBytes, 0), caches: Object.fromEntries(Object.entries(tileCaches).map(([name, cache]) => [name, { bytes: cache.cachedBytes, full: cache.isFull(), limit: cache.maxBytesSize }])), layers: tilesets.map(tiles => ({ kind: tiles.kind, groundHeightFilter: groundHeightDiagnostics(tiles), geometry: [...tiles.visibleTiles].reduce((counts, tile) => { tile.engineData.scene?.traverseVisible(mesh => { if (mesh.isMesh) { counts.meshes++; counts.triangles += (mesh.geometry.index?.count ?? mesh.geometry.getAttribute('position')?.count ?? 0) / 3 * (mesh.isInstancedMesh ? mesh.count : 1); } }); return counts; }, { meshes: 0, triangles: 0 }), visible: tiles.visibleTiles.size, downloading: tiles.stats.downloading, parsing: tiles.stats.parsing, queued: tiles.stats.queued, refused: tiles.stats.refused })), rendering: lastCityRender, memory: renderer.info.memory }),
    dispose() {
      disposed = true; clearTimeout(deferredUpdateTimer); if (scheduledFrame) cancelAnimationFrame(scheduledFrame); observer.disconnect();
      for (const [event, handler] of [['pointerdown', pointerDown], ['pointermove', pointerMove], ['pointerup', pointerUp], ['pointercancel', pointerUp], ['wheel', wheel], ['dblclick', doubleClick], ['contextmenu', contextMenu]]) canvas.removeEventListener(event, handler);
      document.removeEventListener('visibilitychange', pauseTraffic); reducedMotion.removeEventListener('change', pauseTraffic);
      buildingBatches.dispose(); for (const layer of simulatedLayers) layer.dispose(); transit.dispose(); metroCityCut.dispose(); emptyCutawayTexture.dispose(); cutawayDepthMaterial.dispose();
      for (const query of surfaceQueries.values()) query.dispose();
      sourceFusion.dispose(); publicSpaceStyle.dispose(); treeBatches.dispose(); objectDetail.dispose(); vegetationStyle.dispose(); fixtureSurfaceLighting.dispose();
      for (const tiles of tilesets) tiles.dispose();
      for (const material of Object.values(materials)) material.dispose();
      lampGlowMaterial.dispose(); lampPoolMaterial.dispose(); lampShaftMaterial.dispose(); reflectionTarget.dispose(); cityTarget.dispose(); presentationQuad.geometry.dispose(); presentationMaterial.dispose();
      overview.traverse(object => { object.geometry?.dispose(); object.material?.dispose(); });
      sea.geometry.dispose(); sea.material.dispose(); renderer.dispose();
    },
  };
}
