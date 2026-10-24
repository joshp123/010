#!/usr/bin/env node
// Written by AI on 2026-10-24 by model GPT-6 Astra.
// Cached source only. Keep native geometry/URLs and derive bounds from the shipped filter's retained triangles.
// devenv shell -- node scripts/build-ground-bounds.mjs --output work/ground-bounds-candidate
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { registerHooks } from 'node:module';
import { createHash } from 'node:crypto';
import { gzipSync, gunzipSync } from 'node:zlib';

const project = fileURLToPath(new URL('../', import.meta.url));
const argumentsList = process.argv.slice(2);
const argument = (name, fallback) => {
  const index = argumentsList.indexOf(name);
  return index < 0 ? fallback : argumentsList[index + 1];
};
const outputArgument = argument('--output');
if (!outputArgument) throw new Error('Provide --output with a separate candidate directory');
const outputDirectory = path.resolve(project, outputArgument);
const sourcePath = path.resolve(project, argument('--source', 'work/source-quality/ground-model.json'));
const sourceBase = 'https://www.3drotterdam.nl/datasource-data/0025cb58-e0f5-4169-bb4c-5339a3bc2a7e/';
const sourceBytes = await fs.readFile(sourcePath);
const tileset = JSON.parse(sourceBytes);
const originalTileset = structuredClone(tileset);
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
registerHooks({
  resolve(specifier, context, next) {
    if (specifier === 'three') return { url: pathToFileURL(path.join(project, 'public/vendor/three/build/three.module.js')).href, shortCircuit: true };
    if (specifier.startsWith('three/addons/')) return { url: pathToFileURL(path.join(project, 'public/vendor/three/examples/jsm', specifier.slice(13))).href, shortCircuit: true };
    return next(specifier, context);
  },
});
const THREE = await import('three');
const { B3DMLoader } = await import(pathToFileURL(path.join(project, 'public/vendor/3d-tiles-renderer/build/index.three.js')));
const filterPath = path.join(project, 'public/ground-height-filter.js');
const { omitInvalidGroundTriangles } = await import(pathToFileURL(filterPath));
const contentTiles = new Map();
let ancestorCount = 0;
function inventory(tile) {
  if (tile.transform) throw new Error('This source stage expects the retained native ECEF source with no tile transforms');
  if (tile.content) contentTiles.set(tile.content.uri, tile);
  if (tile.children?.length) ancestorCount++;
  for (const child of tile.children || []) inventory(child);
}
inventory(tileset.root);

const cachedSources = new Map();
const cacheDirectory = path.join(project, 'work/data-cache/green-terrain');
for (const filename of await fs.readdir(cacheDirectory)) {
  if (!filename.endsWith('.json')) continue;
  const metadata = JSON.parse(await fs.readFile(path.join(cacheDirectory, filename)));
  if (!metadata.url?.startsWith(sourceBase)) continue;
  const uri = metadata.url.slice(sourceBase.length);
  if (contentTiles.has(uri)) cachedSources.set(uri, {
    filename: path.join(cacheDirectory, filename.replace(/\.json$/, '.gz')),
    expectedSha256: metadata.sha256,
    identity: 'retained acquisition URL and source hash',
    originalEncodedBytes: metadata.headers?.['Content-Encoding'] === 'gzip' ? Number(metadata.headers['Content-Length']) : null,
  });
}
const samplesDirectory = path.join(project, 'work/source-quality');
const inspectionPath = path.join(samplesDirectory, 'ground-height/inspection.json');
const inspection = JSON.parse(await fs.readFile(inspectionPath));
const inspectedHashes = new Map(inspection.sources.map(record => [record.source.slice(sourceBase.length), record.sha256]));
for (const filename of await fs.readdir(samplesDirectory, { recursive: true })) {
  if (!filename.endsWith('.b3dm') || !(filename.includes('ground') || filename.startsWith('ground-height/'))) continue;
  const match = filename.match(/(33\d{3})-(69\d{2})/);
  if (!match) continue;
  const uri = `15/${match[1]}/${match[2]}.b3dm`;
  if (contentTiles.has(uri) && !cachedSources.has(uri)) cachedSources.set(uri, {
    filename: path.join(samplesDirectory, filename),
    expectedSha256: inspectedHashes.get(uri),
    identity: inspectedHashes.has(uri) ? 'retained inspection URL and source hash' : 'retained exact-source sample named by tile coordinates',
  });
}
for (const filename of await fs.readdir(samplesDirectory)) {
  if (!filename.startsWith('ground-model--') || !filename.endsWith('-location.json')) continue;
  const record = JSON.parse(await fs.readFile(path.join(samplesDirectory, filename)));
  if (!record.url?.startsWith(sourceBase)) continue;
  const uri = record.url.slice(sourceBase.length);
  const sample = path.join(samplesDirectory, filename.replace('-location.json', '.b3dm'));
  if (contentTiles.has(uri) && !cachedSources.has(uri) && await fs.stat(sample).catch(() => null)) {
    cachedSources.set(uri, { filename: sample, identity: 'retained source-location URL' });
  }
}

