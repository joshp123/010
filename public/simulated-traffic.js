import * as THREE from 'three';

class RoadReader {
  constructor(bytes) { this.bytes = bytes; this.offset = 0; }
  integer() {
    let value = 0, factor = 1;
    while (this.offset < this.bytes.length) {
      const byte = this.bytes[this.offset++]; value += (byte & 127) * factor;
      if (!(byte & 128)) return value;
      factor *= 128;
    }
    throw new Error('Truncated road protobuf');
  }
  fields(consume) {
    while (this.offset < this.bytes.length) {
      const tag = this.integer(), field = tag >> 3, wire = tag & 7;
      if (wire === 0) consume(field, this.integer());
      else if (wire === 2) {
        const length = this.integer(), end = this.offset + length;
        if (end > this.bytes.length) throw new Error('Truncated road protobuf block');
        const bytes = this.bytes.subarray(this.offset, end); this.offset = end; consume(field, bytes);
      } else throw new Error(`Unsupported road protobuf wire type ${wire}`);
    }
  }
}

export function decodeTrafficRoads(bytes) {
  const network = { version: 0, roads: [] }, text = new TextDecoder();
  new RoadReader(bytes).fields((field, value) => {
    if (field === 1) network.version = value;
    if (field !== 2) return;
    const road = { id: 0, start: 0, end: 0, direction: 0, coordinates: [], roadClass: '' };
    new RoadReader(value).fields((key, content) => {
      if (key <= 4) road[['', 'id', 'start', 'end', 'direction'][key]] = content;
      if (key === 6) road.roadClass = text.decode(content);
      if (key === 5) {
        const reader = new RoadReader(content), previous = [0, 0];
        while (reader.offset < reader.bytes.length) {
          const point = [];
          for (let axis = 0; axis < 2; axis++) {
            const encoded = reader.integer(); previous[axis] += encoded % 2 ? -(encoded + 1) / 2 : encoded / 2; point.push(previous[axis] / 1e7);
          }
          road.coordinates.push(point);
        }
      }
    });
    network.roads.push(road);
  });
  if (network.version !== 1) throw new Error(`Unsupported road network version ${network.version}`);
  return network;
}

const PALETTE = ['#d1d0bf', '#697e7c', '#ac6f5c', '#dbd8cb', '#596765', '#b09b72'];

