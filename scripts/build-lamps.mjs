#!/usr/bin/env node
// Written by AI on 2026-10-24 by model GPT-6.
// Acquire the public source once, then reproduce compact lamp tiles from its cache.
import { readFile, writeFile, mkdir, stat } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { gunzipSync, gzipSync } from 'node:zlib';
import * as THREE from '../public/vendor/three/build/three.module.js';

const project = new URL('../', import.meta.url), output = new URL('public/data/lamps/', project), cache = new URL('work/data-cache/light-cost/', project);
const source = 'https://www.3drotterdam.nl/datasource-data/2602863a-3d22-44c2-8c95-bbf88a20bf37/tileset.json';
const origin = { latitude: 51.915, longitude: 4.49 }, radians = Math.PI / 180, bucketMetres = 1000;
const inventory = new Map(), requests = new Map();
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
await mkdir(cache, { recursive: true });
async function acquire(url) {
  if (requests.has(url)) return requests.get(url);
  const request = (async () => {
    const file = new URL(`${hash(url)}.bin`, cache); let bytes, info;
    try { bytes = await readFile(file); info = await stat(file); }
    catch (error) {
      if (error.code !== 'ENOENT') throw error;
      const response = await fetch(url, { signal: AbortSignal.timeout(60000) });
      if (!response.ok) throw Error(`${response.status} acquiring ${url}`);
      bytes = Buffer.from(await response.arrayBuffer()); await writeFile(file, bytes); info = await stat(file);
    }
    const decoded = bytes[0] === 31 && bytes[1] === 139 ? gunzipSync(bytes) : bytes;
    inventory.set(url, { url, sha256: hash(decoded), bytes: decoded.length, cachedBytes: bytes.length, acquiredAt: info.mtime.toISOString() });
    return decoded;
  })();
  requests.set(url, request); return request;
}
async function workers(items, action, concurrency = 6) {
  let next = 0; const errors = [];
  await Promise.all(Array.from({ length: concurrency }, async () => {
    while (next < items.length) { const item = items[next++]; try { await action(item); } catch (error) { errors.push({ item: item.url || item, error: error.message }); } }
  }));
  if (errors.length) { await writeFile(new URL('lamp-acquisition-errors.json', cache), JSON.stringify(errors, null, 2)); throw Error(`${errors.length} source acquisitions failed; see work/data-cache/light-cost/lamp-acquisition-errors.json`); }
}
const tileset = JSON.parse(await acquire(source));
if (tileset.asset.gltfUpAxis && tileset.asset.gltfUpAxis !== 'Y') throw Error('Unexpected source glTF up axis');
const sourceTiles = [];
function visit(tile, ancestor = new THREE.Matrix4()) {
  const transform = ancestor.clone(); if (tile.transform) transform.multiply(new THREE.Matrix4().fromArray(tile.transform));
  if (tile.content) sourceTiles.push({ url: new URL(tile.content.uri || tile.content.url, source).href, transform });
  for (const child of tile.children || []) visit(child, transform);
}
visit(tileset.root);
console.log(`Acquiring ${sourceTiles.length} public lamp tiles…`);
await workers(sourceTiles, async tile => { tile.bytes = await acquire(tile.url); });
function* components(bytes) {
  const type = bytes.toString('ascii', 0, 4);
  if (type === 'cmpt') {
    let offset = 16;
    for (let index = 0; index < bytes.readUInt32LE(12); index++) { const length = bytes.readUInt32LE(offset + 8); yield* components(bytes.subarray(offset, offset + length)); offset += length; }
  } else if (type === 'i3dm') yield bytes;
  else throw Error(`Unsupported source tile ${type}`);
}
const parts = [], prototypeUrls = new Set();
for (const tile of sourceTiles) for (const bytes of components(tile.bytes)) {
  const featureJsonLength = bytes.readUInt32LE(12), featureBinaryLength = bytes.readUInt32LE(16), batchJsonLength = bytes.readUInt32LE(20), batchBinaryLength = bytes.readUInt32LE(24);
  const feature = JSON.parse(bytes.subarray(32, 32 + featureJsonLength)), featureBinary = bytes.subarray(32 + featureJsonLength, 32 + featureJsonLength + featureBinaryLength);
  const batchStart = 32 + featureJsonLength + featureBinaryLength, batch = JSON.parse(bytes.subarray(batchStart, batchStart + batchJsonLength));
  if (bytes.readUInt32LE(28) !== 0) throw Error('Expected source external GLB prototype');
  const url = new URL(bytes.subarray(batchStart + batchJsonLength + batchBinaryLength).toString().replace(/[\0\s]+$/, ''), tile.url).href;
  parts.push({ tile, feature, featureBinary, batch, url }); prototypeUrls.add(url);
}
console.log(`Acquiring ${prototypeUrls.size} shared lamp prototypes…`);
await workers([...prototypeUrls], acquire);
function nodeMatrix(node) {
  return node.matrix ? new THREE.Matrix4().fromArray(node.matrix) : new THREE.Matrix4().compose(new THREE.Vector3().fromArray(node.translation || [0, 0, 0]), new THREE.Quaternion().fromArray(node.rotation || [0, 0, 0, 1]), new THREE.Vector3().fromArray(node.scale || [1, 1, 1]));
}
const prototypes = new Map();
for (const url of prototypeUrls) {
  const bytes = await acquire(url), jsonLength = bytes.readUInt32LE(12), document = JSON.parse(bytes.subarray(20, 20 + jsonLength)), binary = bytes.subarray(28 + jsonLength), vertices = [];
  function walkNode(index, parent = new THREE.Matrix4()) {
    const node = document.nodes[index], matrix = parent.clone().multiply(nodeMatrix(node));
    if (node.mesh !== undefined) for (const primitive of document.meshes[node.mesh].primitives) {
      const accessor = document.accessors[primitive.attributes.POSITION], view = document.bufferViews[accessor.bufferView];
      if (accessor.componentType !== 5126 || accessor.type !== 'VEC3' || accessor.sparse) throw Error(`Unexpected prototype POSITION: ${url}`);
      for (let vertex = 0; vertex < accessor.count; vertex++) {
        const offset = (view.byteOffset || 0) + (accessor.byteOffset || 0) + vertex * (view.byteStride || 12);
        vertices.push(new THREE.Vector3(binary.readFloatLE(offset), binary.readFloatLE(offset + 4), binary.readFloatLE(offset + 8)).applyMatrix4(matrix));
      }
    }
    for (const child of node.children || []) walkNode(child, matrix);
  }
  for (const node of document.scenes[document.scene || 0].nodes) walkNode(node);
  prototypes.set(url, vertices);
}
const latitude = origin.latitude * radians, longitude = origin.longitude * radians;
const eccentricitySquared = 0.00669437999014, radius = 6378137 / Math.sqrt(1 - eccentricitySquared * Math.sin(latitude) ** 2);
const earthOrigin = new THREE.Vector3(radius * Math.cos(latitude) * Math.cos(longitude), radius * Math.cos(latitude) * Math.sin(longitude), radius * (1 - eccentricitySquared) * Math.sin(latitude));
const east = new THREE.Vector3(-Math.sin(longitude), Math.cos(longitude), 0), up = new THREE.Vector3(Math.cos(latitude) * Math.cos(longitude), Math.cos(latitude) * Math.sin(longitude), Math.sin(latitude));
const north = new THREE.Vector3(-Math.sin(latitude) * Math.cos(longitude), -Math.sin(latitude) * Math.sin(longitude), Math.cos(latitude));
const earthToLocal = new THREE.Matrix4().set(east.x, east.y, east.z, -east.dot(earthOrigin), up.x, up.y, up.z, -up.dot(earthOrigin), -north.x, -north.y, -north.z, north.dot(earthOrigin), 0, 0, 0, 1);
const enuToEarth = new THREE.Matrix4().set(east.x, north.x, up.x, earthOrigin.x, east.y, north.y, up.y, earthOrigin.y, east.z, north.z, up.z, earthOrigin.z, 0, 0, 0, 1);
const municipalityBytes = await readFile(new URL('public/data/municipality.json', project)), municipality = JSON.parse(municipalityBytes).features.find(feature => feature.properties.identificatie === 'GM0599');
if (!municipality) throw Error('Missing GM0599 municipality');
const polygons = municipality.geometry.type === 'MultiPolygon' ? municipality.geometry.coordinates : [municipality.geometry.coordinates];
function inRing(x, y, ring) {
  let inside = false;
  for (let a = 0, b = ring.length - 1; a < ring.length; b = a++) {
    const [ax, ay] = ring[a], [bx, by] = ring[b];
    if ((ay > y) !== (by > y) && x < (bx - ax) * (y - ay) / (by - ay) + ax) inside = !inside;
  }
  return inside;
}
function municipalityContains(earth) {
  const lon = Math.atan2(earth.y, earth.x), horizontal = Math.hypot(earth.x, earth.y);
  let lat = Math.atan2(earth.z, horizontal * (1 - eccentricitySquared));
  for (let iteration = 0; iteration < 5; iteration++) { const r = 6378137 / Math.sqrt(1 - eccentricitySquared * Math.sin(lat) ** 2); lat = Math.atan2(earth.z + eccentricitySquared * r * Math.sin(lat), horizontal); }
  const x = lon / radians, y = lat / radians;
  return polygons.some(rings => inRing(x, y, rings[0]) && !rings.slice(1).some(ring => inRing(x, y, ring)));
}
// The overview is simplified for display. Pool eligibility uses the retained
// original survey polygons, including small water bodies and polygon holes.
const poolRadiusMetres = 9, poolClearanceMetres = poolRadiusMetres + 0.1, surveyInventory = [], surveyFeatures = [];
const geographicPoints = polygons.flat(2), bounds = [Math.min(...geographicPoints.map(p => p[0])), Math.min(...geographicPoints.map(p => p[1])), Math.max(...geographicPoints.map(p => p[0])), Math.max(...geographicPoints.map(p => p[1]))];
let waterUrl = `https://api.pdok.nl/kadaster/brt-top10nl/ogc/v1/collections/waterdeel_vlak/items?${new URLSearchParams({ bbox: bounds.join(','), limit: '1000', f: 'json' })}`;
while (waterUrl) {
  const file = new URL(`work/data-cache/${hash(waterUrl)}.json`, project); let bytes;
  try { bytes = await readFile(file); }
  catch (error) { if (error.code !== 'ENOENT') throw error; const response = await fetch(waterUrl); if (!response.ok) throw Error(`Survey water acquisition failed: ${response.status}`); bytes = Buffer.from(await response.arrayBuffer()); await writeFile(file, bytes); }
  const page = JSON.parse(bytes);
  surveyInventory.push({ url: waterUrl, sha256: hash(bytes), bytes: bytes.length, acquiredAt: (await stat(file)).mtime.toISOString() });
  surveyFeatures.push(...page.features);
  waterUrl = page.links?.find(link => link.rel === 'next')?.href;
}
function surveyLocal([longitude, latitude]) {
  const lat = latitude * radians, lon = longitude * radians, radius = 6378137 / Math.sqrt(1 - eccentricitySquared * Math.sin(lat) ** 2);
  const point = new THREE.Vector3(radius * Math.cos(lat) * Math.cos(lon), radius * Math.cos(lat) * Math.sin(lon), radius * (1 - eccentricitySquared) * Math.sin(lat)).applyMatrix4(earthToLocal);
  return [point.x, point.z];
}
const shorelineCells = new Map(), waterCells = new Map(), poolCellMetres = 200;
function indexBounds(index, bounds, item) {
  for (let x = Math.floor(bounds[0] / poolCellMetres); x <= Math.floor(bounds[2] / poolCellMetres); x++) for (let z = Math.floor(bounds[1] / poolCellMetres); z <= Math.floor(bounds[3] / poolCellMetres); z++) {
    const key = `${x},${z}`; if (!index.has(key)) index.set(key, []); index.get(key).push(item);
  }
}
function indexRing(ring) {
  for (let i = 1; i < ring.length; i++) {
    const a = ring[i - 1], b = ring[i];
    indexBounds(shorelineCells, [Math.min(a[0], b[0]) - poolClearanceMetres, Math.min(a[1], b[1]) - poolClearanceMetres, Math.max(a[0], b[0]) + poolClearanceMetres, Math.max(a[1], b[1]) + poolClearanceMetres], [a, b]);
  }
}
for (const polygon of polygons) for (const ring of polygon) indexRing(ring.map(surveyLocal));
for (const feature of surveyFeatures) {
  const geometry = feature.geometry;
  if (!geometry || !['Polygon', 'MultiPolygon'].includes(geometry.type)) throw Error('Unexpected survey water geometry');
  for (const polygon of geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates) {
    const rings = polygon.map(ring => ring.map(surveyLocal)), points = rings[0];
    indexBounds(waterCells, [Math.min(...points.map(p => p[0])), Math.min(...points.map(p => p[1])), Math.max(...points.map(p => p[0])), Math.max(...points.map(p => p[1]))], rings);
    rings.forEach(indexRing);
  }
}
const poolCounts = { eligible: 0, onWater: 0, nearShoreOrMunicipalEdge: 0 };
function poolEligibility(base) {
  const x = base.x, z = base.z, key = `${Math.floor(x / poolCellMetres)},${Math.floor(z / poolCellMetres)}`;
  if ((waterCells.get(key) || []).some(rings => inRing(x, z, rings[0]) && !rings.slice(1).some(ring => inRing(x, z, ring)))) { poolCounts.onWater++; return false; }
  for (const [a, b] of shorelineCells.get(key) || []) {
    const dx = b[0] - a[0], dz = b[1] - a[1], lengthSquared = dx * dx + dz * dz;
    const t = lengthSquared ? Math.max(0, Math.min(1, ((x - a[0]) * dx + (z - a[1]) * dz) / lengthSquared)) : 0;
    if (Math.hypot(x - a[0] - t * dx, z - a[1] - t * dz) <= poolClearanceMetres) { poolCounts.nearShoreOrMunicipalEdge++; return false; }
  }
  poolCounts.eligible++; return true;
}
console.log(`Classifying pools against ${surveyFeatures.length} unsimplified survey water features…`);

