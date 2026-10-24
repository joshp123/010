#!/usr/bin/env node
// Written by AI on 2026-10-24 by model GPT-6.
// node scripts/build-streets.mjs [input.geojson]
// Standard 3D Tiles + glTF; geometry/provenance remain independent of styling.
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { gzipSync, gunzipSync } from 'node:zlib';
import * as THREE from '../public/vendor/three/build/three.module.js';

const project = new URL('../', import.meta.url);
const input = process.argv[2] ? new URL(process.argv[2], project) : new URL('source-data/transport-network.geojson.gz', project);
const output = new URL('public/data/streets/', project);
const inputBytes = await readFile(input), sourceBytes = input.pathname.endsWith('.gz') ? gunzipSync(inputBytes) : inputBytes, collection = JSON.parse(sourceBytes);
const origin = { lat: 51.915, lon: 4.49 }, degrees = Math.PI / 180, eccentricitySquared = 0.00669437999014;
const bucketSizeMetres = 1000, maximumQuantizationErrorMetres = 0.02;
function earthPosition(lat, lon, height = 0) {
  const latitude = lat * degrees, longitude = lon * degrees;
  const radius = 6378137 / Math.sqrt(1 - eccentricitySquared * Math.sin(latitude) ** 2);
  return new THREE.Vector3((radius + height) * Math.cos(latitude) * Math.cos(longitude), (radius + height) * Math.cos(latitude) * Math.sin(longitude), (radius * (1 - eccentricitySquared) + height) * Math.sin(latitude));
}
const originEarth = earthPosition(origin.lat, origin.lon), lat = origin.lat * degrees, lon = origin.lon * degrees;
const east = new THREE.Vector3(-Math.sin(lon), Math.cos(lon), 0);
const up = new THREE.Vector3(Math.cos(lat) * Math.cos(lon), Math.cos(lat) * Math.sin(lon), Math.sin(lat));
const south = new THREE.Vector3(Math.sin(lat) * Math.cos(lon), Math.sin(lat) * Math.sin(lon), -Math.cos(lat));
const north = south.clone().negate();
const earthToLocal = new THREE.Matrix4().set(east.x, east.y, east.z, -east.dot(originEarth), up.x, up.y, up.z, -up.dot(originEarth), south.x, south.y, south.z, -south.dot(originEarth), 0, 0, 0, 1);
const enuToEarth = new THREE.Matrix4().set(east.x, north.x, up.x, originEarth.x, east.y, north.y, up.y, originEarth.y, east.z, north.z, up.z, originEarth.z, 0, 0, 0, 1);
const localPosition = (lat, lon, height) => earthPosition(lat, lon, height).applyMatrix4(earthToLocal);
function surfaceKind(properties) {
  if (properties.kind === 'rail') return 'rail';
  const purpose = properties.hoofdverkeersgebruik || '';
  return purpose.includes('fiets') ? 'cycleway' : purpose.includes('voetganger') ? 'footway' : 'road';
}
function featureGeometry(feature) {
  const vertices = [], indices = [];
  function addVertex(point) { vertices.push(Math.fround(point.x), Math.fround(point.y), Math.fround(point.z)); return vertices.length / 3 - 1; }
  function polygon(rings) {
    const contours = rings.map(ring => ring.slice(0, -1).map(([lon, lat]) => localPosition(lat, lon, -0.55)));
    if (!contours[0]?.length) return;
    const points = contours.flat(), base = vertices.length / 3;
    points.forEach(addVertex);
    const faces = THREE.ShapeUtils.triangulateShape(contours[0].map(p => new THREE.Vector2(p.x, p.z)), contours.slice(1).map(ring => ring.map(p => new THREE.Vector2(p.x, p.z))));
    for (const face of faces) indices.push(...face.map(index => base + index));
  }
  function ribbon(coordinates, width) {
    const points = coordinates.map(([lon, lat]) => localPosition(lat, lon, -0.45)), left = [], right = [];
    for (let index = 0; index < points.length; index++) {
      const previous = points[Math.max(0, index - 1)], next = points[Math.min(points.length - 1, index + 1)];
      const direction = next.clone().sub(previous); direction.y = 0; direction.normalize();
      const offset = new THREE.Vector3(-direction.z, 0, direction.x).multiplyScalar(width / 2);
      left.push(addVertex(points[index].clone().add(offset))); right.push(addVertex(points[index].clone().sub(offset)));
    }
    for (let index = 1; index < points.length; index++) indices.push(left[index - 1], right[index - 1], left[index], right[index - 1], right[index], left[index]);
  }
  const { type, coordinates } = feature.geometry, properties = feature.properties;
  if (type === 'Polygon') polygon(coordinates);
  else if (type === 'MultiPolygon') coordinates.forEach(polygon);
  else {
    const widthClass = properties.verhardingsbreedteklasse || '';
    const width = properties.kind === 'rail' ? (properties.aantalsporen === 'dubbel' ? 6 : 3.2) : widthClass.includes('4 - 7') ? 5.5 : widthClass.includes('2 - 4') ? 3 : 1.6;
    for (const line of type === 'MultiLineString' ? coordinates : [coordinates]) ribbon(line, width);
  }
  return { vertices, indices };
}
const buckets = new Map(), counts = {}, excluded = { structure: 0, belowGround: 0, ferry: 0, notInUse: 0 };
for (const feature of collection.features) {
  const p = feature.properties;
  if (/brug|tunnel|overkluisd/.test(p.fysiekvoorkomen || '')) { excluded.structure++; continue; }
  if (p.hoogteniveau < 0) { excluded.belowGround++; continue; }
  if (p.typeweg === 'veerverbinding') { excluded.ferry++; continue; }
  if (p.status !== 'in gebruik') { excluded.notInUse++; continue; }
  const geometry = featureGeometry(feature);
  if (!geometry.indices.length) continue;
  const bounds = new THREE.Box3().setFromBufferAttribute(new THREE.Float32BufferAttribute(geometry.vertices, 3));
  const centre = bounds.getCenter(new THREE.Vector3()), key = `${Math.floor(centre.x / bucketSizeMetres)}_${Math.floor(centre.z / bucketSizeMetres)}`;
  if (!buckets.has(key)) buckets.set(key, { kinds: new Map(), bounds: new THREE.Box3(), features: 0 });
  const bucket = buckets.get(key), kind = surfaceKind(p);
  if (!bucket.kinds.has(kind)) bucket.kinds.set(kind, { vertices: [], indices: [] });
  const mesh = bucket.kinds.get(kind), base = mesh.vertices.length / 3;
  for (const value of geometry.vertices) mesh.vertices.push(value);
  for (const index of geometry.indices) mesh.indices.push(base + index);
  bucket.bounds.union(bounds); bucket.features++; counts[kind] = (counts[kind] || 0) + 1;
}
function enuBox(bounds) {
  const c = bounds.getCenter(new THREE.Vector3()), h = bounds.getSize(new THREE.Vector3()).multiplyScalar(0.5);
  return [c.x, -c.z, c.y, h.x, 0, 0, 0, h.z, 0, 0, 0, Math.max(0.01, h.y)];
}
function encodeTile(bucket) {
  const document = { asset: { version: '2.0', generator: '010 build-streets.mjs' }, scene: 0, scenes: [{ nodes: [] }], nodes: [], meshes: [], accessors: [], bufferViews: [], buffers: [{ byteLength: 0 }] };
  const chunks = []; let length = 0, quantizedMeshes = 0, exactMeshes = 0, triangles = 0;
  function accessor(array, type, target, bounds) {
    const padding = (4 - length % 4) % 4;
    if (padding) { chunks.push(Buffer.alloc(padding)); length += padding; }
    let bytes = Buffer.from(array.buffer, array.byteOffset, array.byteLength);
    const stride = array instanceof Uint16Array && type === 'VEC3' ? 8 : undefined;
    if (stride) { bytes = Buffer.alloc(array.length / 3 * stride); for (let i = 0; i < array.length; i++) bytes.writeUInt16LE(array[i], Math.floor(i / 3) * stride + i % 3 * 2); }
    const bufferView = document.bufferViews.length;
    document.bufferViews.push({ buffer: 0, byteOffset: length, byteLength: bytes.length, target, ...(stride ? { byteStride: stride } : {}) });
    chunks.push(bytes); length += bytes.length;
    document.accessors.push({ bufferView, componentType: array instanceof Float32Array ? 5126 : array instanceof Uint32Array ? 5125 : 5123, count: array.length / (type === 'VEC3' ? 3 : 1), type, ...bounds });
    return document.accessors.length - 1;
  }
  for (const [kind, geometry] of bucket.kinds) {
    const bounds = new THREE.Box3().setFromBufferAttribute(new THREE.Float32BufferAttribute(geometry.vertices, 3));
    const minimum = bounds.min.toArray(), maximum = bounds.max.toArray(), steps = maximum.map((value, axis) => (value - minimum[axis]) / 65535);
    const quantize = steps.every(step => step / 2 <= maximumQuantizationErrorMetres);
    const unique = new Map(), positions = [], indices = [];
    for (const sourceIndex of geometry.indices) {
      const point = geometry.vertices.slice(sourceIndex * 3, sourceIndex * 3 + 3);
      const encoded = quantize ? point.map((value, axis) => steps[axis] ? Math.round((value - minimum[axis]) / steps[axis]) : 0) : point;
      const key = encoded.join(','); let index = unique.get(key);
      if (index === undefined) { index = unique.size; unique.set(key, index); positions.push(...encoded); }
      indices.push(index);
    }
    const positionBounds = quantize ? { min: [0, 0, 0], max: steps.map(step => step ? 65535 : 0) } : { min: minimum, max: maximum };
    const positionAccessor = accessor(quantize ? new Uint16Array(positions) : new Float32Array(positions), 'VEC3', 34962, positionBounds);
    const indexAccessor = accessor(unique.size > 65535 ? new Uint32Array(indices) : new Uint16Array(indices), 'SCALAR', 34963);
    const meshIndex = document.meshes.length;
    document.meshes.push({ name: kind, extras: { surfaceKind: kind }, primitives: [{ attributes: { POSITION: positionAccessor }, indices: indexAccessor, mode: 4 }] });
    document.nodes.push({ mesh: meshIndex, ...(quantize ? { translation: minimum, scale: steps.map(step => step || 1) } : {}), extras: { surfaceKind: kind, maximumPositionErrorMetres: quantize ? steps.map(step => step / 2) : [0, 0, 0] } });
    document.scenes[0].nodes.push(meshIndex); triangles += indices.length / 3;
    quantize ? quantizedMeshes++ : exactMeshes++;
  }
  if (quantizedMeshes) document.extensionsUsed = document.extensionsRequired = ['KHR_mesh_quantization'];
  document.buffers[0].byteLength = length;
  const json = Buffer.from(JSON.stringify(document)), jsonChunk = Buffer.concat([json, Buffer.alloc((4 - json.length % 4) % 4, 0x20)]), binaryChunk = Buffer.concat([...chunks, Buffer.alloc((4 - length % 4) % 4)]);
  const header = Buffer.alloc(12), jsonHeader = Buffer.alloc(8), binaryHeader = Buffer.alloc(8);
  header.write('glTF'); header.writeUInt32LE(2, 4); header.writeUInt32LE(28 + jsonChunk.length + binaryChunk.length, 8);
  jsonHeader.writeUInt32LE(jsonChunk.length); jsonHeader.writeUInt32LE(0x4e4f534a, 4);
  binaryHeader.writeUInt32LE(binaryChunk.length); binaryHeader.writeUInt32LE(0x004e4942, 4);
  return { bytes: Buffer.concat([header, jsonHeader, jsonChunk, binaryHeader, binaryChunk]), triangles, quantizedMeshes, exactMeshes };
}
await mkdir(output, { recursive: true });
const allBounds = new THREE.Box3(), children = [], tiles = [];
for (const [key, bucket] of [...buckets].sort(([a], [b]) => a.localeCompare(b))) {
  const filename = `${key}.glb`, encoded = encodeTile(bucket);
  await writeFile(new URL(filename, output), encoded.bytes);
  children.push({ boundingVolume: { box: enuBox(bucket.bounds) }, geometricError: 0, content: { uri: filename } });
  allBounds.union(bucket.bounds);
  tiles.push({ uri: filename, features: bucket.features, triangles: encoded.triangles, bytes: encoded.bytes.length, gzipBytes: gzipSync(encoded.bytes).length, quantizedMeshes: encoded.quantizedMeshes, exactMeshes: encoded.exactMeshes });
}
const tileset = { asset: { version: '1.1', gltfUpAxis: 'Y' }, geometricError: 1e6, root: { transform: enuToEarth.toArray(), boundingVolume: { box: enuBox(allBounds) }, geometricError: 1e6, refine: 'REPLACE', children } };
await writeFile(new URL('tileset.json', output), JSON.stringify(tileset));
const manifest = {
  source: { input: input.pathname.split('/').pop(), sha256: createHash('sha256').update(sourceBytes).digest('hex'), ...Object.fromEntries(Object.entries(collection).filter(([key]) => key !== 'features')) },
  origin, meshAxes: 'X east, Y up, Z south', tileAxes: 'X east, Y north, Z up', rootTransform: 'ENU to WGS84 ECEF',
  bucketSizeMetres, bucketing: 'feature bounding-box centre; tile bounds include complete feature geometry', maximumQuantizationErrorMetres,
  semantics: { polygonHeightMetres: -0.55, ribbonHeightMetres: -0.45, ribbonWidths: 'rail double 6m/single3.2m; road width classes 4–7m:5.5m,2–4m:3m,otherwise1.6m', surfaceKind: 'rail; hoofdverkeersgebruik includes fiets:cycleway, voetganger:footway; otherwise road', excludes: 'brug/tunnel/overkluisd, hoogteniveau<0, veerverbinding, status other than in gebruik', elevation: 'illustrative 2D network, not measured road/rail elevations' },
  runtimeLimit: 'No coarse parent geometry. Show only at span<8000; retain coarse overview for wider views.', inputFeatures: collection.features.length, includedFeatures: Object.values(counts).reduce((a, b) => a + b, 0), surfaceCounts: counts, excluded, tiles,
};
await writeFile(new URL('manifest.json', output), JSON.stringify(manifest, null, 2) + '\n');
console.log(JSON.stringify({ tiles: tiles.length, triangles: tiles.reduce((s, t) => s + t.triangles, 0), bytes: tiles.reduce((s, t) => s + t.bytes, 0), gzipBytes: tiles.reduce((s, t) => s + t.gzipBytes, 0), quantizedMeshes: tiles.reduce((s, t) => s + t.quantizedMeshes, 0), exactMeshes: tiles.reduce((s, t) => s + t.exactMeshes, 0), includedFeatures: manifest.includedFeatures }));
