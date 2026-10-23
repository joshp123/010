#!/usr/bin/env node
// Written by AI, gpt-6-astra, 2026-10-24. Standard 3D Tiles for measured BGT yards.
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import * as THREE from '../dist/vendor/three/build/three.module.js';

const project = new URL('../', import.meta.url);
const input = new URL('work/source-quality/port/industrial-ground.geojson', project);
const output = new URL('dist/data/industrial-ground/', project);
const sourceBytes = await readFile(input), collection = JSON.parse(sourceBytes);
const origin = { lat: 51.915, lon: 4.49 }, radians = Math.PI / 180;
const bucketSizeMetres = 1000, polygonHeightMetres = -0.65, railHeightMetres = -0.62, railWidthMetres = 0.35;
function earthPosition(latitude, longitude, height) {
  const lat = latitude * radians, lon = longitude * radians;
  const radius = 6378137 / Math.sqrt(1 - 0.00669437999014 * Math.sin(lat) ** 2);
  return new THREE.Vector3((radius + height) * Math.cos(lat) * Math.cos(lon), (radius + height) * Math.cos(lat) * Math.sin(lon), (radius * (1 - 0.00669437999014) + height) * Math.sin(lat));
}
const originEarth = earthPosition(origin.lat, origin.lon, 0), lat = origin.lat * radians, lon = origin.lon * radians;
const east = new THREE.Vector3(-Math.sin(lon), Math.cos(lon), 0);
const up = new THREE.Vector3(Math.cos(lat) * Math.cos(lon), Math.cos(lat) * Math.sin(lon), Math.sin(lat));
const south = new THREE.Vector3(Math.sin(lat) * Math.cos(lon), Math.sin(lat) * Math.sin(lon), -Math.cos(lat));
const north = south.clone().negate();
const earthToLocal = new THREE.Matrix4().set(east.x, east.y, east.z, -east.dot(originEarth), up.x, up.y, up.z, -up.dot(originEarth), south.x, south.y, south.z, -south.dot(originEarth), 0, 0, 0, 1);
const enuToEarth = new THREE.Matrix4().set(east.x, north.x, up.x, originEarth.x, east.y, north.y, up.y, originEarth.y, east.z, north.z, up.z, originEarth.z, 0, 0, 0, 1);
const localPosition = ([longitude, latitude], height) => earthPosition(latitude, longitude, height).applyMatrix4(earthToLocal);