const sourcePoint = new THREE.Vector3();
function geographicPosition(point) {
  const radius = Math.hypot(point.x, point.y);
  const theta = Math.atan2(point.z * 6378137, radius * 6356752.314245179);
  const latitude = Math.atan2(
    point.z + 0.006739496742276434 * 6356752.314245179 * Math.sin(theta) ** 3,
    radius - 0.0066943799901413165 * 6378137 * Math.cos(theta) ** 3,
  );
  const sine = Math.sin(latitude);
  const height = radius * Math.cos(latitude) + point.z * sine - 6378137 * Math.sqrt(1 - 0.0066943799901413165 * sine * sine);
  return [Math.atan2(point.y, point.x), latitude, height];
}
function retainedBounds(scene) {
  const minimum = [Infinity, Infinity, Infinity], maximum = [-Infinity, -Infinity, -Infinity];
  const deepClasses = new Set();
  let triangles = 0;
  scene.updateMatrixWorld(true);
  scene.traverse(mesh => {
    if (!mesh.isMesh) return;
    const geometry = mesh.geometry, positions = geometry.attributes.position, indices = geometry.index;
    const coordinates = new Float64Array(positions.count * 3), used = new Uint8Array(positions.count);
    for (const vertex of indices.array) used[vertex] = 1;
    for (let vertex = 0; vertex < positions.count; vertex++) {
      if (!used[vertex]) continue;
      sourcePoint.fromBufferAttribute(positions, vertex).applyMatrix4(mesh.matrixWorld);
      const position = geographicPosition(sourcePoint);
      coordinates.set(position, vertex * 3);
      for (let axis = 0; axis < 3; axis++) {
        minimum[axis] = Math.min(minimum[axis], position[axis]);
        maximum[axis] = Math.max(maximum[axis], position[axis]);
      }
    }
    let ancestor = mesh;
    while (ancestor && !ancestor.batchTable) ancestor = ancestor.parent;
    for (let offset = 0; offset < indices.count; offset += 3) {
      triangles++;
      if ([0, 1, 2].some(corner => coordinates[indices.getX(offset + corner) * 3 + 2] < -30)) {
        const batchId = geometry.attributes._batchid?.getX(indices.getX(offset));
        const attributes = ancestor?.batchTable?.getDataFromId(batchId)?.attributes || {};
        deepClasses.add(`${attributes.KLASSE_IMG || 'unknown'}/${attributes.KLASSE || 'unknown'}`);
      }
    }
    geometry.dispose();
  });
  return { minimum, maximum, triangles, deepClasses: [...deepClasses] };
}
function correctRegion(region, bounds) {
  // Preserve source horizontal bounds; expand if observed vertices exceed them.
  const angularMargin = 0.01 / 6378137;
  return [
    Math.min(region[0], bounds.minimum[0] - angularMargin),
    Math.min(region[1], bounds.minimum[1] - angularMargin),
    Math.max(region[2], bounds.maximum[0] + angularMargin),
    Math.max(region[3], bounds.maximum[1] + angularMargin),
    Math.floor(bounds.minimum[2] * 100) / 100 - 1,
    Math.ceil(bounds.maximum[2] * 100) / 100 + 1,
  ];
}
const started = performance.now();
const reports = [];
for (const [uri, source] of [...cachedSources].sort(([first], [second]) => first.localeCompare(second))) {
  const tile = contentTiles.get(uri), before = performance.now();
  const stored = await fs.readFile(source.filename);
  const decoded = stored[0] === 31 && stored[1] === 139 ? gunzipSync(stored) : stored;
  const sha256 = hash(decoded);
  if (source.expectedSha256 && sha256 !== source.expectedSha256) throw new Error(`Source cache hash differs: ${uri}`);
  const loader = new B3DMLoader();
  loader.adjustmentTransform.makeRotationX(Math.PI / 2);
  const { scene } = await loader.parse(decoded.buffer.slice(decoded.byteOffset, decoded.byteOffset + decoded.byteLength));
  const filter = omitInvalidGroundTriangles(scene);
  const retained = retainedBounds(scene);
  const originalRegion = [...tile.boundingVolume.region];
  if (retained.triangles) {
    tile.boundingVolume.region = correctRegion(tile.boundingVolume.region, retained);
    if (tile.content.boundingVolume) tile.content.boundingVolume.region = correctRegion(tile.content.boundingVolume.region, retained);
  }
  reports.push({
    uri, sourceSha256: sha256, cache: path.relative(project, source.filename), identity: source.identity,
    originalEncodedBytes: source.originalEncodedBytes || null,
    decodedBytes: decoded.length, gzipBytes: gzipSync(decoded).length,
    originalRegion, correctedRegion: [...tile.boundingVolume.region],
    retainedTriangles: retained.triangles,
    retainedHeight: retained.triangles ? [retained.minimum[2], retained.maximum[2]] : null,
    retainedDeepClasses: retained.deepClasses,
    emptyBoundsUnchanged: retained.triangles === 0, filter,
    extractionMilliseconds: performance.now() - before,
  });
}
function reconcileAncestors(tile) {
  for (const child of tile.children || []) reconcileAncestors(child);
  if (!tile.children?.length) return;
  const region = tile.boundingVolume.region;
  const contributors = tile.children.map(child => child.boundingVolume.region);
  if (tile.content) contributors.push(tile.content.boundingVolume?.region || region);
  tile.boundingVolume.region = [
    Math.min(region[0], ...contributors.map(child => child[0])),
    Math.min(region[1], ...contributors.map(child => child[1])),
    Math.max(region[2], ...contributors.map(child => child[2])),
    Math.max(region[3], ...contributors.map(child => child[3])),
    Math.min(...contributors.map(child => child[4])),
    Math.max(...contributors.map(child => child[5])),
  ];
}
reconcileAncestors(tileset.root);
function absoluteContentUrls(tile) {
  if (tile.content) tile.content.uri = new URL(tile.content.uri, sourceBase).href;
  for (const child of tile.children || []) absoluteContentUrls(child);
}
absoluteContentUrls(tileset.root);
const candidateBytes = Buffer.from(JSON.stringify(tileset));
const report = {
  writtenBy: 'AI, GPT-6 Astra, 2026-10-24',
  command: 'devenv shell -- node scripts/build-ground-bounds.mjs --output <separate-candidate-directory>',
  source: sourceBase + 'tileset.json', sourceInventorySha256: hash(sourceBytes),
  shippedFilterSha256: hash(await fs.readFile(filterPath)),
  rule: 'Exact shipped ground filtering; bounds enclose every retained indexed vertex in every class. Original horizontal extents retained/expanded; vertical extrema rounded outward with a 1 m margin for triangle chord sag. Empty and unprocessed content bounds unchanged. Ancestors enclose all child bounds. Native model bytes/geometry/materials are not replaced.',
  totalContentTiles: contentTiles.size, ancestorCount,
  cachedContentTiles: reports.length,
  correctedContentTiles: reports.filter(item => item.retainedTriangles).length,
  emptyContentTilesLeftUnchanged: reports.filter(item => item.emptyBoundsUnchanged).length,
  unprocessedContentTiles: contentTiles.size - reports.length,
  decodedBytesRead: reports.reduce((sum, item) => sum + item.decodedBytes, 0),
  cachedSourceGzipBytes: reports.reduce((sum, item) => sum + item.gzipBytes, 0),
  candidateBytes: candidateBytes.length, candidateGzipBytes: gzipSync(candidateBytes).length,
  extractionSeconds: (performance.now() - started) / 1000,
  retainedDeepGeometry: reports.filter(item => item.retainedHeight?.[0] < -30),
  sources: reports,
};
await fs.mkdir(outputDirectory, { recursive: true });
await fs.writeFile(path.join(outputDirectory, 'tileset.json'), candidateBytes);
await fs.writeFile(path.join(outputDirectory, 'manifest.json'), JSON.stringify(report, null, 2) + '\n');
await fs.writeFile(path.join(outputDirectory, 'original-tileset.json'), JSON.stringify(originalTileset));
console.log(JSON.stringify(Object.fromEntries(Object.entries(report).filter(([key]) => !['sources', 'retainedDeepGeometry'].includes(key))), null, 2));