// This is decorative simulation on source roads, independent of live transit.
// Parent drives advance(seconds); this module never owns an animation timer.
export function createSimulatedTraffic({ project, localPosition, requestRender = () => {}, maximumVehicles = 320, vehiclesPerKilometre = 6, maximumSpan = 6500 } = {}) {
  const place = project || localPosition;
  const group = new THREE.Group(); group.name = 'Simulated road traffic'; group.userData.simulated = true;
  const geometry = new THREE.BoxGeometry(1, 1, 1);
  const material = new THREE.MeshStandardMaterial({ color: '#ffffff', roughness: .92, metalness: 0 });
  const roofMaterial = new THREE.MeshStandardMaterial({ color: '#52635f', roughness: .85, metalness: 0 });
  const body = new THREE.InstancedMesh(geometry, material, maximumVehicles), roof = new THREE.InstancedMesh(geometry, roofMaterial, maximumVehicles);
  body.name = 'Simulated cars'; roof.name = 'Simulated car roofs'; body.count = roof.count = 0;
  body.instanceMatrix.setUsage(THREE.DynamicDrawUsage); roof.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  body.castShadow = true; body.receiveShadow = true; group.add(body, roof);
  const transform = new THREE.Object3D(), color = new THREE.Color(), position = new THREE.Vector3(), tangent = new THREE.Vector3();
  const frustum = new THREE.Frustum(), cameraMatrix = new THREE.Matrix4();
  let sourceNetwork = null, roads = [], outgoing = new Map(), candidates = [], cars = [];
  let span = 1700, viewportHeight = 900, hasView = false, enabled = true, paused = false, lastTime = null, elapsed = 0, sequence = 1;
  let desiredCount = 0;

  function random() { sequence = (Math.imul(sequence, 1664525) + 1013904223) >>> 0; return sequence / 4294967296; }
  function inside(point) { return !hasView || frustum.containsPoint(point); }
  function locate(road, distance) {
    let index = 1;
    while (index < road.distances.length - 1 && road.distances[index] < distance) index++;
    const start = road.points[index - 1], end = road.points[index];
    position.copy(start).lerp(end, (distance - road.distances[index - 1]) / (road.distances[index] - road.distances[index - 1] || 1));
    tangent.subVectors(end, start);
  }

  function setRoads(network) {
    sourceNetwork = network; roads = []; outgoing = new Map(); cars = []; lastTime = null;
    for (const source of network.roads) {
      const points = source.coordinates.map(([longitude, latitude]) => place(latitude, longitude, .2, { source: 'NWB', roadId: source.id, roadClass: source.roadClass }));
      const distances = [0];
      for (let index = 1; index < points.length; index++) distances.push(distances.at(-1) + points[index].distanceTo(points[index - 1]));
      const road = { ...source, points, distances, length: distances.at(-1), bounds: new THREE.Box3().setFromPoints(points).expandByScalar(5) };
      roads.push(road);
      for (const direction of source.direction === 3 ? [1, -1] : [source.direction === 1 ? 1 : -1]) {
        const start = direction === 1 ? road.start : road.end;
        if (start) { if (!outgoing.has(start)) outgoing.set(start, []); outgoing.get(start).push({ road, direction }); }
      }
    }
    selectRoads(); render();
  }

  function nextRoad(car) {
    const end = car.direction === 1 ? car.road.end : car.road.start;
    const endpoint = car.direction === 1 ? car.road.points.at(-1) : car.road.points[0];
    const options = (outgoing.get(end) || []).filter(next => next.road !== car.road && endpoint.distanceTo(next.direction === 1 ? next.road.points[0] : next.road.points.at(-1)) <= .5);
    return options.length ? options[Math.floor(random() * options.length)] : null;
  }

  function selectRoads() {
    candidates = roads.filter(road => !hasView || frustum.intersectsBox(road.bounds));
    desiredCount = Math.min(maximumVehicles, Math.round(candidates.reduce((length, road) => length + road.length, 0) * vehiclesPerKilometre / 1000));
    cars = cars.filter(car => { locate(car.road, car.distance); return inside(position); }).slice(0, desiredCount);
    populate();
  }

  function populate() {
    if (!candidates.length || !group.visible) return;
    let attempts = 0;
    while (cars.length < desiredCount && attempts++ < desiredCount * 12) {
      const road = candidates[Math.floor(random() * candidates.length)], distance = random() * road.length;
      locate(road, distance);
      if (!inside(position)) continue;
      const direction = road.direction === 3 ? random() > .5 ? 1 : -1 : road.direction === 1 ? 1 : -1;
      const motorway = road.roadClass === 'HR';
      cars.push({ road, distance, direction, speed: motorway ? 16 + random() * 9 : 5 + random() * 5, color: PALETTE[Math.floor(random() * PALETTE.length)] });
    }
  }

  function render() {
    let count = 0;
    for (const car of cars) {
      locate(car.road, car.distance);
      if (!inside(position)) continue;
      // No lane or corner interpolation: every centre stays on a source segment.
      const scale = THREE.MathUtils.clamp(2 * span / viewportHeight / 4.2, 1, 2);
      transform.position.copy(position); transform.position.y += .7 * scale;
      transform.rotation.set(0, Math.atan2(tangent.x * car.direction, tangent.z * car.direction), 0);
      transform.scale.set(1.75 * scale, 1.4 * scale, 4.2 * scale); transform.updateMatrix(); body.setMatrixAt(count, transform.matrix);
      body.setColorAt(count, color.set(car.color));
      transform.position.y += .72 * scale; transform.scale.set(1.45 * scale, .35 * scale, 2.25 * scale); transform.updateMatrix(); roof.setMatrixAt(count, transform.matrix);
      count++;
    }
    body.count = roof.count = count; body.instanceMatrix.needsUpdate = roof.instanceMatrix.needsUpdate = true;
    if (body.instanceColor) body.instanceColor.needsUpdate = true;
    body.computeBoundingSphere(); roof.computeBoundingSphere(); group.updateMatrixWorld(true); requestRender();
  }

  async function load(url = './data/traffic/roads.pb.gz') {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Traffic roads HTTP ${response.status}`);
    let bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes[0] === 31 && bytes[1] === 139) bytes = new Uint8Array(await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer());
    setRoads(decodeTrafficRoads(bytes));
    return statistics();
  }

  function statistics() { return { simulated: true, sourceRoads: roads.length, visibleRoads: candidates.length, cars: body.count, maximumVehicles, drawCalls: body.count && group.visible ? 2 : 0, paused, enabled, simulationSeconds: elapsed }; }

  return {
    group, load, setRoads,
    setView({ camera, span: nextSpan = span, viewportHeight: nextHeight = viewportHeight }) {
      span = nextSpan; viewportHeight = nextHeight;
      if (camera) { camera.updateMatrixWorld(); cameraMatrix.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse); frustum.setFromProjectionMatrix(cameraMatrix); hasView = true; }
      const visible = enabled && span <= maximumSpan;
      if (group.visible !== visible) lastTime = null;
      group.visible = visible;
      selectRoads(); render();
    },
    advance(timeSeconds) {
      const delta = lastTime === null ? 0 : Math.max(0, timeSeconds - lastTime); lastTime = timeSeconds;
      if (paused || !group.visible || !roads.length || !cars.length) return false;
      elapsed += delta;
      cars = cars.filter(car => {
        let remaining = delta * car.speed;
        while (remaining > 0) {
          const available = car.direction === 1 ? car.road.length - car.distance : car.distance;
          if (remaining < available) { car.distance += remaining * car.direction; break; }
          remaining -= available;
          const next = nextRoad(car);
          if (!next) return false;
          car.road = next.road; car.direction = next.direction; car.distance = car.direction === 1 ? 0 : car.road.length;
        }
        locate(car.road, car.distance); return inside(position);
      });
      populate(); render(); return cars.length > 0;
    },
    setPaused(value) { paused = value; lastTime = null; requestRender(); },
    setEnabled(value) { enabled = value; group.visible = enabled && span <= maximumSpan; lastTime = null; if (enabled) { selectRoads(); render(); } else requestRender(); },
    refreshProjection() { if (sourceNetwork) setRoads(sourceNetwork); },
    statistics,
    dispose() { group.removeFromParent(); group.clear(); body.dispose(); roof.dispose(); geometry.dispose(); material.dispose(); roofMaterial.dispose(); roads = []; cars = []; outgoing.clear(); },
  };
}