function featureGeometry(feature) {
  const vertices = [], indices = [];
  function add(point) { vertices.push(point.x, point.y, point.z); return vertices.length / 3 - 1; }
  function polygon(rings) {
    const contours = rings.map(ring => ring.slice(0, -1).map(point => localPosition(point, polygonHeightMetres)));
    const base = vertices.length / 3;
    contours.flat().forEach(add);
    const flat = contours.map(ring => ring.map(point => new THREE.Vector2(point.x, point.z)));
    for (const face of THREE.ShapeUtils.triangulateShape(flat[0], flat.slice(1))) indices.push(...face.map(index => base + index));
  }
  function rail(coordinates) {
    const points = coordinates.map(point => localPosition(point, railHeightMetres)), left = [], right = [];
    points.forEach((point, index) => {
      const direction = points[Math.min(index + 1, points.length - 1)].clone().sub(points[Math.max(0, index - 1)]);
      direction.y = 0; direction.normalize();
      const offset = new THREE.Vector3(-direction.z, 0, direction.x).multiplyScalar(railWidthMetres / 2);
      left.push(add(point.clone().add(offset))); right.push(add(point.clone().sub(offset)));
    });
    for (let index = 1; index < points.length; index++) indices.push(left[index - 1], right[index - 1], left[index], right[index - 1], right[index], left[index]);
  }
  const { type, coordinates } = feature.geometry;
  if (type === 'Polygon') polygon(coordinates);
  else if (type === 'MultiPolygon') coordinates.forEach(polygon);
  else if (type === 'LineString') rail(coordinates);
  else if (type === 'MultiLineString') coordinates.forEach(rail);
  return { vertices, indices };
}
const buckets = new Map(), counts = {};
for (const feature of collection.features) {
  const geometry = featureGeometry(feature);
  if (!geometry.indices.length) continue;
  const bounds = new THREE.Box3().setFromBufferAttribute(new THREE.BufferAttribute(new Float64Array(geometry.vertices), 3));
  const centre = bounds.getCenter(new THREE.Vector3()), key = `${Math.floor(centre.x / bucketSizeMetres)}_${Math.floor(centre.z / bucketSizeMetres)}`;
  if (!buckets.has(key)) buckets.set(key, { kinds: new Map(), bounds: new THREE.Box3(), features: 0 });
  const bucket = buckets.get(key), kind = feature.properties.kind;
  if (!bucket.kinds.has(kind)) bucket.kinds.set(kind, { vertices: [], indices: [] });
  const mesh = bucket.kinds.get(kind), base = mesh.vertices.length / 3;
  for (const value of geometry.vertices) mesh.vertices.push(value);
  for (const value of geometry.indices) mesh.indices.push(base + value);
  bucket.bounds.union(bounds); bucket.features++; counts[kind] = (counts[kind] || 0) + 1;
}
function enuBox(bounds) {
  const centre = bounds.getCenter(new THREE.Vector3()), half = bounds.getSize(new THREE.Vector3()).multiplyScalar(0.5);
  return [centre.x, -centre.z, centre.y, half.x, 0, 0, 0, half.z, 0, 0, 0, Math.max(0.01, half.y)];
}
function encodeTile(bucket) {
  const document = { asset: { version: '2.0', generator: '010 build-industrial-ground.mjs' }, scene: 0, scenes: [{ nodes: [] }], nodes: [], meshes: [], accessors: [], bufferViews: [], buffers: [{ byteLength: 0 }] };
  const chunks = []; let length = 0, triangles = 0;
  function accessor(array, type, target, bounds = {}) {
    const padding = (4 - length % 4) % 4;
    if (padding) { chunks.push(Buffer.alloc(padding)); length += padding; }
    const bytes = Buffer.from(array.buffer, array.byteOffset, array.byteLength), bufferView = document.bufferViews.length;
    document.bufferViews.push({ buffer: 0, byteOffset: length, byteLength: bytes.length, target });
    chunks.push(bytes); length += bytes.length;
    document.accessors.push({ bufferView, componentType: array instanceof Float32Array ? 5126 : array instanceof Uint32Array ? 5125 : 5123, count: array.length / (type === 'VEC3' ? 3 : 1), type, ...bounds });
    return document.accessors.length - 1;
  }
  for (const [kind, geometry] of bucket.kinds) {
    const centre = bucket.bounds.getCenter(new THREE.Vector3()), translation = centre.toArray();
    const positions = new Float32Array(geometry.vertices.map((value, index) => value - translation[index % 3]));
    const indices = geometry.indices;
    for (let index = 0; index < indices.length; index += 3) {
      const a = indices[index] * 3, b = indices[index + 1] * 3, c = indices[index + 2] * 3;
      const normalY = (positions[b + 2] - positions[a + 2]) * (positions[c] - positions[a]) - (positions[b] - positions[a]) * (positions[c + 2] - positions[a + 2]);
      if (normalY < 0) [indices[index + 1], indices[index + 2]] = [indices[index + 2], indices[index + 1]];
    }
    const bounds = new THREE.Box3().setFromBufferAttribute(new THREE.BufferAttribute(positions, 3));
    const positionAccessor = accessor(positions, 'VEC3', 34962, { min: bounds.min.toArray(), max: bounds.max.toArray() });
    const indexAccessor = accessor(positions.length / 3 > 65535 ? new Uint32Array(geometry.indices) : new Uint16Array(geometry.indices), 'SCALAR', 34963);
    const meshIndex = document.meshes.length;
    document.meshes.push({ name: kind, extras: { surfaceKind: kind }, primitives: [{ attributes: { POSITION: positionAccessor }, indices: indexAccessor, mode: 4 }] });
    document.nodes.push({ mesh: meshIndex, translation, extras: { surfaceKind: kind } });
    document.scenes[0].nodes.push(meshIndex); triangles += geometry.indices.length / 3;
  }
  document.buffers[0].byteLength = length;
  const json = Buffer.from(JSON.stringify(document)), jsonChunk = Buffer.concat([json, Buffer.alloc((4 - json.length % 4) % 4, 0x20)]), binaryChunk = Buffer.concat([...chunks, Buffer.alloc((4 - length % 4) % 4)]);
  const header = Buffer.alloc(12), jsonHeader = Buffer.alloc(8), binaryHeader = Buffer.alloc(8);
  header.write('glTF'); header.writeUInt32LE(2, 4); header.writeUInt32LE(28 + jsonChunk.length + binaryChunk.length, 8);
  jsonHeader.writeUInt32LE(jsonChunk.length); jsonHeader.writeUInt32LE(0x4e4f534a, 4);
  binaryHeader.writeUInt32LE(binaryChunk.length); binaryHeader.writeUInt32LE(0x004e4942, 4);
  return { bytes: Buffer.concat([header, jsonHeader, jsonChunk, binaryHeader, binaryChunk]), triangles };
}
await mkdir(output, { recursive: true });
const allBounds = new THREE.Box3(), children = [], tiles = [];
for (const [key, bucket] of [...buckets].sort(([a], [b]) => a.localeCompare(b))) {
  const filename = `${key}.glb`, encoded = encodeTile(bucket);
  await writeFile(new URL(filename, output), encoded.bytes);
  children.push({ boundingVolume: { box: enuBox(bucket.bounds) }, geometricError: 0, content: { uri: filename } });
  allBounds.union(bucket.bounds);
  tiles.push({ uri: filename, features: bucket.features, triangles: encoded.triangles, bytes: encoded.bytes.length });
}
const tileset = { asset: { version: '1.1', gltfUpAxis: 'Y' }, geometricError: 1e6, root: { transform: enuToEarth.toArray(), boundingVolume: { box: enuBox(allBounds) }, geometricError: 1e6, refine: 'REPLACE', children } };
await writeFile(new URL('tileset.json', output), JSON.stringify(tileset));
const manifest = { source: { ...Object.fromEntries(Object.entries(collection).filter(([key]) => key !== 'features')), derivedInputSha256: createHash('sha256').update(sourceBytes).digest('hex') }, origin, bucketSizeMetres, meshAxes: 'X east, Y up, Z south', tileAxes: 'X east, Y north, Z up', rootTransform: 'ENU to WGS84 ECEF', polygonHeightMetres, railHeightMetres, railWidthMetres, elevation: 'Display offsets, not surveyed elevation; rail ribbon width is illustrative.', surfaceCounts: counts, tiles };
await writeFile(new URL('manifest.json', output), JSON.stringify(manifest, null, 2) + '\n');
console.log(JSON.stringify({ tiles: tiles.length, triangles: tiles.reduce((sum, tile) => sum + tile.triangles, 0), bytes: tiles.reduce((sum, tile) => sum + tile.bytes, 0), surfaceCounts: counts }));
