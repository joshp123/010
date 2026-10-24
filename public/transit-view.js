import * as THREE from 'three';

const VEHICLE_STYLES = {
  bus: { color: '#c49558', width: 2.7, height: 3.1, length: 12 },
  tram: { color: '#b56a59', width: 2.6, height: 3.3, length: 28 },
  metro: { color: '#d1d7cc', width: 3, height: 3.5, length: 48 },
  train: { color: '#d1af58', width: 3.2, height: 3.8, length: 72 },
  ferry: { color: '#698a9a', width: 5, height: 3.5, length: 20 },
  unknown: { color: '#b3b6ac', width: 3, height: 3, length: 9 },
};
const TUNNEL_DEPTH = 12;
const CLASSIFICATION_DISTANCE = 18;
const CUTAWAY_HALF_WIDTH = 8; // View-projected illustrated aperture, not tunnel engineering.
const CHAMBER_HALF_WIDTH = 7;

function pointOnSegment(point, start, end) {
  const dx = end.x - start.x, dz = end.z - start.z;
  const fraction = THREE.MathUtils.clamp(((point.x - start.x) * dx + (point.z - start.z) * dz) / (dx * dx + dz * dz || 1), 0, 1);
  return { distance: Math.hypot(point.x - start.x - fraction * dx, point.z - start.z - fraction * dz), heading: Math.atan2(dx, dz) };
}

