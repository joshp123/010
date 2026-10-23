import * as THREE from 'three';
import { TilesRenderer } from '3d-tiles-renderer';

const ORIGIN = { lat: 51.915, lon: 4.49 };
const DEFAULT_VIEW = { lat: 51.9105, lon: 4.4875, span: 1700, bearing: 35 };
const DEGREES = Math.PI / 180;
const DATA_BASE = 'https://www.3drotterdam.nl/datasource-data/';
const LAYERS = [
  ['buildings', '8b5d0ded-a222-4e44-bc70-2992bc2192fc'],
  ['ground', '0025cb58-e0f5-4169-bb4c-5339a3bc2a7e'],
  ['bridges', '06595036-c78e-4081-ab25-e8f88b66bc19'],
  ['tanks', 'c70023a7-2878-41e9-bb81-a7c454bc310a'],
  ['trees', 'b9294d5b-79e0-4744-ac88-b61e3e90d5bc'],
  ['lights', '2602863a-3d22-44c2-8c95-bbf88a20bf37'],
];
const BUILDING_COLORS = ['#d5c9ad', '#bda58a', '#a77d62', '#c5c4b5', '#aebfc1', '#e0d4bb', '#a68c7b', '#8d9ea3'].map(color => new THREE.Color(color));
const GROUND_COLORS = {
  water: new THREE.Color('#367b86'), green: new THREE.Color('#73936d'), road: new THREE.Color('#9ba09a'),
  pavement: new THREE.Color('#c8c2ac'), building: new THREE.Color('#b4ad98'), other: new THREE.Color('#b3b5a1'),
};

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
function hashNumber(value) { let hash = 2166136261; for (const char of String(value)) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619); return (hash >>> 0); }
function batchTableFor(mesh) { let parent = mesh; while (parent && !parent.batchTable) parent = parent.parent; return parent?.batchTable; }
function classOfGround(attributes) {
  const type = String(attributes.KLASSE_IMG || attributes.KLASSE || '').toLowerCase();
  const detail = String(attributes.FYSIEKVK || attributes.FUNCTIE || '').toLowerCase();
  if (type.includes('water')) return 'water';
  if (type.includes('begroeid') || type.includes('plant') || /gras|groen|struik|bos|tuin/.test(detail)) return 'green';
  if (type.includes('pand')) return 'building';
  if (type.includes('weg') && !/voet|fiets|ruiter|berm/.test(detail)) return 'road';
  if (type.includes('weg') || type.includes('onbegroeid') || type.includes('ondersteunend')) return 'pavement';
  return 'other';
}

