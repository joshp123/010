import * as THREE from 'three';

const sourceIndices = new WeakMap();
const WGS84_RADIUS = 6378137;
const WGS84_POLAR_RADIUS = 6356752.314245179;
const WGS84_ECCENTRICITY_SQUARED = 0.0066943799901413165;
const WGS84_SECOND_ECCENTRICITY_SQUARED = 0.006739496742276434;
const MINIMUM_SURFACE_HEIGHT = -30;
const SURFACE_CLASSES = new Set(['Begroeid terreindeel', 'Onbegroeid terreindeel', 'Wegdeel', 'Ondersteunend wegdeel', 'Waterdeel', 'Ondersteunend waterdeel']);

function geographicPosition(point) {
  const radius = Math.hypot(point.x, point.y);
  const theta = Math.atan2(point.z * WGS84_RADIUS, radius * WGS84_POLAR_RADIUS);
  const latitude = Math.atan2(
    point.z + WGS84_SECOND_ECCENTRICITY_SQUARED * WGS84_POLAR_RADIUS * Math.sin(theta) ** 3,
    radius - WGS84_ECCENTRICITY_SQUARED * WGS84_RADIUS * Math.cos(theta) ** 3,
  );
  const sine = Math.sin(latitude);
  const height = radius * Math.cos(latitude) + point.z * sine - WGS84_RADIUS * Math.sqrt(1 - WGS84_ECCENTRICITY_SQUARED * sine * sine);
  return [Math.atan2(point.y, point.x), latitude, height];
}

function isSurface(attributes) {
  return SURFACE_CLASSES.has(attributes.KLASSE_IMG) && !/kade|muur|damwand|keerwand/i.test(`${attributes.KLASSE || ''} ${attributes.FYSIEKVK || ''}`);
}

// The native model root contains the source/tile ECEF transform. Remove any
// renderer parent frame before reading it; attachment must not change filtering.
export function omitInvalidGroundTriangles(model) {
  model.updateWorldMatrix(true, true);
  const parentFrameInverse = model.parent ? model.parent.matrixWorld.clone().invert() : new THREE.Matrix4();
  const meshToEarth = new THREE.Matrix4();
  const point = new THREE.Vector3();
  let minimumHeight = Infinity, maximumHeight = -Infinity;
  let sourceTriangles = 0, missingHeightTriangles = 0, interpolatedMissingHeightTriangles = 0, verticalSkirtTriangles = 0;
  model.traverse(mesh => {
    if (!mesh.isMesh) return;
    const geometry = mesh.geometry;
    if (sourceIndices.has(geometry)) return;
    const positions = geometry.getAttribute('position'), sourceIndex = geometry.index;
    const indexCount = sourceIndex?.count ?? positions.count;
    const geographic = new Float64Array(positions.count * 3);
    const batchIds = geometry.getAttribute('_batchid'), missingHeightBatches = new Set();
    meshToEarth.multiplyMatrices(parentFrameInverse, mesh.matrixWorld);
    for (let vertex = 0; vertex < positions.count; vertex++) {
      point.fromBufferAttribute(positions, vertex).applyMatrix4(meshToEarth);
      const coordinate = geographicPosition(point);
      geographic.set(coordinate, vertex * 3);
      minimumHeight = Math.min(minimumHeight, coordinate[2]);
      maximumHeight = Math.max(maximumHeight, coordinate[2]);
      if (Math.abs(coordinate[2] + 99.99) < 0.01) missingHeightBatches.add(batchIds?.getX(vertex));
    }
    const longitudeScale = WGS84_RADIUS * Math.cos(geographic[1]);
    const surfaceBatches = new Map();
    let ancestor = mesh;
    while (ancestor && !ancestor.batchTable) ancestor = ancestor.parent;
    const retainedIndices = [];
    for (let offset = 0; offset < indexCount; offset += 3) {
      const vertices = [0, 1, 2].map(corner => sourceIndex ? sourceIndex.getX(offset + corner) : offset + corner);
      sourceTriangles++;
      const batchId = batchIds?.getX(vertices[0]);
      if (!surfaceBatches.has(batchId)) surfaceBatches.set(batchId, isSurface(ancestor?.batchTable?.getDataFromId(batchId)?.attributes || {}));
      const [a, b, c] = vertices.map(vertex => vertex * 3);
      const heights = [geographic[a + 2], geographic[b + 2], geographic[c + 2]];
      if (heights.some(height => Math.abs(height + 99.99) < 0.01)) { missingHeightTriangles++; continue; }
      if ((surfaceBatches.get(batchId) || missingHeightBatches.has(batchId)) && heights.some(height => height < MINIMUM_SURFACE_HEIGHT)) { interpolatedMissingHeightTriangles++; continue; }
      if (surfaceBatches.get(batchId)) {
        const abX = (geographic[b] - geographic[a]) * longitudeScale;
        const abY = (geographic[b + 1] - geographic[a + 1]) * WGS84_RADIUS;
        const acX = (geographic[c] - geographic[a]) * longitudeScale;
        const acY = (geographic[c + 1] - geographic[a + 1]) * WGS84_RADIUS;
        const longestEdge = Math.max(Math.hypot(abX, abY), Math.hypot(acX, acY), Math.hypot(abX - acX, abY - acY));
        const doubledPlanArea = Math.abs(abX * acY - abY * acX);
        if (Math.max(...heights) - Math.min(...heights) > 1 && doubledPlanArea < 0.05 * longestEdge) { verticalSkirtTriangles++; continue; }
      }
      retainedIndices.push(...vertices);
    }
    if (retainedIndices.length === indexCount) return;
    sourceIndices.set(geometry, sourceIndex);
    const IndexArray = sourceIndex ? sourceIndex.array.constructor : positions.count > 65535 ? Uint32Array : Uint16Array;
    geometry.setIndex(new THREE.BufferAttribute(new IndexArray(retainedIndices), 1));
  });
  return { sourceTriangles, missingHeightTriangles, interpolatedMissingHeightTriangles, verticalSkirtTriangles, sourceHeightRangeMetres: [minimumHeight, maximumHeight], sourceHadParent: model.parent !== null };
}

export function originalGroundIndex(geometry) {
  return sourceIndices.has(geometry) ? sourceIndices.get(geometry) : geometry.index;
}
