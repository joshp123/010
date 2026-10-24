import * as THREE from 'three';
import { rightHandOffset, safeStep, followingDistance, speedForRoadClass } from './traffic-motion.js';
import { createJourneyPlanner } from './traffic-journeys.js';

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
export function createSimulatedTraffic({ project, localPosition, requestRender = () => {}, maximumVehicles = 320, vehiclesPerKilometre = 6, maximumSpan = 6500, bicycles = false } = {}) {
  const place = project || localPosition;
  const group = new THREE.Group(); group.name = bicycles ? 'Simulated cyclists' : 'Simulated road traffic'; group.userData.simulated = true;
  const geometry = new THREE.BoxGeometry(1, 1, 1);
  const material = new THREE.MeshStandardMaterial({ color: '#ffffff', roughness: .92, metalness: 0 });
  const roofMaterial = new THREE.MeshStandardMaterial({ color: '#52635f', roughness: .85, metalness: 0 });
  const body = new THREE.InstancedMesh(geometry, material, maximumVehicles), roof = new THREE.InstancedMesh(geometry, roofMaterial, maximumVehicles);
  body.name = bicycles ? 'Simulated riders' : 'Simulated cars'; roof.name = bicycles ? 'Rider heads' : 'Simulated car roofs'; body.count = roof.count = 0;
  body.instanceMatrix.setUsage(THREE.DynamicDrawUsage); roof.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  body.castShadow = true; body.receiveShadow = true; group.add(body, roof);
  const wheelGeometry = bicycles ? new THREE.TorusGeometry(.3, .055, 3, 8).rotateY(Math.PI / 2) : null;
  const bicycleMaterial = bicycles ? new THREE.MeshStandardMaterial({color:'#343e3d',roughness:1}) : null;
  const wheels = bicycles ? new THREE.InstancedMesh(wheelGeometry, bicycleMaterial, maximumVehicles * 2) : null;
  const frames = bicycles ? new THREE.InstancedMesh(geometry, bicycleMaterial, maximumVehicles * 3) : null;
  if (bicycles) {
    wheels.count = frames.count = 0;
    wheels.instanceMatrix.setUsage(THREE.DynamicDrawUsage); frames.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    wheels.name = 'Bicycle wheels'; frames.name = 'Bicycle frames'; group.add(wheels, frames);
    roofMaterial.color.set('#e2bf9a');
  }
  const cruiseSpeed = roadClass => bicycles ? 4.2 : speedForRoadClass(roadClass);
  const transform = new THREE.Object3D(), color = new THREE.Color(), position = new THREE.Vector3(), tangent = new THREE.Vector3();
  const frustum = new THREE.Frustum(), cameraMatrix = new THREE.Matrix4();
  let sourceNetwork = null, roads = [], planner = null, candidates = [], cars = [];
  let span = 1700, viewportHeight = 900, hasView = false, enabled = true, paused = false, lastTime = null, elapsed = 0, sequence = 1;
  let desiredCount = 0, seeded = false, plannedJourneys = 0, completedJourneys = 0;
  const unroutableOrigins = new Set();
  const nextPosition = new THREE.Vector3(), cornerTangent = new THREE.Vector3();

  function random() { sequence = (Math.imul(sequence, 1664525) + 1013904223) >>> 0; return sequence / 4294967296; }
  function inside(point) { return !hasView || frustum.containsPoint(point); }
  function locate(road, distance) {
    let index = 1;
    while (index < road.distances.length - 1 && road.distances[index] < distance) index++;
    const start = road.points[index - 1], end = road.points[index];
    position.copy(start).lerp(end, (distance - road.distances[index - 1]) / (road.distances[index] - road.distances[index - 1] || 1));
    tangent.subVectors(end, start).normalize();
    // Rotate the lane normal through a surveyed bend instead of switching its
    // offset abruptly at a polyline vertex. The centreline position is unchanged.
    const fromStart = distance - road.distances[index - 1], toEnd = road.distances[index] - distance;
    const cornerRadius = Math.min(3, (road.distances[index] - road.distances[index - 1]) / 2);
    if (index > 1 && fromStart < cornerRadius) {
      cornerTangent.subVectors(start, road.points[index - 2]).normalize();
      tangent.lerp(cornerTangent, .5 * (1 - Math.max(0, fromStart) / cornerRadius)).normalize();
    }
    if (index < road.points.length - 1 && toEnd < cornerRadius) {
      cornerTangent.subVectors(road.points[index + 1], end).normalize();
      tangent.lerp(cornerTangent, .5 * (1 - Math.max(0, toEnd) / cornerRadius)).normalize();
    }
  }

  function setRoads(network, preserveCars = false) {
    const previousCars = preserveCars ? cars : [];
    sourceNetwork = network; roads = []; cars = []; lastTime = null; unroutableOrigins.clear();
    for (const source of network.roads) {
      if (source.coordinates.length < 2 || ![1, 2, 3].includes(source.direction)) continue;
      const points = source.coordinates.map(([longitude, latitude]) => place(latitude, longitude, .2, { source: 'NWB', roadId: source.id, roadClass: source.roadClass }));
      const distances = [0];
      for (let index = 1; index < points.length; index++) distances.push(distances.at(-1) + Math.hypot(points[index].x - points[index - 1].x, points[index].z - points[index - 1].z));
      if (distances.at(-1) < .1) continue;
      const road = { ...source, sourceIndex: roads.length, points, distances, length: distances.at(-1), bounds: new THREE.Box3().setFromPoints(points).expandByScalar(5) };
      roads.push(road);
    }
    planner = createJourneyPlanner(roads);
    if (preserveCars) {
      cars = previousCars.flatMap(car => {
        const road = roads[car.road.sourceIndex];
        if (!road || road.id !== car.road.id) return [];
        const journey = { ...car.journey, path: car.journey.path.map(step => ({ ...step, road: roads[step.roadIndex] })) };
        if (journey.path.some(step => !step.road)) return [];
        if (journey.path.some((step, index) => index && !planner.transitions(journey.path[index - 1].roadIndex, journey.path[index - 1].direction).some(next => next.roadIndex === step.roadIndex && next.direction === step.direction))) return [];
        return [{ ...car, road, journey, distance: car.distance / car.road.length * road.length, next: journey.path[car.journeyIndex + 1] || null }];
      });
    } else { seeded = false; plannedJourneys = 0; completedJourneys = 0; }
    selectRoads(!preserveCars); render();
  }

  function selectRoads(allowInterior = true) {
    candidates = roads.filter(road => !hasView || frustum.intersectsBox(road.bounds));
    desiredCount = Math.min(maximumVehicles, Math.round(candidates.reduce((length, road) => length + road.length, 0) * vehiclesPerKilometre / 1000));
    cars = cars.filter(car => { locate(car.road, car.distance); return inside(position); }).slice(0, desiredCount);
    populate(allowInterior); seeded = true;
  }

  function populate(allowInterior = false) {
    if (!candidates.length || !group.visible) return;
    let attempts = 0;
    while (cars.length < desiredCount && attempts++ < desiredCount * 12) {
      const road = candidates[Math.floor(random() * candidates.length)], distance = random() * road.length;
      locate(road, distance);
      if (!inside(position)) continue;
      const direction = road.direction === 3 ? random() > .5 ? 1 : -1 : road.direction === 1 ? 1 : -1;
      // After a view change seed its roads once. Replacement traffic must enter at
      // the view edge; a dead-end car no longer teleports to a random visible street.
      if (!allowInterior && seeded) {
        nextPosition.copy(position).addScaledVector(tangent.clone().normalize(), -direction * 25);
        if (!hasView || inside(nextPosition)) continue;
      }
      if (cars.some(car => car.road === road && Math.abs(car.distance - distance) < 14)) continue;
      const originKey = `${road.sourceIndex}:${direction}`;
      if (unroutableOrigins.has(originKey)) continue;
      const journey = planner.plan({ roadIndex: road.sourceIndex, direction, random,
        minDistance: bicycles ? 150 : 350, maxDistance: bicycles ? 1800 : 4000,
        preferDestination: point => hasView && !inside(point) });
      if (!journey) { unroutableOrigins.add(originKey); continue; }
      plannedJourneys++;
      cars.push({ road, distance, direction, journey, journeyIndex: 0, next: journey.path[1] || null, ending: journey.path.length === 1,
        speed: 0, cruise: cruiseSpeed(road.roadClass) * (.85 + random() * .3),
        heading: Math.atan2(tangent.x * direction, tangent.z * direction), age: allowInterior ? 1 : 0,
        color: PALETTE[Math.floor(random() * PALETTE.length)] });
    }
  }

  function render() {
    let count = 0;
    for (const car of cars) {
      locate(car.road, car.distance);
      if (!inside(position)) continue;
      const [laneX, laneZ] = rightHandOffset(tangent.x, tangent.z, car.direction, car.distance, car.road.length, car.road.direction === 3);
      position.x += laneX * (bicycles ? .35 : 1); position.z += laneZ * (bicycles ? .35 : 1);
      // Keep city vehicles in scale; zoom must not turn cars into buses.
      const endDistance = car.direction === 1 ? car.road.length - car.distance : car.distance;
      const fade = Math.min(1, car.age * 2, car.next === null && car.ending ? endDistance / 8 : 1);
      const scale = Math.max(0, fade);
      transform.rotation.set(0, car.heading, 0);
      if (bicycles) {
        transform.position.copy(position); transform.position.y += .55 * scale;
        transform.scale.set(.14 * scale, .14 * scale, 1.05 * scale); transform.updateMatrix(); frames.setMatrixAt(count * 3, transform.matrix);
        for (let leg = 0; leg < 2; leg++) {
          transform.position.copy(position); transform.position.y += .57 * scale;
          const lateral = (leg ? .15 : -.15) * scale;
          transform.position.x += Math.cos(car.heading) * lateral;
          transform.position.z -= Math.sin(car.heading) * lateral;
          transform.rotation.set(Math.sin(car.distance * 1.8 + leg * Math.PI) * .35, car.heading, 0, 'YXZ');
          transform.scale.set(.12 * scale, .46 * scale, .13 * scale); transform.updateMatrix(); frames.setMatrixAt(count * 3 + leg + 1, transform.matrix);
        }
        transform.rotation.set(0, car.heading, 0);
        for (let wheel = 0; wheel < 2; wheel++) {
          transform.position.copy(position); transform.position.y += .3 * scale;
          const longitudinal = (wheel ? .55 : -.55) * scale;
          transform.position.x += Math.sin(car.heading) * longitudinal;
          transform.position.z += Math.cos(car.heading) * longitudinal;
          transform.scale.setScalar(scale); transform.updateMatrix(); wheels.setMatrixAt(count * 2 + wheel, transform.matrix);
        }
        transform.position.copy(position); transform.position.y += 1.05 * scale;
        transform.scale.set(.42 * scale, .62 * scale, .35 * scale); transform.updateMatrix(); body.setMatrixAt(count, transform.matrix);
        body.setColorAt(count, color.set(car.color));
        transform.position.y += .43 * scale; transform.scale.set(.28 * scale, .28 * scale, .28 * scale); transform.updateMatrix(); roof.setMatrixAt(count, transform.matrix);
      } else {
        transform.position.copy(position); transform.position.y += .7 * scale;
        transform.scale.set(1.75 * scale, 1.4 * scale, 4.2 * scale); transform.updateMatrix(); body.setMatrixAt(count, transform.matrix);
        body.setColorAt(count, color.set(car.color));
        transform.position.y += .72 * scale; transform.scale.set(1.45 * scale, .35 * scale, 2.25 * scale); transform.updateMatrix(); roof.setMatrixAt(count, transform.matrix);
      }
      count++;
    }
    body.count = roof.count = count; body.instanceMatrix.needsUpdate = roof.instanceMatrix.needsUpdate = true;
    if (bicycles) {
      wheels.count = count * 2; frames.count = count * 3;
      wheels.instanceMatrix.needsUpdate = frames.instanceMatrix.needsUpdate = true;
      wheels.computeBoundingSphere(); frames.computeBoundingSphere();
    }
    if (body.instanceColor) body.instanceColor.needsUpdate = true;
    body.computeBoundingSphere(); roof.computeBoundingSphere(); group.updateMatrixWorld(true); requestRender();
  }

  async function load(url = bicycles ? './data/traffic/cycleways.pb.gz' : './data/traffic/roads.pb.gz') {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Traffic roads HTTP ${response.status}`);
    let bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes[0] === 31 && bytes[1] === 139) bytes = new Uint8Array(await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer());
    setRoads(decodeTrafficRoads(bytes));
    return statistics();
  }

  function statistics() { return { simulated: true, sourceRoads: roads.length, visibleRoads: candidates.length, cars: bicycles ? 0 : body.count, cyclists: bicycles ? body.count : 0, vehicles: body.count, maximumVehicles, drawCalls: body.count && group.visible ? (bicycles ? 4 : 2) : 0, paused, enabled, simulationSeconds: elapsed, plannedJourneys, completedJourneys, unroutableOrigins: unroutableOrigins.size, network: planner?.diagnostics() || null }; }

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
      const delta = safeStep(lastTime === null ? 0 : timeSeconds - lastTime); lastTime = timeSeconds;
      if (paused || !group.visible || !roads.length || !cars.length) return false;
      elapsed += delta;
      const junctionReservations = new Map();
      cars = cars.filter(car => {
        car.age += delta;
        let endDistance = car.direction === 1 ? car.road.length - car.distance : car.distance;
        let targetSpeed = car.cruise;
        // Brake into the planned turn. Trip demand is illustrative; legal turn restrictions are not in this source.
        if (car.next && car.next.weight < 5) targetSpeed = Math.min(targetSpeed, 3.5 + endDistance * .25);
        for (const other of cars) {
          if (other === car || other.road !== car.road || other.direction !== car.direction) continue;
          const gap = (other.distance - car.distance) * car.direction;
          if (gap > 0 && gap < followingDistance(car.speed)) targetSpeed = Math.min(targetSpeed, Math.max(0, (gap - 5.5) / 1.4));
        }
        const junction = car.direction === 1 ? car.road.end : car.road.start;
        if (junction && endDistance < 10 && !car.ending) {
          if (junctionReservations.has(junction)) targetSpeed = Math.min(targetSpeed, Math.max(0, (endDistance - 3) * .6));
          else junctionReservations.set(junction, car);
        }
        car.speed += THREE.MathUtils.clamp(targetSpeed - car.speed, -6 * delta, 2 * delta);
        let remaining = delta * car.speed;
        while (remaining > 0) {
          const available = car.direction === 1 ? car.road.length - car.distance : car.distance;
          if (remaining < available) { car.distance += remaining * car.direction; break; }
          remaining -= available;
          const next = car.next;
          if (!next) { completedJourneys++; return false; }
          car.road = next.road; car.direction = next.direction; car.distance = car.direction === 1 ? 0 : car.road.length;
          car.journeyIndex++; car.next = car.journey.path[car.journeyIndex + 1] || null; car.ending = !car.next;
          car.cruise = cruiseSpeed(car.road.roadClass);
        }
        locate(car.road, car.distance);
        const desiredHeading = Math.atan2(tangent.x * car.direction, tangent.z * car.direction);
        const angle = Math.atan2(Math.sin(desiredHeading - car.heading), Math.cos(desiredHeading - car.heading));
        car.heading += THREE.MathUtils.clamp(angle, -2.8 * delta, 2.8 * delta);
        return inside(position);
      });
      populate(); render(); return cars.length > 0;
    },
    setPaused(value) { paused = value; lastTime = null; requestRender(); },
    setEnabled(value) { enabled = value; group.visible = enabled && span <= maximumSpan; lastTime = null; if (enabled) { selectRoads(); render(); } else requestRender(); },
    refreshProjection() { if (sourceNetwork) setRoads(sourceNetwork, true); },
    statistics,
    dispose() { group.removeFromParent(); group.clear(); body.dispose(); roof.dispose(); geometry.dispose(); wheels?.dispose(); frames?.dispose(); wheelGeometry?.dispose(); bicycleMaterial?.dispose(); material.dispose(); roofMaterial.dispose(); roads = []; cars = []; planner = null; unroutableOrigins.clear(); },
  };
}