function property(feature, binary, name, count, fallback) {
  const value = feature[name]; if (!value) return fallback;
  if (Array.isArray(value)) return value;
  const offset = value.byteOffset;
  const reader = value.componentType === 'UNSIGNED_BYTE' ? 'readUInt8' : value.componentType === 'UNSIGNED_INT' ? 'readUInt32LE' : name === 'POSITION_QUANTIZED' || name === 'BATCH_ID' ? 'readUInt16LE' : 'readFloatLE';
  const width = reader === 'readUInt8' ? 1 : reader === 'readUInt16LE' ? 2 : 4;
  return Array.from({ length: count }, (_, index) => binary[reader](offset + index * width));
}
const buckets = new Map(), seen = new Set(), counts = { sourceInstances: 0, included: 0, outsideMunicipality: 0, duplicateRecords: 0 }, adjustment = new THREE.Matrix4().makeRotationX(Math.PI / 2);
const right = new THREE.Vector3(), normalUp = new THREE.Vector3(), forward = new THREE.Vector3(), position = new THREE.Vector3(), scale = new THREE.Vector3(), orientation = new THREE.Matrix4(), matrix = new THREE.Matrix4(), vertex = new THREE.Vector3(), top = new THREE.Vector3();
for (const part of parts) {
  const { feature, featureBinary: binary, batch, tile } = part, count = feature.INSTANCES_LENGTH;
  const positions = property(feature, binary, 'POSITION', count * 3), quantized = property(feature, binary, 'POSITION_QUANTIZED', count * 3);
  const rights = property(feature, binary, 'NORMAL_RIGHT', count * 3), ups = property(feature, binary, 'NORMAL_UP', count * 3), scales = property(feature, binary, 'SCALE_NON_UNIFORM', count * 3), scalarScales = property(feature, binary, 'SCALE', count), batchIds = property(feature, binary, 'BATCH_ID', count);
  if ((!positions && !quantized) || !rights || !ups || feature.EAST_NORTH_UP) throw Error(`Unrecognised source instance orientation in ${tile.url}`);
  const rtc = new THREE.Vector3().fromArray(feature.RTC_CENTER || [0, 0, 0]);
  for (let instance = 0; instance < count; instance++) {
    counts.sourceInstances++;
    if (positions) position.fromArray(positions, instance * 3);
    else position.set(...[0, 1, 2].map(axis => feature.QUANTIZED_VOLUME_OFFSET[axis] + quantized[instance * 3 + axis] / 65535 * feature.QUANTIZED_VOLUME_SCALE[axis]));
    position.add(rtc);
    const anchor = position.clone().applyMatrix4(tile.transform);
    if (!municipalityContains(anchor)) { counts.outsideMunicipality++; continue; }
    const batchId = batchIds ? batchIds[instance] : instance, id = String(batch.id[batchId]);
    right.fromArray(rights, instance * 3); normalUp.fromArray(ups, instance * 3); forward.crossVectors(right, normalUp).normalize(); orientation.makeBasis(right, normalUp, forward);
    scale.fromArray(scales || [1, 1, 1], scales ? instance * 3 : 0).multiplyScalar(scalarScales ? scalarScales[instance] : 1);
    matrix.copy(tile.transform).multiply(new THREE.Matrix4().compose(position, new THREE.Quaternion().setFromRotationMatrix(orientation), scale)).multiply(adjustment);
    let highest = -Infinity;
    for (const point of prototypes.get(part.url)) { vertex.copy(point).applyMatrix4(matrix); const elevation = vertex.dot(up); if (elevation > highest) { highest = elevation; top.copy(vertex); } }
    const key = `${id}:${anchor.toArray().join(',')}:${top.toArray().join(',')}`;
    if (seen.has(key)) { counts.duplicateRecords++; continue; } seen.add(key);
    const baseLocal = anchor.applyMatrix4(earthToLocal), topLocal = top.clone().applyMatrix4(earthToLocal);
    if (![...baseLocal.toArray(), ...topLocal.toArray()].every(Number.isFinite)) throw Error(`Invalid coordinates for ${id}`);
    const bucketKey = `${Math.floor(baseLocal.x / bucketMetres)}_${Math.floor(baseLocal.z / bucketMetres)}`;
    if (!buckets.has(bucketKey)) buckets.set(bucketKey, { records: [], bounds: new THREE.Box3() });
    const bucket = buckets.get(bucketKey); bucket.records.push({ id, base: baseLocal.toArray(), top: topLocal.toArray(), poolEligible: poolEligibility(baseLocal) }); bucket.bounds.expandByPoint(baseLocal).expandByPoint(topLocal); counts.included++;
  }
}
function enuBox(bounds) {
  const c = bounds.getCenter(new THREE.Vector3()), h = bounds.getSize(new THREE.Vector3()).multiplyScalar(0.5);
  return [c.x, -c.z, c.y, Math.max(h.x, 0.01), 0, 0, 0, Math.max(h.z, 0.01), 0, 0, 0, Math.max(h.y, 0.01)];
}
function encode(bucket) {
  const minimum = bucket.bounds.min.toArray(), extent = bucket.bounds.getSize(new THREE.Vector3()).toArray(), steps = extent.map(value => value / 65535);
  if (steps.some(step => step / 2 > 0.02)) throw Error('A lamp bucket exceeds the 2 cm position error budget');
  const count = bucket.records.length, encodedPositions = Buffer.alloc(count * 16), IndexArray = count * 2 > 65535 ? Uint32Array : Uint16Array;
  const shaftIndices = new IndexArray(count * 2), headIndices = new IndexArray(count), poolIndices = new IndexArray(bucket.records.filter(record => record.poolEligible).length);
  let poolIndex = 0;
  let maximumPositionError = 0;
  bucket.records.forEach((record, index) => {
    for (const [endpoint, point] of [record.base, record.top].entries()) {
      const decoded = [];
      point.forEach((value, axis) => {
        const quantized = steps[axis] ? Math.round((value - minimum[axis]) / steps[axis]) : 0;
        encodedPositions.writeUInt16LE(quantized, index * 16 + endpoint * 8 + axis * 2); decoded.push(minimum[axis] + quantized * steps[axis]);
      });
      maximumPositionError = Math.max(maximumPositionError, Math.hypot(...point.map((value, axis) => value - decoded[axis])));
    }
    shaftIndices[index * 2] = index * 2; shaftIndices[index * 2 + 1] = index * 2 + 1; headIndices[index] = index * 2 + 1;
    if (record.poolEligible) poolIndices[poolIndex++] = index * 2;
  });
  const shaftBytes = Buffer.from(shaftIndices.buffer), headBytes = Buffer.from(headIndices.buffer), poolBytes = Buffer.from(poolIndices.buffer), headOffset = encodedPositions.length + shaftBytes.length, poolPadding = Buffer.alloc((4 - (headOffset + headBytes.length) % 4) % 4), poolOffset = headOffset + headBytes.length + poolPadding.length;
  const document = {
    asset: { version: '2.0', generator: '010 build-lamps.mjs' }, extensionsUsed: ['KHR_mesh_quantization'], extensionsRequired: ['KHR_mesh_quantization'],
    scene: 0, scenes: [{ nodes: [0, 1] }],
    nodes: [0, 1].map(mesh => ({ mesh, translation: minimum, scale: steps.map(step => step || 1) })),
    meshes: [
      { name: 'lampShafts', extras: { objectKind: 'lampShafts', placement: 'source instance origin to highest prototype vertex; straight connector is illustrative' }, primitives: [{ attributes: { POSITION: 0 }, indices: 1, mode: 1 }] },
      { name: 'lampHeads', extras: { objectKind: 'lampHeads', sourceIds: bucket.records.map(record => record.id), sourceRecordIndex: 'floor(POSITION vertex index / 2)', placement: 'highest source prototype vertex along the Rotterdam local vertical; glow anchor, not a surveyed emitter' }, primitives: [{ attributes: { POSITION: 0 }, indices: 2, mode: 0 }] },
    ],
    accessors: [
      { bufferView: 0, componentType: 5123, type: 'VEC3', count: count * 2, min: [0, 0, 0], max: steps.map(step => step ? 65535 : 0) },
      { bufferView: 1, componentType: IndexArray === Uint32Array ? 5125 : 5123, type: 'SCALAR', count: count * 2 },
      { bufferView: 2, componentType: IndexArray === Uint32Array ? 5125 : 5123, type: 'SCALAR', count },
    ],
    bufferViews: [
      { buffer: 0, byteOffset: 0, byteLength: encodedPositions.length, byteStride: 8, target: 34962 },
      { buffer: 0, byteOffset: encodedPositions.length, byteLength: shaftBytes.length, target: 34963 },
      { buffer: 0, byteOffset: headOffset, byteLength: headBytes.length, target: 34963 },
    ], buffers: [{ byteLength: poolOffset + poolBytes.length }],
  };
  if (poolIndices.length) {
    document.scenes[0].nodes.push(2);
    document.nodes.push({ mesh: 2, translation: minimum, scale: steps.map(step => step || 1) });
    document.meshes.push({ name: 'lampPools', extras: { objectKind: 'lampPools', maximumRadiusMetres: poolRadiusMetres, placement: 'unchanged source bases with full pool footprint outside unsimplified surveyed water and inside the municipality' }, primitives: [{ attributes: { POSITION: 0 }, indices: 3, mode: 0 }] });
    document.accessors.push({ bufferView: 3, componentType: IndexArray === Uint32Array ? 5125 : 5123, type: 'SCALAR', count: poolIndices.length });
    document.bufferViews.push({ buffer: 0, byteOffset: poolOffset, byteLength: poolBytes.length, target: 34963 });
  }
  const json = Buffer.from(JSON.stringify(document)), jsonChunk = Buffer.concat([json, Buffer.alloc((4 - json.length % 4) % 4, 32)]), binary = Buffer.concat([encodedPositions, shaftBytes, headBytes, poolPadding, poolBytes, Buffer.alloc((4 - document.buffers[0].byteLength % 4) % 4)]);
  const header = Buffer.alloc(28); header.write('glTF'); header.writeUInt32LE(2, 4); header.writeUInt32LE(28 + jsonChunk.length + binary.length, 8); header.writeUInt32LE(jsonChunk.length, 12); header.writeUInt32LE(0x4e4f534a, 16); header.writeUInt32LE(binary.length, 20); header.writeUInt32LE(0x004e4942, 24);
  const glb = Buffer.concat([header.subarray(0, 20), jsonChunk, header.subarray(20), binary]);
  return { glb, maximumPositionError };
}
await mkdir(output, { recursive: true });
const children = [], tiles = [], worldBounds = new THREE.Box3(); let rawBytes = 0, gzipBytes = 0, maximumPositionError = 0;
for (const [key, bucket] of [...buckets.entries()].sort(([a], [b]) => a.localeCompare(b))) {
  const { glb, maximumPositionError: error } = encode(bucket), uri = `${key}.glb`, compressedBytes = gzipSync(glb).length;
  await writeFile(new URL(uri, output), glb); worldBounds.union(bucket.bounds); rawBytes += glb.length; gzipBytes += compressedBytes; maximumPositionError = Math.max(maximumPositionError, error);
  children.push({ boundingVolume: { box: enuBox(bucket.bounds) }, geometricError: 0, content: { uri } });
  tiles.push({ uri, records: bucket.records.length, pools: bucket.records.filter(record => record.poolEligible).length, bytes: glb.length, gzipBytes: compressedBytes, maximumPositionErrorMetres: error });
}
const generated = { asset: { version: '1.0', gltfUpAxis: 'Y' }, geometricError: 1000000, root: { boundingVolume: { box: enuBox(worldBounds) }, geometricError: 1000000, refine: 'REPLACE', transform: enuToEarth.toArray(), children } };
await writeFile(new URL('tileset.json', output), JSON.stringify(generated));
const manifest = {
  writtenBy: 'AI, GPT-6, 2026-10-24', generatedAt: new Date().toISOString(), source, sourceAsset: tileset.asset,
  publisher: 'Gemeente Rotterdam', license: 'Public domain, Rotterdam 3D catalogue', sourcePage: 'https://www.rotterdam.nl/rotterdam-in-3d', licensePage: 'https://data.overheid.nl/dataset/10230-rotterdam-3d',
  municipality: { identifier: 'GM0599', file: '../municipality.json', sha256: hash(municipalityBytes), test: 'source instance origin lies within municipality polygon including holes' },
  acquisition: { complete: true, tiles: sourceTiles.length, prototypes: prototypeUrls.size, decodedBytes: [...inventory.values()].reduce((sum, record) => sum + record.bytes, 0), cache: 'work/data-cache/light-cost/', inventory: [...inventory.values()].sort((a, b) => a.url.localeCompare(b.url)) },
  counts, pools: { ...poolCounts, maximumRadiusMetres: poolRadiusMetres, clearanceMetres: poolClearanceMetres, surveyFeatures: surveyFeatures.length, source: 'Kadaster / PDOK BRT TOP10NL waterdeel_vlak; CC BY 4.0', license: 'https://creativecommons.org/licenses/by/4.0/', surveyInventory, method: 'No geometry simplification or minimum water-body area. Municipal land is the exact municipality minus surveyed water. Exclude centres in water and any base within the 9.1 m clearance of a water or municipal boundary. Pool indices reference unchanged source bases. The extra 0.1 m covers local projection and output quantization rounding.' }, output: { tiles: tiles.length, bytes: rawBytes, gzipBytes, maximumPositionErrorMetres: maximumPositionError },
  coordinates: { source: 'I3DM ECEF placement/orientation/scale and glTF prototype vertices; all tile/node transforms retained', output: 'glTF X east, Y up, Z south; tileset bounding boxes in Z-up ENU', origin, bucketMetres, quantization: 'unsigned 16-bit KHR_mesh_quantization; <=2 cm per axis; actual Euclidean error reported per tile' },
  interpretation: { lampHeads: 'Exact highest transformed prototype vertex along the fixed local vertical, matching the existing native glow anchor. This is a display anchor, not a surveyed light emitter.', lampShafts: 'Illustrative straight connection from source instance origin to the retained head vertex. Does not replace the native curved pole geometry at close range.', identifiers: 'Head mesh extras.sourceIds follow source record order; indexed POSITION vertex 2i is base and 2i+1 is head.', sourceDates: 'Original record dates and attributes remain in cached I3DM batch tables; acquisition date is not an assertion of live/current hardware.', gaps: `Complete acquisition of all ${sourceTiles.length} advertised source content tiles, not a claim that every real lamp is present. The source has no leaf coverage at the sampled Maasvlakte point (4.0 E, 51.94 N). No missing placements are invented.`, precision: 'Original quantized ECEF coordinates are decoded in double precision before local quantization. The native browser I3DM loader first converts ECEF to Float32, introducing roughly decimetre placement rounding that is not reproduced here.', duplicates: 'Remove only records with identical source identifier, instance origin and transformed top vertex.' },
  tiles,
};
await writeFile(new URL('manifest.json', output), JSON.stringify(manifest, null, 2) + '\n');
console.log(JSON.stringify({ counts, pools: poolCounts, tiles: tiles.length, rawBytes, gzipBytes, maximumPositionErrorMetres: maximumPositionError, sourceBytes: manifest.acquisition.decodedBytes }, null, 2));