// project returns the intended local ground surface plus offsetMetres. Shapes
// are symmetric symbols: dimensions and rail-axis orientation are illustrative.
export function createTransitView({ project, localPosition, requestRender = () => {} }) {
  const place = project || localPosition;
  const group = new THREE.Group();
  group.name = 'Observed public transport';
  const cutawayGroup = new THREE.Group();
  cutawayGroup.name = 'BRT tunnel plan · depth illustrated';
  cutawayGroup.visible = false;
  group.add(cutawayGroup);
  const box = new THREE.BoxGeometry(1, 1, 1);
  const bodyMaterial = new THREE.MeshStandardMaterial({ color: '#ffffff', roughness: 0.9, metalness: 0, flatShading: true });
  const roofMaterial = new THREE.MeshStandardMaterial({ color: '#e3e2ce', roughness: 0.95, metalness: 0 });
  const tunnelMaterial = new THREE.MeshStandardMaterial({ color: '#a8aaa0', roughness: 1, side: THREE.DoubleSide });
  const metroBodyMaterial = bodyMaterial.clone(), metroRoofMaterial = roofMaterial.clone();
  for (const material of [metroBodyMaterial, metroRoofMaterial]) {
    const isBody = material === metroBodyMaterial;
    material.onBeforeCompile = shader => {
      shader.vertexShader = 'varying vec3 transitLocal;\n' + shader.vertexShader;
      shader.vertexShader = shader.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\n transitLocal = position;');
      shader.fragmentShader = 'varying vec3 transitLocal;\n' + shader.fragmentShader;
      shader.fragmentShader = shader.fragmentShader.replace('#include <emissivemap_fragment>', `#include <emissivemap_fragment>
        // Three illustrated articulated sections; no rolling-stock identity claim.
        float carriage = fract((transitLocal.z + 0.5) * 3.0);
        if (carriage < 0.013 || carriage > 0.987) discard;
        ${isBody ? `
        float side = step(0.49, abs(transitLocal.x));
        float window = step(-0.02, transitLocal.y) * step(transitLocal.y, 0.31);
        float pane = step(0.12, fract(carriage * 6.0)) * step(fract(carriage * 6.0), 0.86);
        float glazing = window * mix(step(0.49, abs(transitLocal.z)), pane, side);
        diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.025, 0.065, 0.075), glazing * 0.92);
        float stripe = side * step(-0.15, transitLocal.y) * step(transitLocal.y, -0.07);
        diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.16, 0.36, 0.32), stripe);
        totalEmissiveRadiance += vec3(0.18, 0.14, 0.07) * glazing;
        ` : ''}
      `);
    };
    material.customProgramCacheKey = () => `010-metro-articulation-${isBody ? 'body' : 'roof'}-v1`;
  }
  const trackMaterials = [
    new THREE.MeshStandardMaterial({ color: '#3c443e', roughness: 1, side: THREE.DoubleSide }),
    new THREE.MeshStandardMaterial({ color: '#7c8170', roughness: 1, side: THREE.DoubleSide }),
    new THREE.MeshStandardMaterial({ color: '#c5c4a7', roughness: 0.8, side: THREE.DoubleSide }),
  ];
  const batches = new Map();
  const transform = new THREE.Object3D(), color = new THREE.Color();
  let snapshot = { vehicles: [] }, records = [], railSegments = [], cutaway = false, cutawayMask = null;
  let span = 1700, viewportHeight = 900, camera = null;
  const maskViewDirection = new THREE.Vector3();
  let tunnelSegments = [], maskRebuilds = 0, maskMilliseconds = 0, maskMetresPerPixel = Infinity;

  function batchFor(mode, count) {
    let batch = batches.get(mode);
    if (!batch || batch.capacity < count) {
      if (batch) { group.remove(batch.body, batch.roof); batch.body.dispose(); batch.roof.dispose(); }
      const capacity = Math.max(16, count);
      const body = new THREE.InstancedMesh(box, mode === 'metro' ? metroBodyMaterial : bodyMaterial, capacity);
      const roof = new THREE.InstancedMesh(box, mode === 'metro' ? metroRoofMaterial : roofMaterial, capacity);
      body.name = `Observed ${mode}`; roof.name = `${mode} roofs`;
      body.instanceMatrix.setUsage(THREE.DynamicDrawUsage); roof.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      body.castShadow = true; body.receiveShadow = true;
      group.add(body, roof);
      batch = { body, roof, capacity, records: [] };
      batches.set(mode, batch);
    }
    return batch;
  }

  function classify(position) {
    let nearest = null;
    for (const segment of railSegments) {
      const result = pointOnSegment(position, segment.start, segment.end);
      if (result.distance <= CLASSIFICATION_DISTANCE && (!nearest || result.distance < nearest.distance)) nearest = { ...result, id: segment.id, form: segment.form, relativeLevel: segment.relativeLevel };
    }
    return nearest;
  }

  function routeAxis(report) {
    if (!report.routeShape) return null;
    const eastMetresPerDegree = 111320 * Math.cos(report.latitude * Math.PI / 180);
    let nearest = null;
    for (const line of report.routeShape) for (let index = 1; index < line.length; index++) {
      const [lonA, latA] = line[index - 1], [lonB, latB] = line[index];
      const start = { x: (lonA - report.longitude) * eastMetresPerDegree, z: (report.latitude - latA) * 111320 };
      const end = { x: (lonB - report.longitude) * eastMetresPerDegree, z: (report.latitude - latB) * 111320 };
      const result = pointOnSegment({ x: 0, z: 0 }, start, end);
      if (result.distance <= 40 && (!nearest || result.distance < nearest.distance)) nearest = result;
    }
    return nearest?.heading ?? null;
  }

  function rebuild(refreshReports = false) {
    if (refreshReports) {
      records = [];
      for (const report of snapshot.vehicles) {
        const mode = VEHICLE_STYLES[report.mode] ? report.mode : 'unknown';
        const ground = place(report.latitude, report.longitude, 0);
        const rail = mode === 'metro' ? classify(ground) : null;
        const underground = rail?.form === 'tunnel';
        const routeHeading = Number.isFinite(report.bearing) ? Math.PI - report.bearing * Math.PI / 180 : rail?.heading ?? routeAxis(report);
        const orientation = Number.isFinite(report.bearing) ? 'reported-bearing' : rail ? 'source-track-axis' : routeHeading !== null ? 'source-route-axis' : 'camera-facing-symbol';
        const record = { report, ground, rail, underground, mode, routeHeading, orientation };
        records.push(record);
      }
    }
    const modes = new Map();
    for (const record of records) {
      if (record.underground && !cutaway) continue;
      if (!modes.has(record.mode)) modes.set(record.mode, []);
      modes.get(record.mode).push(record);
    }
    for (const [mode, reports] of modes) {
      const batch = batchFor(mode, reports.length), style = VEHICLE_STYLES[mode];
      batch.records = reports;
      for (let index = 0; index < reports.length; index++) {
        const record = reports[index], report = record.report;
        const scale = record.underground ? 1 : THREE.MathUtils.clamp(4 * span / viewportHeight / style.length, 1, 8);
        const verticalOffset = record.underground ? -TUNNEL_DEPTH : 0;
        const base = place(report.latitude, report.longitude, verticalOffset);
        transform.position.copy(base); transform.position.y += style.height * scale / 2 + 0.4;
        // Compass bearings are clockwise from north; local +Z points south.
        transform.rotation.set(0, record.routeHeading ?? (camera ? Math.atan2(camera.position.x - base.x, camera.position.z - base.z) : 0), 0);
        transform.scale.set(style.width * scale, style.height * scale, style.length * scale);
        transform.updateMatrix(); batch.body.setMatrixAt(index, transform.matrix);
        color.set(style.color);
        if (report.freshness !== 'fresh' || !report.sourceConnected) color.set('#92968e');
        batch.body.setColorAt(index, color);
        transform.position.y += style.height * scale * 0.48;
        transform.scale.set(style.width * scale * 0.8, style.height * scale * 0.16, style.length * scale * 0.76);
        transform.updateMatrix(); batch.roof.setMatrixAt(index, transform.matrix);
      }
      batch.body.count = batch.roof.count = reports.length;
      batch.body.instanceMatrix.needsUpdate = batch.roof.instanceMatrix.needsUpdate = true;
      if (batch.body.instanceColor) batch.body.instanceColor.needsUpdate = true;
      batch.body.computeBoundingSphere(); batch.roof.computeBoundingSphere();
    }
    for (const [mode, batch] of batches) if (!modes.has(mode)) { batch.body.count = batch.roof.count = 0; batch.records = []; }
    group.updateMatrixWorld(true);
    requestRender();
  }

  function setMetroData(data) {
    railSegments = [];
    for (const segment of data.segments) {
      const points = segment.coordinates.map(([longitude, latitude]) => place(latitude, longitude, 0));
      for (let index = 1; index < points.length; index++) railSegments.push({ ...segment, coordinates: undefined, start: points[index - 1], end: points[index] });
    }
    for (const child of [...cutawayGroup.children]) { cutawayGroup.remove(child); child.geometry.dispose(); }
    cutawayMask?.texture.dispose();
    const tunnels = railSegments.filter(segment => segment.form === 'tunnel');
    if (!tunnels.length) { cutawayMask = null; rebuild(true); return; }
    const vertices = [];
    const trackVertices = [[], [], []];
    const bounds = new THREE.Box3();
    const addQuad = (a, b, c, d, output = vertices) => { for (const point of [a, b, c, a, c, d]) output.push(point.x, point.y, point.z); };
    for (const segment of tunnels) {
      const { start, end } = segment;
      bounds.expandByPoint(start); bounds.expandByPoint(end);
      const direction = new THREE.Vector3().subVectors(end, start).setY(0).normalize();
      const side = new THREE.Vector3(-direction.z, 0, direction.x).multiplyScalar(CHAMBER_HALF_WIDTH);
      const a = start.clone().add(side), b = start.clone().sub(side), c = end.clone().sub(side), d = end.clone().add(side);
      const floor = [a, b, c, d].map(point => point.clone().add(new THREE.Vector3(0, -TUNNEL_DEPTH, 0)));
      addQuad(...floor);
      const wallTop = floor.map(point => point.clone().add(new THREE.Vector3(0, 4.2, 0)));
      addQuad(wallTop[0], wallTop[3], floor[3], floor[0]); addQuad(wallTop[1], floor[1], floor[2], wallTop[2]);
      const trackSide = new THREE.Vector3(-direction.z, 0, direction.x);
      const trackStart = start.clone().add(new THREE.Vector3(0, -TUNNEL_DEPTH, 0));
      const trackEnd = end.clone().add(new THREE.Vector3(0, -TUNNEL_DEPTH, 0));
      const strip = (from, to, halfWidth, elevation, output) => {
        const left = trackSide.clone().multiplyScalar(halfWidth);
        const lift = new THREE.Vector3(0, elevation, 0);
        addQuad(from.clone().add(left).add(lift), from.clone().sub(left).add(lift), to.clone().sub(left).add(lift), to.clone().add(left).add(lift), output);
      };
      // The source gives a rail corridor axis, not gauge or sleeper engineering.
      strip(trackStart, trackEnd, 1.8, .02, trackVertices[0]);
      const length = Math.hypot(end.x-start.x, end.z-start.z);
      for (let distance = .6; distance < length; distance += 1.2) {
        const centre = trackStart.clone().lerp(trackEnd, distance/length);
        strip(centre.clone().addScaledVector(direction, -.14), centre.clone().addScaledVector(direction, .14), 1.3, .08, trackVertices[1]);
      }
      for (const offset of [-.75, .75]) {
        const lateral = trackSide.clone().multiplyScalar(offset);
        strip(trackStart.clone().add(lateral), trackEnd.clone().add(lateral), .11, .2, trackVertices[2]);
      }
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3)); geometry.computeVertexNormals();
    cutawayGroup.add(new THREE.Mesh(geometry, tunnelMaterial));
    for (let index = 0; index < trackVertices.length; index++) {
      const trackGeometry = new THREE.BufferGeometry();
      trackGeometry.setAttribute('position', new THREE.Float32BufferAttribute(trackVertices[index], 3));
      trackGeometry.computeVertexNormals();
      const mesh = new THREE.Mesh(trackGeometry, trackMaterials[index]);
      mesh.name = ['Illustrated track bed', 'Illustrated sleepers', 'Illustrated rails'][index];
      mesh.userData.source = data.source;
      mesh.userData.dimensions = 'Illustrated gauge 1.5 m, rail width 0.22 m, sleepers every 1.2 m; source corridor axis only';
      cutawayGroup.add(mesh);
    }
    const texture = new THREE.DataTexture(new Uint8Array([0]), 1, 1, THREE.RedFormat, THREE.UnsignedByteType);
    texture.minFilter = texture.magFilter = THREE.LinearFilter;
    texture.generateMipmaps = false; texture.needsUpdate = true;
    tunnelSegments = tunnels;
    maskMetresPerPixel = Infinity;
    cutawayMask = { texture, bounds: new THREE.Vector4(0, 0, 1, 1), illustrativeDepthMetres: TUNNEL_DEPTH, source: data.source, classification: 'BRT explicitly in tunnel', sourceSegmentCount: data.segments.filter(segment => segment.form === 'tunnel').length };
    updateCutawayMask(true);
    rebuild(true);
  }

  function updateCutawayMask(force = false) {
    if (!cutawayMask || !camera || !cutaway && !force) return;
    const started = performance.now(), visibleBounds = new THREE.Box3();
    const ray = new THREE.Raycaster(), plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
    for (const x of [-1, 1]) for (const y of [-1, 1]) {
      ray.setFromCamera(new THREE.Vector2(x, y), camera);
      const point = ray.ray.intersectPlane(plane, new THREE.Vector3());
      if (point) visibleBounds.expandByPoint(point);
    }
    if (visibleBounds.isEmpty()) return;
    // Reuse the padded viewport until a pan exits it or zoom changes by 25%.
    const metresPerPixel = span / viewportHeight;
    const viewDirection = camera.getWorldDirection(new THREE.Vector3());
    const apertureShift = viewDirection.clone().multiplyScalar(TUNNEL_DEPTH / Math.min(-0.1, viewDirection.y)).setY(0);
    const previous = cutawayMask.bounds;
    if (!force && maskViewDirection.distanceToSquared(viewDirection) < .000001 && metresPerPixel >= maskMetresPerPixel * .8 && metresPerPixel <= maskMetresPerPixel * 1.25 &&
      visibleBounds.min.x >= previous.x + 40 && visibleBounds.min.z >= previous.y + 40 &&
      visibleBounds.max.x <= previous.x + previous.z - 40 && visibleBounds.max.z <= previous.y + previous.w - 40) return;
    const size = visibleBounds.getSize(new THREE.Vector3());
    visibleBounds.min.x -= Math.max(80, size.x * .15); visibleBounds.max.x += Math.max(80, size.x * .15);
    visibleBounds.min.z -= Math.max(80, size.z * .15); visibleBounds.max.z += Math.max(80, size.z * .15);
    const sizeX = visibleBounds.max.x - visibleBounds.min.x, sizeZ = visibleBounds.max.z - visibleBounds.min.z;
    const width = Math.min(2048, Math.max(64, Math.ceil(sizeX / metresPerPixel)));
    const height = Math.min(2048, Math.max(64, Math.ceil(sizeZ / metresPerPixel)));
    const cellX = sizeX / width, cellZ = sizeZ / height, edgeWidth = Math.hypot(cellX, cellZ);
    const pixels = new Uint8Array(width * height), radius = CUTAWAY_HALF_WIDTH;
    for (const segment of tunnelSegments) {
      // An oblique cut follows the viewing rays from the real tunnel floor to
      // the ground. A narrow opening can reveal depth without erasing a 40 m
      // road-width stripe centred blindly above the tunnel.
      const start = segment.start.clone().add(apertureShift);
      const end = segment.end.clone().add(apertureShift);
      const padding = radius + edgeWidth;
      const left = Math.max(0, Math.floor((Math.min(start.x, end.x) - padding - visibleBounds.min.x) / cellX));
      const right = Math.min(width - 1, Math.ceil((Math.max(start.x, end.x) + padding - visibleBounds.min.x) / cellX));
      const top = Math.max(0, Math.floor((Math.min(start.z, end.z) - padding - visibleBounds.min.z) / cellZ));
      const bottom = Math.min(height - 1, Math.ceil((Math.max(start.z, end.z) + padding - visibleBounds.min.z) / cellZ));
      const dx = end.x - start.x, dz = end.z - start.z, lengthSquared = dx * dx + dz * dz || 1;
      for (let y = top; y <= bottom; y++) for (let x = left; x <= right; x++) {
        const px = visibleBounds.min.x + (x + .5) * cellX - start.x;
        const pz = visibleBounds.min.z + (y + .5) * cellZ - start.z;
        const fraction = THREE.MathUtils.clamp((px * dx + pz * dz) / lengthSquared, 0, 1);
        const distance = Math.hypot(px - fraction * dx, pz - fraction * dz);
        const coverage = Math.round(255 * THREE.MathUtils.clamp(.5 + (radius - distance) / edgeWidth, 0, 1));
        const index = y * width + x;
        if (coverage > pixels[index]) pixels[index] = coverage;
      }
    }
    cutawayMask.texture.image = { data: pixels, width, height };
    cutawayMask.texture.needsUpdate = true;
    cutawayMask.bounds.set(visibleBounds.min.x, visibleBounds.min.z, sizeX, sizeZ);
    maskMetresPerPixel = metresPerPixel;
    maskViewDirection.copy(viewDirection);
    maskRebuilds++; maskMilliseconds = performance.now() - started;
  }

  async function loadMetro(url = './data/transit/metro-physical.json.gz') {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Metro physical geometry HTTP ${response.status}`);
    let bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes[0] === 31 && bytes[1] === 139) bytes = new Uint8Array(await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer());
    setMetroData(JSON.parse(new TextDecoder().decode(bytes)));
    return cutawayMask;
  }

  function pick(raycaster) {
    const hits = raycaster.intersectObjects([...batches.values()].flatMap(batch => [batch.body, batch.roof]), false);
    const hit = hits.find(hit => {
      const batch = [...batches.values()].find(batch => batch.body === hit.object || batch.roof === hit.object);
      return cutaway || !batch.records[hit.instanceId].underground;
    });
    if (!hit) return null;
    const batch = [...batches.values()].find(batch => batch.body === hit.object || batch.roof === hit.object);
    const record = batch.records[hit.instanceId];
    return { ...record.report, presentation: { physicalForm: record.rail?.form || 'unclassified', sourceSegmentId: record.rail?.id || null, illustrativeDepthMetres: record.underground ? TUNNEL_DEPTH : null, orientation: record.orientation, dimensions: 'illustrative' } };
  }

  function metroVisibility() {
    const metros = records.filter(record => record.mode === 'metro');
    const inside = record => {
      if (!camera) return false;
      const position = record.ground.clone();
      position.y += record.underground ? -TUNNEL_DEPTH + 2 : 2;
      position.project(camera);
      return Math.abs(position.x) <= 1 && Math.abs(position.y) <= 1 && Math.abs(position.z) <= 1;
    };
    const visible = metros.filter(inside);
    const underground = visible.filter(record => record.underground);
    const fresh = record => record.report.freshness === 'fresh' && record.report.sourceConnected;
    return {
      metroObservations: metros.length,
      visibleMetroObservations: visible.length,
      visibleUndergroundObservations: underground.length,
      visibleFreshMetroObservations: visible.filter(fresh).length,
      visibleFreshUndergroundObservations: underground.filter(fresh).length,
      cutawayMessage: !cutaway ? null : underground.length
        ? `${underground.filter(fresh).length} fresh metro reports in this cutaway`
        : 'No metro report in this cutaway view',
    };
  }

  return {
    group,
    update(nextSnapshot) { snapshot = nextSnapshot; rebuild(true); },
    setView(view) { camera = view.camera || camera; span = view.span ?? span; viewportHeight = view.viewportHeight ?? viewportHeight; updateCutawayMask(); rebuild(); },
    setCutaway(enabled) { cutaway = typeof enabled === 'object' ? enabled.enabled : enabled; cutawayGroup.visible = cutaway; updateCutawayMask(); rebuild(); return cutawayMask; },
    getCutaway() { return cutawayMask; },
    setMetroData, loadMetro, pick,
    statistics() { return { ...metroVisibility(), observations: records.length, underground: records.filter(record => record.underground).length, batches: batches.size, drawCalls: [...batches.values()].filter(batch => batch.body.count).length * 2 + (cutaway ? cutawayGroup.children.length : 0), railSegments: railSegments.length, mask: cutawayMask ? { width: cutawayMask.texture.image.width, height: cutawayMask.texture.image.height, metresPerTexel: [cutawayMask.bounds.z / cutawayMask.texture.image.width, cutawayMask.bounds.w / cutawayMask.texture.image.height], rebuilds: maskRebuilds, milliseconds: maskMilliseconds } : null }; },
    dispose() {
      for (const batch of batches.values()) { batch.body.dispose(); batch.roof.dispose(); }
      for (const child of cutawayGroup.children) child.geometry.dispose();
      cutawayMask?.texture.dispose(); box.dispose(); bodyMaterial.dispose(); roofMaterial.dispose(); metroBodyMaterial.dispose(); metroRoofMaterial.dispose(); tunnelMaterial.dispose(); trackMaterials.forEach(material => material.dispose());
      group.removeFromParent(); group.clear(); batches.clear();
    },
  };
}
