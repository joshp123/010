import { createTrafficCoordinator } from './traffic-coordinator.js';
import { projectSourceRoadSurface } from './traffic-surface-projection.js';
import * as THREE from 'three';
import { journeyLaneOffset, safeStep, routeFollowingGap, speedForRoadClass, applyReviewedRoadGeometry, applySurfaceProfiles } from './traffic-motion.js';
import { createJourneyPlanner } from './traffic-journeys.js';
import { createCarGeometries, createBicycleGeometries } from './traffic-models.js';

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
export function createSimulatedTraffic({ project, localPosition, requestRender = () => {}, maximumVehicles = 320, vehiclesPerKilometre = 6, maximumSpan = 6500, bicycles = false, coordinator = createTrafficCoordinator() } = {}) {
  const place = project || localPosition;
  const group = new THREE.Group(); group.name = bicycles ? 'Simulated cyclists' : 'Simulated road traffic'; group.userData.simulated = true;
  const models=bicycles?createBicycleGeometries():createCarGeometries();
  const geometry = new THREE.BoxGeometry(1, 1, 1);
  const material = new THREE.MeshStandardMaterial({ color: '#ffffff', roughness: .92, metalness: 0 });
  const roofMaterial = new THREE.MeshStandardMaterial({ color: bicycles?'#e2bf9a':'#405451', roughness: .65, metalness: 0 });
  const detailMaterial = new THREE.MeshStandardMaterial({color:'#ffffff',vertexColors:true,roughness:.95});
  const darkMaterial = new THREE.MeshStandardMaterial({color:'#303a37',roughness:1});
  const body = new THREE.InstancedMesh(models.body, material, maximumVehicles), roof = new THREE.InstancedMesh(bicycles?models.head:models.glass, roofMaterial, maximumVehicles);
  body.name = bicycles ? 'Simulated riders' : 'Simulated cars'; roof.name = bicycles ? 'Rider heads' : 'Car glazing';
  body.castShadow = true; body.receiveShadow = true; group.add(body, roof);
  const details=new THREE.InstancedMesh(bicycles?models.frame:models.trim,detailMaterial,maximumVehicles);details.name=bicycles?'Bicycle frames':'Car wheels and trim';group.add(details);
  const wheels = bicycles ? new THREE.InstancedMesh(models.wheel, darkMaterial, maximumVehicles * 2) : null;
  const legs = bicycles ? new THREE.InstancedMesh(geometry, darkMaterial, maximumVehicles * 4) : null;
  if(bicycles) {wheels.name='Bicycle wheels';legs.name='Rider legs';group.add(wheels,legs);}
  const meshes=[body,roof,details,...(bicycles?[wheels,legs]:[])];
  for(const mesh of meshes) {mesh.count=0;mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);}
  const localTransform=new THREE.Object3D(),modelMatrix=new THREE.Matrix4(),legStart=new THREE.Vector3(),legEnd=new THREE.Vector3(),legDirection=new THREE.Vector3(),up=new THREE.Vector3(0,1,0);
  const cruiseSpeed = roadClass => bicycles ? 4.2 : speedForRoadClass(roadClass);
  const transform = new THREE.Object3D(), color = new THREE.Color(), position = new THREE.Vector3(), tangent = new THREE.Vector3();
  const frustum = new THREE.Frustum(), cameraMatrix = new THREE.Matrix4();
  let restrictionStatus=bicycles?'not-applicable':'not-loaded';
  let geometryStatus=bicycles?'original-bicycle-network':'not-loaded';
  let surfaceProfileStatus='not-loaded';
  let sourceNetwork = null, roads = [], planner = null, candidates = [], cars = [];
  const unregisterTraffic = coordinator.register(() => paused || !group.visible ? [] : cars);
  let span = 1700, viewportHeight = 900, hasView = false, enabled = true, paused = false, lastTime = null, elapsed = 0, sequence = 1, nextVehicleId = 1;
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
    coordinator.clear();
    const previousCars = preserveCars ? cars : [];
    sourceNetwork = network; roads = []; cars = []; lastTime = null; unroutableOrigins.clear();
    for (const source of network.roads) {
      if (source.coordinates.length < 2 || ![1, 2, 3].includes(source.direction)) continue;
      const { points, coordinates } = projectSourceRoadSurface(source, place);
      const distances = [0];
      for (let index = 1; index < points.length; index++) distances.push(distances.at(-1) + Math.hypot(points[index].x - points[index - 1].x, points[index].z - points[index - 1].z));
      if (distances.at(-1) < .1) continue;
      const road = { ...source, sourceCoordinates: source.coordinates, coordinates, sourceIndex: roads.length, points, distances, length: distances.at(-1), bounds: new THREE.Box3().setFromPoints(points).expandByScalar(5) };
      roads.push(road);
    }
    planner = createJourneyPlanner(roads,{turnRestrictions:bicycles?[]:(network.turnRestrictions||[])});
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
      // Let traffic enter crossings through yielding, rather than appear inside
      // an occupied junction when a new view is seeded.
      if ((road.start && distance < 8) || (road.end && road.length - distance < 8)) continue;
      locate(road, distance);
      if (!inside(position)) continue;
      const direction = road.direction === 3 ? random() > .5 ? 1 : -1 : road.direction === 1 ? 1 : -1;
      // After a view change seed its roads once. Replacement traffic must enter at
      // the view edge; a dead-end car no longer teleports to a random visible street.
      if (!allowInterior && seeded) {
        nextPosition.copy(position).addScaledVector(tangent.clone().normalize(), -direction * 25);
        if (!hasView || inside(nextPosition)) continue;
      }
      if (coordinator.occupied(road.id, distance, 14)) continue;
      const originKey = `${road.sourceIndex}:${direction}`;
      if (unroutableOrigins.has(originKey)) continue;
      const journey = planner.plan({ roadIndex: road.sourceIndex, direction, random,
        minDistance: bicycles ? 150 : 350, maxDistance: bicycles ? 1800 : 4000,
        preferDestination: point => hasView && !inside(point) });
      if (!journey) { unroutableOrigins.add(originKey); continue; }
      plannedJourneys++;
      cars.push({ vehicleId:nextVehicleId++, road, distance, direction, journey, journeyIndex: 0, next: journey.path[1] || null, ending: journey.path.length === 1,
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
      const [laneX, laneZ] = journeyLaneOffset(car, tangent);
      position.x += laneX * (bicycles ? .35 : 1); position.z += laneZ * (bicycles ? .35 : 1);
      // Keep city vehicles in scale; zoom must not turn cars into buses.
      const endDistance = car.direction === 1 ? car.road.length - car.distance : car.distance;
      const fade = Math.min(1, car.age * 2, car.next === null && car.ending ? endDistance / 8 : 1);
      const scale = Math.max(0, fade);
      transform.position.copy(position);transform.rotation.set(0,car.heading,0);transform.scale.setScalar(scale);transform.updateMatrix();
      body.setMatrixAt(count,transform.matrix);roof.setMatrixAt(count,transform.matrix);details.setMatrixAt(count,transform.matrix);
      body.setColorAt(count,color.set(car.color));
      if(bicycles) {
        for(let wheel=0;wheel<2;wheel++) {
          localTransform.position.set(0,.32,wheel?.56:-.56);localTransform.rotation.set(0,0,0);localTransform.scale.setScalar(1);localTransform.updateMatrix();
          wheels.setMatrixAt(count*2+wheel,modelMatrix.multiplyMatrices(transform.matrix,localTransform.matrix));
        }
        // Two bent legs follow a modest pedal circle, never a whole-body wobble.
        for(let side=0;side<2;side++) {
          const x=side?.14:-.14,phase=car.distance*1.8+side*Math.PI;
          const hip=[x,.99,-.20],knee=[x,.66,.09+Math.sin(phase)*.10],foot=[x,.35+Math.cos(phase)*.12,-.05+Math.sin(phase)*.12];
          for(let part=0;part<2;part++) {
            legStart.fromArray(part?knee:hip);legEnd.fromArray(part?foot:knee);legDirection.subVectors(legEnd,legStart);
            localTransform.position.copy(legStart).add(legEnd).multiplyScalar(.5);localTransform.quaternion.setFromUnitVectors(up,legDirection.clone().normalize());localTransform.scale.set(.12,legDirection.length(),.12);localTransform.updateMatrix();
            legs.setMatrixAt(count*4+side*2+part,modelMatrix.multiplyMatrices(transform.matrix,localTransform.matrix));
          }
        }
      }
      count++;
    }
    body.count=roof.count=details.count=count;
    if(bicycles){wheels.count=count*2;legs.count=count*4;}
    for(const mesh of meshes){mesh.instanceMatrix.needsUpdate=true;mesh.computeBoundingSphere();}
    if(body.instanceColor)body.instanceColor.needsUpdate=true;
    group.updateMatrixWorld(true);requestRender();
  }

  async function load(url = bicycles ? './data/traffic/cycleways.pb.gz' : './data/traffic/roads.pb.gz') {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Traffic roads HTTP ${response.status}`);
    let bytes = new Uint8Array(await response.arrayBuffer());
    if (bytes[0] === 31 && bytes[1] === 139) bytes = new Uint8Array(await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer());
    const network=decodeTrafficRoads(bytes);
    if(!bicycles) {
      try {
        const response=await fetch('./data/traffic/turn-restrictions.json');
        if(!response.ok)throw new Error(`HTTP ${response.status}`);
        const data=await response.json();
        if(data.version!==1 || data.mode!=='motorcar' || !Array.isArray(data.rules))throw new Error('Unsupported turn restriction format');
        network.turnRestrictions=data.rules;restrictionStatus=`loaded:${data.rules.length}`;
      } catch(error) {restrictionStatus=`unavailable:${error.message}`;}
      try {
        const response=await fetch('./data/traffic/road-geometry.json');
        if(!response.ok)throw new Error(`HTTP ${response.status}`);
        geometryStatus=`reviewed:${applyReviewedRoadGeometry(network,await response.json())}`;
      } catch(error) {geometryStatus=`original:${error.message}`;}
    }
    try {
      const response=await fetch('./data/traffic/surface-profiles.json');
      if(!response.ok)throw new Error(`HTTP ${response.status}`);
      surfaceProfileStatus=`loaded:${applySurfaceProfiles(network,await response.json())}`;
    } catch(error) {surfaceProfileStatus=`original:${error.message}`;}
    setRoads(network);
    return statistics();
  }

  // On-demand inspection only: no extra tracking, allocations or raycasts in
  // advance/render. Read the exact instanced base matrix used by the last render.
  function sampleVehicles({limit=8,roadId=null,near=null,radius=Infinity}={}) {
    const samples=[],matrix=new THREE.Matrix4(),centre=new THREE.Vector3();let instanceIndex=0;
    const cap=Math.max(0,Math.min(64,Math.floor(Number(limit)||0)));
    if(!group.visible||!cap)return samples;
    for(const car of cars) {
      let segment=1;while(segment<car.road.distances.length-1&&car.road.distances[segment]<car.distance)segment++;
      const fraction=(car.distance-car.road.distances[segment-1])/(car.road.distances[segment]-car.road.distances[segment-1]||1);
      centre.copy(car.road.points[segment-1]).lerp(car.road.points[segment],fraction);
      if(!inside(centre))continue;
      const index=instanceIndex++;
      if(index>=body.count)break;
      if(roadId!==null&&car.road.id!==Number(roadId))continue;
      body.getMatrixAt(index,matrix);
      const base=new THREE.Vector3().setFromMatrixPosition(matrix);
      if(near&&Math.hypot(base.x-near.x,base.z-near.z)>radius)continue;
      const a=car.road.coordinates[segment-1],b=car.road.coordinates[segment];
      samples.push({vehicleId:car.vehicleId,instanceIndex:index,mode:bicycles?'bicycle':'motorcar',roadId:car.road.id,roadClass:car.road.roadClass,direction:car.direction,
        distanceMetres:car.distance,roadLengthMetres:car.road.length,headingRadians:car.heading,speedMetresPerSecond:car.speed,
        sourcePosition:{longitude:a[0]+(b[0]-a[0])*fraction,latitude:a[1]+(b[1]-a[1])*fraction},
        geometryEvidence:car.road.geometryEvidence||'original NWB',
        surfaceProfileEvidence:car.road.surfaceProfileEvidence||null,
        sourceCentreline:centre.toArray(),localBasePosition:base.toArray(),worldBasePosition:base.clone().applyMatrix4(group.matrixWorld).toArray(),
        laneOffset:[base.x-centre.x,base.z-centre.z],screenNDC:hasView?base.clone().applyMatrix4(group.matrixWorld).applyMatrix4(cameraMatrix).toArray():null,
        modelScale:Math.hypot(matrix.elements[0],matrix.elements[1],matrix.elements[2]),
        journey:{origin:car.journey.origin,destination:car.journey.destination,step:car.journeyIndex,steps:car.journey.path.length,nextRoadId:car.next?.road.id??null}});
      if(samples.length>=cap)break;
    }
    return samples;
  }

  function statistics() { return { simulated: true, sourceRoads: roads.length, visibleRoads: candidates.length, cars: bicycles ? 0 : body.count, cyclists: bicycles ? body.count : 0, vehicles: body.count, maximumVehicles, drawCalls: body.count && group.visible ? (bicycles ? 5 : 3) : 0, paused, enabled, simulationSeconds: elapsed, plannedJourneys, completedJourneys, restrictionStatus, geometryStatus, surfaceProfileStatus, unroutableOrigins: unroutableOrigins.size, network: planner?.diagnostics() || null }; }

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
      if (paused || !group.visible || !roads.length) return false;
      elapsed += delta;
      // A temporarily occupied entry must not disable this fleet forever.
      // New journeys still enter through the view boundary after initial seeding.
      if (!cars.length) { populate(); render(); return desiredCount > 0; }
      const { occupants, junctionReservations } = coordinator.frame(timeSeconds, delta);
      cars = cars.filter(car => {
        car.age += delta;
        let endDistance = car.direction === 1 ? car.road.length - car.distance : car.distance;
        let targetSpeed = car.cruise;
        // Brake into the planned turn. Trip demand remains illustrative.
        if (car.next && car.next.weight < 5) targetSpeed = Math.min(targetSpeed, 3.5 + endDistance * .25);
        const gap=routeFollowingGap(car,occupants);
        if(Number.isFinite(gap))targetSpeed=Math.min(targetSpeed,Math.max(0,(gap-5.5)/1.4));
        const junction = car.direction === 1 ? car.road.end : car.road.start;
        if (junction && endDistance < 10 && !car.ending) {
          if (junctionReservations.get(junction)!==car) targetSpeed = Math.min(targetSpeed, Math.max(0, (endDistance - 3) * .6));
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
    statistics, sampleVehicles,
    dispose() {unregisterTraffic();group.removeFromParent();group.clear();for(const mesh of meshes)mesh.dispose();for(const item of Object.values(models))item.dispose();geometry.dispose();material.dispose();roofMaterial.dispose();detailMaterial.dispose();darkMaterial.dispose();roads=[];cars=[];planner=null;unroutableOrigins.clear();},
  };
}
