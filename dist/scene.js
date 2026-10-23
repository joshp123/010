import * as THREE from 'three';
import { createCityMaterial, featureColor, streetColor, yardColor, createLampPoolMaterial } from './miniature-style.js';
import { createSourceFusion } from './source-fusion.js';
import { createObjectDetail } from './object-detail.js';
import { createTreeBatches } from './tree-batches.js';
import { TilesRenderer } from '3d-tiles-renderer';
import { LRUCache, unifiedPriorityCallback, FAILED, LOADED } from './vendor/3d-tiles-renderer/build/index.core.js';

const ORIGIN = { lat: 51.915, lon: 4.49 };
const DEFAULT_VIEW = { lat: 51.9105, lon: 4.4875, span: 1700, bearing: 35 };
const DEGREES = Math.PI / 180;
const DATA_BASE = 'https://www.3drotterdam.nl/datasource-data/';
const LAYERS = [
  ['streets', './data/streets/tileset.json'],
  ['yards', './data/industrial-ground/tileset.json'],
  ['lamps', './data/lamps/tileset.json'],
  ['buildings', '8b5d0ded-a222-4e44-bc70-2992bc2192fc'],
  ['ground', '0025cb58-e0f5-4169-bb4c-5339a3bc2a7e'],
  ['bridges', '06595036-c78e-4081-ab25-e8f88b66bc19'],
  ['bridgeSurfaces', './data/bridge-surfaces/tileset.json'],
  ['tanks', 'c70023a7-2878-41e9-bb81-a7c454bc310a'],
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

export async function createScene({ canvas, onViewChange = () => {}, onStatus = () => {} }) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
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
  const lampPoolMaterial = createLampPoolMaterial(uniforms.night, lampPixelsPerMetre);
  const lampShaftMaterial = new THREE.LineBasicMaterial({ color: '#53666a', transparent: true, opacity: 0.55 });
  const materials = Object.fromEntries(LAYERS.map(([kind]) => [kind, createCityMaterial(['streets', 'bridgeSurfaces'].includes(kind) ? 'ground' : kind, uniforms)]));
  Object.assign(materials.bridgeSurfaces, { polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 });
  const seaGeometry = new THREE.PlaneGeometry(180000, 180000, 96, 96);
  const seaVertices = seaGeometry.getAttribute('position');
  for (let i = 0; i < seaVertices.count; i++) seaVertices.setZ(i, -((seaVertices.getX(i) ** 2 + seaVertices.getY(i) ** 2) / (2 * 6371000)));
  seaGeometry.computeVertexNormals();
  const seaColors = new Float32Array(seaVertices.count * 3);
  const waterColor = streetColor('water');
  for (let index = 0; index < seaColors.length; index += 3) waterColor.toArray(seaColors, index);
  seaGeometry.setAttribute('color', new THREE.BufferAttribute(seaColors, 3));
  const sea = new THREE.Mesh(seaGeometry, materials.ground);
  sea.rotation.x = -Math.PI / 2;
  sea.position.y = -4;
  sea.receiveShadow = true;
  scene.add(sea);
  let needsRender = true, disposed = false, scheduledFrame = null, width = 1, height = 1;
  const loadedByLayer = {};
  let loadErrors = 0, loadedTiles = 0, lighting = { mode: 'day', date: new Date(), cloudCover: 0, rain: 0, snow: 0 };
  let sunVector = new THREE.Vector3(-0.65, 0.8, 0.45).normalize();
  let lastStatus = '', lastPresentation = 0, lastCityRender = {};
  let latestInputTime = null;
  let overviewState = 'loading';
  const loadMilestones = { firstBuildingsSubmittedMs: null, initialDetailSettledMs: null };
  const frameTimes = [], inputRenderTimes = [];
  function recordTiming(samples, value) { samples.push(value); if (samples.length > 240) samples.shift(); }
  function timingSummary(samples) { const sorted = [...samples].sort((a, b) => a - b); return { samples: sorted.length, median: sorted[Math.floor(sorted.length / 2)] ?? null, p95: sorted[Math.floor(sorted.length * 0.95)] ?? null }; }
  const failedTileRetries = new Map();
  const tilesets = [];
  const sourceFusion = createSourceFusion();
  const objectDetail = createObjectDetail({ maximumPixelError: 1 });
  const treeBatches = createTreeBatches(scene);
  let capturingFullDetail = false;
  const tileCaches = Object.fromEntries([['city', 224], ['trees', 24], ['lights', 12]].map(([name, megabytes]) => {
    const cache = new LRUCache();
    cache.maxBytesSize = megabytes * 1024 * 1024;
    cache.minBytesSize = cache.maxBytesSize * 0.8;
    return [name, cache];
  }));
  const overview = new THREE.Group();
  scene.add(overview);

  function requestRender() { needsRender = true; if (!scheduledFrame && !disposed) scheduledFrame = requestAnimationFrame(frame); }
  function viewReadiness() {
    let pending = overviewState === 'loading' ? 1 : 0;
    let failed = overviewState === 'error';
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
  function colorModel(model, kind) {
    model.traverse(mesh => {
      if (kind === 'lamps') {
        if (mesh.isPoints) mesh.material = mesh.userData.objectKind === 'lampPools' ? lampPoolMaterial : lampGlowMaterial;
        if (mesh.isLineSegments) mesh.material = lampShaftMaterial;
        return;
      }
      if (!mesh.isMesh) return;
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
          color = ['streets', 'bridgeSurfaces'].includes(kind) ? streetColor(mesh.userData.surfaceKind) : kind === 'yards' ? yardColor(mesh.userData.surfaceKind) : featureColor(kind, attributes, `${batchId}:${Math.round(position.getX(index))}:${Math.round(position.getZ(index))}`);
          cachedColors.set(batchId, color);
        }
        color.toArray(colors, index * 3);
      }
      mesh.geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
      mesh.material = materials[kind];
      mesh.castShadow = !['ground', 'streets', 'yards', 'bridgeSurfaces'].includes(kind);
      mesh.receiveShadow = true;
    });
    if (kind === 'trees' || kind === 'lights') objectDetail.addModel(model);
    if (kind === 'trees') treeBatches.addModel(model);
  }

  for (const [kind, id] of LAYERS) {
    const tiles = new TilesRenderer(id.startsWith('./') ? id : `${DATA_BASE}${id}/tileset.json`);
    tiles.kind = kind;
    if (kind === 'buildings') tiles.registerPlugin({
      name: 'Reach the first available building geometry',
      preprocessNode(tile) {
        if (!tile.internal.hasContent && tile.children?.length) tile.geometricError = Infinity;
      },
    });
    if (kind !== 'buildings') { tiles.loadSiblings = false; tiles.loadAncestors = false; }
    tiles.errorTarget = kind === 'buildings' ? 8 : 0;
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
    tiles.addEventListener('load-model', event => { colorModel(event.scene, kind); if (kind === 'ground') sourceFusion.addGround(event.scene); loadedTiles++; loadedByLayer[kind] = (loadedByLayer[kind] || 0) + 1; renderer.shadowMap.needsUpdate = true; requestRender(); });
    if (kind === 'ground') tiles.addEventListener('dispose-model', event => sourceFusion.removeGround(event.scene));
    if (kind === 'trees' || kind === 'lights') tiles.addEventListener('dispose-model', event => { if (kind === 'trees') treeBatches.removeModel(event.scene); objectDetail.removeModel(event.scene); });
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
  const layerPriority = { lamps: 6, streets: 6, yards: 5, ground: 5, bridges: 4, bridgeSurfaces: 3, buildings: 3, tanks: 2, lights: 1, trees: 0 };
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
    const responses = await Promise.all(['municipality.geojson', 'overview.geojson', 'context-land.geojson'].map(name => fetch(`./data/${name}`)));
    if (responses.some(response => !response.ok)) throw new Error('Overview data could not load.');
    addFeatures(await responses[0].json(), true);
    addFeatures(await responses[1].json());
    for (const response of responses.slice(2)) addFeatures(await response.json(), false, true);
    for (const [kind, positions] of positionsByKind) {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
      geometry.computeVertexNormals();
      const color = new THREE.Color(palette[kind] || palette.land), vertexColors = new Float32Array(positions.length);
      for (let index = 0; index < vertexColors.length; index += 3) color.toArray(vertexColors, index);
      geometry.setAttribute('color', new THREE.BufferAttribute(vertexColors, 3));
      const mesh = new THREE.Mesh(geometry, materials.ground); mesh.receiveShadow = true;
      overview.add(mesh);
    }
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
    if (disposed || !needsRender && !precipitation) return;
    const now = performance.now();
    const renderingCity = needsRender;
    if (!needsRender && now - lastPresentation < 32) { scheduledFrame = requestAnimationFrame(frame); return; }
    if (needsRender) {
    needsRender = false;
    scene.updateMatrixWorld(true);
    for (const tiles of tilesets) {
      const visible = tiles.kind === 'streets' ? true : tiles.kind === 'lamps' ? uniforms.night.value > 0.1 : tiles.kind === 'ground' ? view.span < 1400 : tiles.kind === 'trees' ? view.span < 3500 && (loadedByLayer.buildings || 0) >= 6 : tiles.kind === 'lights' ? view.span < 700 && uniforms.night.value > 0.1 : ['bridges', 'bridgeSurfaces'].includes(tiles.kind) ? view.span < 12000 : tiles.kind === 'tanks' ? view.span < 18000 : true;
      if (!visible && tiles.group.visible) {
        for (const tile of tiles.usedSet) tiles.lruCache.markUnused(tile);
        tiles.lruCache.scheduleUnload();
      }
      tiles.group.visible = visible;
      if (visible) tiles.update();
    }
    if (tilesets.find(tiles => tiles.kind === 'ground').group.visible) {
      sourceFusion.setVisibleBridges(tilesets.filter(tiles => tiles.kind === 'bridges' && tiles.group.visible).flatMap(tiles => [...tiles.visibleTiles].map(tile => tile.engineData.scene).filter(Boolean)));
      if (sourceFusion.update()) renderer.shadowMap.needsUpdate = true;
    }
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
    for (const tile of tilesets.find(tiles => tiles.kind === 'lamps').visibleTiles) tile.engineData.scene?.traverse(object => { if (object.isLineSegments) object.visible = view.span >= 700 && view.span < 3500; });
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
    if (needsRender || precipitation) scheduledFrame = requestAnimationFrame(frame);
  }
  function setView(nextView, notify = true) {
    view.lat = THREE.MathUtils.clamp(Number(nextView.lat ?? view.lat), 51.80, 52.05);
    view.lon = THREE.MathUtils.clamp(Number(nextView.lon ?? view.lon), 3.88, 4.66);
    view.span = THREE.MathUtils.clamp(Number(nextView.span ?? view.span), 160, 50000);
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
    uniforms.snow.value = Math.min(1, Number(lighting.snow) || 0);
    sunVector = mode === 'live' && night < 0.9 ? solar.direction : golden ? new THREE.Vector3(-0.9, 0.24, 0.34).normalize() : night ? new THREE.Vector3(-0.5, 0.75, -0.45).normalize() : new THREE.Vector3(-0.65, 0.8, 0.45).normalize();
    sun.color.set(night > 0.5 ? '#9bbaff' : golden ? '#ffc077' : '#fff0d1');
    sun.intensity = night > 0.5 ? 0.8 : (golden ? 3.3 : 3.0) * (1 - cloud * 0.68);
    sky.color.set(night > 0.5 ? '#7896cd' : golden ? '#b8d7ef' : '#cfe9ff');
    sky.groundColor.set(night > 0.5 ? '#28344b' : '#9b8975');
    sky.intensity = night > 0.5 ? 0.8 : 1.25 + cloud * 0.35;
    scene.background.set(night > 0.5 ? '#152b40' : golden ? '#cfc5ab' : '#adc8c7');
    const wetness = Math.min(1, Number(lighting.rain) || 0);
    weatherUniforms.rain.value = wetness > 0 ? Math.max(0.2, wetness) : 0;
    weatherUniforms.snow.value = Math.min(1, Number(lighting.snow) || 0);
    materials.ground.roughness = 0.94 - wetness * 0.35;
    materials.ground.color.setScalar(1 - wetness * 0.13);
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
    tileCaches.trees.maxBytesSize = Math.max(previousTreeCacheLimit, 64 * 1024 * 1024);
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
      tileCaches.trees.scheduleUnload();
      capturePending = false;
      requestRender();
    }
  }
  const pointers = new Map();
  let drag = null;
  function groundAt(clientX, clientY) {
    const bounds = canvas.getBoundingClientRect();
    const ray = new THREE.Raycaster();
    ray.setFromCamera(new THREE.Vector2((clientX - bounds.left) / bounds.width * 2 - 1, 1 - (clientY - bounds.top) / bounds.height * 2), camera);
    return ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), 0), new THREE.Vector3());
  }
  function pointerDown(event) {
    if (![0, 2].includes(event.button) && event.pointerType !== 'touch') return;
    canvas.setPointerCapture(event.pointerId);
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    drag = { rotating: event.button === 2, startX: event.clientX, bearing: view.bearing, point: groundAt(event.clientX, event.clientY), target: target.clone(), distance: pointers.size === 2 ? pointerDistance() : null, span: view.span };
    canvas.style.cursor = 'grabbing';
  }
  function pointerDistance() { const [a, b] = [...pointers.values()]; return Math.hypot(a.x - b.x, a.y - b.y); }
  function pointerMove(event) {
    if (!pointers.has(event.pointerId)) return;
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
  function pointerUp(event) { pointers.delete(event.pointerId); drag = null; pointers.clear(); canvas.style.cursor = 'grab'; }
  function wheel(event) {
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
  return {
    setView, getView: () => ({ ...view }), setLighting, captureCanvas,
    zoom: factor => setView({ span: view.span / factor }), reset: () => setView(DEFAULT_VIEW),
    render: () => { needsRender = true; frame(); }, getCanvas: () => canvas, resize,
    getDiagnostics: () => ({ readiness: viewReadiness(), loadMilestones, timings: { frameSubmissionMs: timingSummary(frameTimes), inputToRenderSubmissionMs: timingSummary(inputRenderTimes) }, treeBatches: treeBatches.diagnostics(), objectDetail: objectDetail.diagnostics(), sourceFusion: sourceFusion.getDiagnostics(), loadedTiles, loadErrors, drawingSize: renderer.getDrawingBufferSize(new THREE.Vector2()).toArray(), cacheBytes: Object.values(tileCaches).reduce((sum, cache) => sum + cache.cachedBytes, 0), caches: Object.fromEntries(Object.entries(tileCaches).map(([name, cache]) => [name, { bytes: cache.cachedBytes, full: cache.isFull(), limit: cache.maxBytesSize }])), layers: tilesets.map(tiles => ({ kind: tiles.kind, geometry: [...tiles.visibleTiles].reduce((counts, tile) => { tile.engineData.scene?.traverseVisible(mesh => { if (mesh.isMesh) { counts.meshes++; counts.triangles += (mesh.geometry.index?.count || mesh.geometry.getAttribute('position')?.count || 0) / 3 * (mesh.isInstancedMesh ? mesh.count : 1); } }); return counts; }, { meshes: 0, triangles: 0 }), visible: tiles.visibleTiles.size, downloading: tiles.stats.downloading, parsing: tiles.stats.parsing, queued: tiles.stats.queued, refused: tiles.stats.refused })), rendering: lastCityRender, memory: renderer.info.memory }),
    dispose() {
      disposed = true; if (scheduledFrame) cancelAnimationFrame(scheduledFrame); observer.disconnect();
      for (const [event, handler] of [['pointerdown', pointerDown], ['pointermove', pointerMove], ['pointerup', pointerUp], ['pointercancel', pointerUp], ['wheel', wheel], ['dblclick', doubleClick], ['contextmenu', contextMenu]]) canvas.removeEventListener(event, handler);
      sourceFusion.dispose(); treeBatches.dispose(); objectDetail.dispose();
      for (const tiles of tilesets) tiles.dispose();
      for (const material of Object.values(materials)) material.dispose();
      lampGlowMaterial.dispose(); lampPoolMaterial.dispose(); lampShaftMaterial.dispose(); reflectionTarget.dispose(); cityTarget.dispose(); presentationQuad.geometry.dispose(); presentationMaterial.dispose();
      overview.traverse(object => { object.geometry?.dispose(); object.material?.dispose(); });
      sea.geometry.dispose(); sea.material.dispose(); renderer.dispose();
    },
  };
}