function cityMaterial(kind, uniforms) {
  const material = new THREE.MeshStandardMaterial({ color: 0xffffff, vertexColors: true, roughness: 0.94, metalness: 0, flatShading: true, side: THREE.DoubleSide });
  material.onBeforeCompile = shader => {
    shader.uniforms.cityNight = uniforms.night;
    shader.uniforms.citySnow = uniforms.snow;
    shader.uniforms.cityReflection = uniforms.reflection;
    shader.uniforms.cityReflectionMatrix = uniforms.reflectionMatrix;
    shader.vertexShader = `varying vec3 cityWorldPosition; varying vec3 cityWorldNormal;\n` + shader.vertexShader;
    shader.vertexShader = shader.vertexShader.replace('#include <begin_vertex>', `#include <begin_vertex>\n vec4 cityVertex = vec4(transformed, 1.0);\n #ifdef USE_INSTANCING\n cityVertex = instanceMatrix * cityVertex;\n #endif\n cityWorldPosition = (modelMatrix * cityVertex).xyz; cityWorldNormal = normalize(mat3(modelMatrix) * objectNormal);`);
    shader.fragmentShader = `uniform float cityNight; uniform float citySnow; uniform sampler2D cityReflection; uniform mat4 cityReflectionMatrix; varying vec3 cityWorldPosition; varying vec3 cityWorldNormal;\n float cityHash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123); }\n` + shader.fragmentShader;
    let surface = '';
    if (kind === 'buildings') {
      surface = `
        vec3 cityNormal = normalize(cityWorldNormal);
        float cityWall = 1.0 - smoothstep(0.15, 0.55, abs(cityNormal.y));
        vec2 cityTangent = normalize(vec2(cityNormal.z + 0.00001, -cityNormal.x));
        float cityHorizontal = dot(cityWorldPosition.xz, cityTangent);
        vec2 cityWindowCell = vec2(cityHorizontal / 3.1, (cityWorldPosition.y - 1.1) / 3.25);
        vec2 cityWindowUV = fract(cityWindowCell);
        vec2 cityWindowAA = min(fwidth(cityWindowCell) * 0.5, vec2(0.24));
        float cityWindow = smoothstep(0.19-cityWindowAA.x, 0.19+cityWindowAA.x, cityWindowUV.x) * (1.0-smoothstep(0.66-cityWindowAA.x, 0.66+cityWindowAA.x, cityWindowUV.x)) * smoothstep(0.18-cityWindowAA.y, 0.18+cityWindowAA.y, cityWindowUV.y) * (1.0-smoothstep(0.73-cityWindowAA.y, 0.73+cityWindowAA.y, cityWindowUV.y)) * cityWall;
        cityWindow *= 1.0-smoothstep(0.8, 2.2, max(fwidth(cityWindowCell.x),fwidth(cityWindowCell.y)));
        cityWindow *= smoothstep(3.2, 5.5, cityWorldPosition.y);
        float cityWindowSeed = cityHash(floor(cityWindowCell) + floor(vColor.rg * 91.0));
        float cityLit = step(0.57, cityWindowSeed);
        vec3 cityWindowLight = mix(vec3(1.0, 0.29, 0.055), vec3(1.0, 0.61, 0.22), step(0.77, cityWindowSeed));
        diffuseColor.rgb *= mix(1.0, 0.68, 1.0 - cityWall);
        diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.12, 0.23, 0.27), cityWindow * 0.62);
        diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.86, 0.90, 0.91), citySnow * smoothstep(0.4, 0.9, cityNormal.y));
        totalEmissiveRadiance += cityWindowLight * cityWindow * cityLit * cityNight * 1.05;
      `;
    } else if (kind === 'ground') {
      surface = `
        float cityWater = step(vColor.r * 1.7, vColor.g) * step(vColor.r * 1.9, vColor.b);
        vec4 cityReflectedPosition = cityReflectionMatrix * vec4(cityWorldPosition, 1.0);
        vec2 cityReflectionUV = cityReflectedPosition.xy / cityReflectedPosition.w * 0.5 + 0.5;
        cityReflectionUV.x += sin(cityWorldPosition.z * 0.42) * 0.0015;
        vec3 cityReflectionLight = texture2D(cityReflection, cityReflectionUV).rgb;
        float cityRipple = 0.52 + 0.22 * sin(cityWorldPosition.z * 0.6 + sin(cityWorldPosition.x * 0.12));
        totalEmissiveRadiance += cityReflectionLight * cityWater * cityNight * cityRipple * 0.65;
      `;
    } else if (kind === 'bridges') {
      surface = `
        float cityEdgeLight = pow(1.0 - abs(normalize(cityWorldNormal).y), 3.0);
        totalEmissiveRadiance += vec3(0.25, 0.52, 0.67) * cityEdgeLight * cityNight * 0.14;
      `;
    }
    shader.fragmentShader = shader.fragmentShader.replace('#include <emissivemap_fragment>', `#include <emissivemap_fragment>\n${surface}`);
  };
  material.customProgramCacheKey = () => `010-${kind}-v1`;
  return material;
}

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
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: false, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(1);
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
  const cityTarget = new THREE.WebGLRenderTarget(512, 512, { type: THREE.HalfFloatType });
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
  const uniforms = { night: { value: 0 }, snow: { value: 0 }, reflection: { value: reflectionTarget.texture }, reflectionMatrix: { value: new THREE.Matrix4() } };
  const glowUniforms = { night: uniforms.night, size: { value: 4 } };
  const lampGlowMaterial = new THREE.ShaderMaterial({
    uniforms: glowUniforms, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false,
    vertexShader: `uniform float size; void main() { gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); gl_PointSize = size; }`,
    fragmentShader: `uniform float night; void main() { float radius = length(gl_PointCoord - 0.5) * 2.0; if(radius > 1.0) discard; float glow = exp(-radius * radius * 10.0) * 0.38 + exp(-radius * radius * 3.0) * 0.07; gl_FragColor = vec4(vec3(1.0, 0.61, 0.23), glow * night); }`,
  });
  const materials = Object.fromEntries(LAYERS.map(([kind]) => [kind, cityMaterial(kind, uniforms)]));
  const seaGeometry = new THREE.PlaneGeometry(180000, 180000, 96, 96);
  const seaVertices = seaGeometry.getAttribute('position');
  for (let i = 0; i < seaVertices.count; i++) seaVertices.setZ(i, -((seaVertices.getX(i) ** 2 + seaVertices.getY(i) ** 2) / (2 * 6371000)));
  seaGeometry.computeVertexNormals();
  const sea = new THREE.Mesh(seaGeometry, new THREE.MeshStandardMaterial({ color: '#347681', roughness: 0.65, metalness: 0.12 }));
  sea.rotation.x = -Math.PI / 2;
  sea.position.y = -4;
  sea.receiveShadow = true;
  scene.add(sea);
  let needsRender = true, disposed = false, scheduledFrame = null, width = 1, height = 1;
  const loadedByLayer = {};
  let loadErrors = 0, loadedTiles = 0, lighting = { mode: 'day', date: new Date(), cloudCover: 0, rain: 0, snow: 0 };
  let sunVector = new THREE.Vector3(-0.65, 0.8, 0.45).normalize();
  let lastStatus = '', lastPresentation = 0;
  const failedTileRetries = new Map();
  const tilesets = [];
  const overview = new THREE.Group();
  scene.add(overview);

  function requestRender() { needsRender = true; if (!scheduledFrame && !disposed) scheduledFrame = requestAnimationFrame(frame); }
  function surfaceDiagnostics() {
    scene.updateMatrixWorld(true);
    const groups = [...tilesets.filter(layer => layer.kind === 'ground').map(layer => ({ name: layer.kind, group: layer.group })), { name: 'overview', group: overview }, { name: 'sea', group: sea }];
    const visibleMeshes = groups.flatMap(({ name, group }) => {
      const entries = [];
      group.traverseVisible(object => { if (object.isMesh) entries.push({ name, object }); });
      return entries;
    });
    const samples = [['Kop van Zuid', 51.9045, 4.488], ['Noordereiland', 51.912, 4.498], ['north bank', 51.917, 4.494], ['river', 51.91, 4.486]];
    return samples.map(([name, lat, lon]) => {
      const origin = localPosition(lat, lon); origin.y = 10000;
      const ray = new THREE.Raycaster(origin, new THREE.Vector3(0, -1, 0));
      const hits = visibleMeshes.flatMap(entry => ray.intersectObject(entry.object, false).map(hit => ({ layer: entry.name, height: hit.point.y, color: hit.object.geometry.getAttribute('color') ? Array.from(hit.object.geometry.getAttribute('color').array.slice(hit.face.a * 3, hit.face.a * 3 + 3)) : null }))).sort((a,b) => b.height-a.height);
      return { name, hits: hits.slice(0, 6) };
    });
  }
  function reportStatus() {
    const pending = tilesets.reduce((sum, tile) => sum + (tile.stats.downloading || 0) + (tile.stats.parsing || 0), 0);
    const state = loadedTiles ? (pending ? 'loading' : 'ready') : (loadErrors ? 'error' : 'loading');
    const message = state === 'error' ? 'The city data could not be loaded. Reload to retry.' : pending || !loadedTiles ? 'Bringing Rotterdam into view…' : 'Rotterdam, in miniature';
    const key = `${state}:${loadedTiles}:${pending}`;
    if (key !== lastStatus) { lastStatus = key; onStatus({ state, message, loadedTiles, loadingTiles: pending }); }
  }
  function colorModel(model, kind) {
    model.traverse(mesh => {
      if (!mesh.isMesh) return;
      const position = mesh.geometry.getAttribute('position');
      const batchIds = mesh.geometry.getAttribute('_batchid');
      const table = batchTableFor(mesh);
      const colors = new Float32Array(position.count * 3);
      const cachedColors = new Map();
      const originalMaterial = Array.isArray(mesh.material) ? mesh.material[0] : mesh.material;
      for (let index = 0; index < position.count; index++) {
        const batchId = batchIds ? batchIds.getX(index) : 0;
        let color = cachedColors.get(batchId);
        if (!color) {
          let attributes = {};
          if (table && batchIds) { try { attributes = table.getDataFromId(batchId)?.attributes || {}; } catch {} }
          if (kind === 'ground') color = GROUND_COLORS[classOfGround(attributes)];
          else if (kind === 'trees') color = new THREE.Color('#638168');
          else if (kind === 'bridges') color = new THREE.Color('#d1d7cb');
          else if (kind === 'tanks') color = new THREE.Color('#d9d9cb');
          else if (kind === 'lights') color = new THREE.Color('#586564');
          else {
            const identifier = attributes.GEBOUWNUMMER || attributes['gml:id'] || `${batchId}:${Math.round(position.getX(index))}:${Math.round(position.getZ(index))}`;
            color = BUILDING_COLORS[hashNumber(identifier) % BUILDING_COLORS.length];
          }
          cachedColors.set(batchId, color);
        }
        color.toArray(colors, index * 3);
      }
      mesh.geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
      mesh.material = materials[kind];
      mesh.castShadow = kind !== 'ground';
      mesh.receiveShadow = true;
    });
    if (kind === 'lights') addLampGlows(model);
  }
  function addLampGlows(model) {
    model.updateMatrixWorld(true);
    const meshes = []; model.traverse(mesh => { if(mesh.isInstancedMesh) meshes.push(mesh); });
    const instanceMatrix = new THREE.Matrix4(), fullMatrix = new THREE.Matrix4();
    const vertex = new THREE.Vector3(), topVertex = new THREE.Vector3();
    for (const mesh of meshes) {
      const positions = [], vertices = mesh.geometry.getAttribute('position');
      for (let instance = 0; instance < mesh.count; instance++) {
        mesh.getMatrixAt(instance, instanceMatrix);
        fullMatrix.multiplyMatrices(mesh.matrixWorld, instanceMatrix);
        let highest = -Infinity;
        for (let index = 0; index < vertices.count; index++) {
          vertex.fromBufferAttribute(vertices, index).applyMatrix4(fullMatrix);
          const elevation = vertex.dot(up);
          if (elevation > highest) { highest = elevation; topVertex.fromBufferAttribute(vertices, index); }
        }
        topVertex.applyMatrix4(instanceMatrix); positions.push(topVertex.x, topVertex.y, topVertex.z);
      }
      const geometry = new THREE.BufferGeometry(); geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
      mesh.add(new THREE.Points(geometry, lampGlowMaterial));
    }
  }

  for (const [kind, id] of LAYERS) {
    const tiles = new TilesRenderer(`${DATA_BASE}${id}/tileset.json`);
    tiles.kind = kind;
    tiles.errorTarget = kind === 'buildings' ? 2 : 0;
    tiles.setCamera(camera);
    tiles.group.matrixAutoUpdate = false;
    tiles.group.matrix.copy(earthToLocal);
    if (tilesets.length) {
      tiles.lruCache = tilesets[0].lruCache;
      tiles.downloadQueue = tilesets[0].downloadQueue;
      tiles.parseQueue = tilesets[0].parseQueue;
      tiles.processNodeQueue = tilesets[0].processNodeQueue;
    } else {
      tiles.lruCache.maxBytesSize = 260 * 1024 * 1024;
      tiles.lruCache.minBytesSize = 200 * 1024 * 1024;
      tiles.downloadQueue.maxJobsPerOrigin = 10;
      tiles.parseQueue.maxJobs = 2;
    }
    tiles.addEventListener('load-model', event => { colorModel(event.scene, kind); loadedTiles++; loadedByLayer[kind] = (loadedByLayer[kind] || 0) + 1; renderer.shadowMap.needsUpdate = true; requestRender(); });
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
  async function loadOverview() {
    const palette = { water: '#397d86', farmland: '#a6af7b', forest: '#678368', grass: '#869c72', land: '#b7baa2', urban: '#b9b7a6', sand: '#d7c8a4' };
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
      for (const face of faces) for (const index of face) positions.push(points[index].x, points[index].y, points[index].z);
    }
    function addFeatures(collection, base = false) {
      for (const feature of collection.features) {
        const kind = base ? 'land' : feature.properties.kind || 'land';
        const heights = { land: -2.7, urban: -2.4, farmland: -2.1, grass: -1.8, forest: -1.5, sand: -1.2, water: -0.9 };
        const height = base ? -3.0 : heights[kind] ?? -2.4;
        const polygons = feature.geometry.type === 'Polygon' ? [feature.geometry.coordinates] : feature.geometry.type === 'MultiPolygon' ? feature.geometry.coordinates : [];
        for (const polygon of polygons) addPolygon(polygon, kind, height);
      }
    }
    const responses = await Promise.all([fetch('./data/municipality.geojson'), fetch('./data/overview.geojson')]);
    if (responses[0].ok) addFeatures(await responses[0].json(), true);
    if (responses[1].ok) addFeatures(await responses[1].json());
    for (const [kind, positions] of positionsByKind) {
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
      geometry.computeVertexNormals();
      let material;
      if (kind === 'water') {
        const color = new THREE.Color(palette.water); const vertexColors = new Float32Array(positions.length);
        for (let index = 0; index < vertexColors.length; index += 3) color.toArray(vertexColors, index);
        geometry.setAttribute('color', new THREE.BufferAttribute(vertexColors, 3)); material = materials.ground;
      } else material = new THREE.MeshStandardMaterial({ color: palette[kind] || palette.land, roughness: 0.96, side: THREE.DoubleSide });
      const mesh = new THREE.Mesh(geometry, material); mesh.receiveShadow = true;
      overview.add(mesh);
    }
    renderer.shadowMap.needsUpdate = true;
    requestRender();
  }
  loadOverview().catch(error => console.warn('010: overview could not load', error));

  function updateCamera() {
    const aspect = width / height;
    glowUniforms.size.value = Math.max(1.5, Math.min(6, 6 * height / view.span));
    camera.left = -view.span * aspect / 2;
    camera.right = view.span * aspect / 2;
    camera.top = view.span / 2;
    camera.bottom = -view.span / 2;
    const bearing = view.bearing * DEGREES, distance = 40000;
    camera.position.copy(target).add(new THREE.Vector3(Math.sin(bearing) * 0.8, 0.82, Math.cos(bearing) * 0.8).normalize().multiplyScalar(distance));
    camera.lookAt(target);
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld();
    updateShadowCamera();
    for (const tiles of tilesets) tiles.setResolutionFromRenderer(camera, renderer);
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
    if (!needsRender && now - lastPresentation < 32) { scheduledFrame = requestAnimationFrame(frame); return; }
    if (needsRender) {
    needsRender = false;
    scene.updateMatrixWorld(true);
    for (const tiles of tilesets) {
      const visible = tiles.kind === 'ground' ? view.span < 6500 : tiles.kind === 'trees' ? view.span < 3500 && (loadedByLayer.buildings || 0) >= 6 : tiles.kind === 'lights' ? view.span < 5000 && uniforms.night.value > 0.1 && (loadedByLayer.ground || 0) > 0 : tiles.kind === 'bridges' ? view.span < 12000 : tiles.kind === 'tanks' ? view.span < 18000 : true;
      tiles.group.visible = visible;
      if (visible) tiles.update();
    }
    if (uniforms.night.value > 0.1 && view.span < 6500) {
      reflectionCamera.copy(camera);
      reflectionCamera.position.y *= -1;
      reflectionCamera.up.set(0, -1, 0);
      reflectionCamera.lookAt(target.x, -target.y, target.z);
      reflectionCamera.updateMatrixWorld();
      uniforms.reflectionMatrix.value.multiplyMatrices(reflectionCamera.projectionMatrix, reflectionCamera.matrixWorldInverse);
      const background = scene.background; scene.background = new THREE.Color(0x000000);
      const groundLayer = tilesets.find(layer => layer.kind === 'ground');
      const groundVisible = groundLayer.group.visible; groundLayer.group.visible = false; overview.visible = false; sea.visible = false;
      renderer.setRenderTarget(reflectionTarget); renderer.render(scene, reflectionCamera); renderer.setRenderTarget(null);
      groundLayer.group.visible = groundVisible; overview.visible = true; sea.visible = true; scene.background = background;
    }
    renderer.setRenderTarget(cityTarget); renderer.render(scene, camera); renderer.setRenderTarget(null);
    reportStatus();
    }
    weatherUniforms.time.value = now / 1000;
    renderer.render(presentationScene, presentationCamera); lastPresentation = now;
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
    sea.material.color.set(night > 0.5 ? '#173746' : golden ? '#53858a' : '#397d86');
    sea.material.emissive.set(night > 0.5 ? '#102b3c' : '#000000');
    sea.material.emissiveIntensity = night > 0.5 ? 0.35 : 0;
    const wetness = Math.min(1, Number(lighting.rain) || 0);
    weatherUniforms.rain.value = wetness > 0 ? Math.max(0.2, wetness) : 0;
    weatherUniforms.snow.value = Math.min(1, Number(lighting.snow) || 0);
    materials.ground.roughness = 0.94 - wetness * 0.35;
    materials.ground.color.setScalar(1 - wetness * 0.13);
    renderer.toneMappingExposure = night > 0.5 ? 1.35 : 1.12;
    updateShadowCamera();
    requestRender();
  }
  function resize() {
    const bounds = canvas.getBoundingClientRect();
    width = Math.max(1, bounds.width); height = Math.max(1, bounds.height);
    const pixelScale = 1;
    renderer.setSize(Math.round(width / pixelScale), Math.round(height / pixelScale), false);
    reflectionTarget.setSize(Math.round(width / 2), Math.round(height / 2));
    cityTarget.setSize(Math.round(width / pixelScale), Math.round(height / pixelScale));
    weatherUniforms.resolution.value.set(width, height);
    updateCamera();
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
    setView, getView: () => ({ ...view }), setLighting,
    zoom: factor => setView({ span: view.span / factor }), reset: () => setView(DEFAULT_VIEW),
    render: () => { needsRender = true; frame(); }, getCanvas: () => canvas, resize,
    getDiagnostics: () => ({ loadedTiles, loadErrors, surfaceSamples: surfaceDiagnostics(), cacheBytes: tilesets[0].lruCache.cachedBytes, cacheFull: tilesets[0].lruCache.isFull(), groundTiles: [...tilesets.find(layer => layer.kind === 'ground').visibleTiles].map(tile => { const bounds = new THREE.Box3().setFromObject(tile.engineData.scene); return { uri: tile.content?.uri || tile.content?.url, bounds: [bounds.min.toArray(), bounds.max.toArray()] }; }), layers: tilesets.map(tiles => ({ kind: tiles.kind, visible: tiles.visibleTiles.size, downloading: tiles.stats.downloading, parsing: tiles.stats.parsing })), rendering: renderer.info.render, memory: renderer.info.memory }),
    dispose() {
      disposed = true; if (scheduledFrame) cancelAnimationFrame(scheduledFrame); observer.disconnect();
      for (const [event, handler] of [['pointerdown', pointerDown], ['pointermove', pointerMove], ['pointerup', pointerUp], ['pointercancel', pointerUp], ['wheel', wheel], ['dblclick', doubleClick], ['contextmenu', contextMenu]]) canvas.removeEventListener(event, handler);
      for (const tiles of tilesets) tiles.dispose();
      for (const material of Object.values(materials)) material.dispose();
      lampGlowMaterial.dispose(); reflectionTarget.dispose(); cityTarget.dispose(); presentationQuad.geometry.dispose(); presentationMaterial.dispose();
      overview.traverse(object => { object.geometry?.dispose(); object.material?.dispose(); });
      sea.geometry.dispose(); sea.material.dispose(); renderer.dispose();
    },
  };
}
