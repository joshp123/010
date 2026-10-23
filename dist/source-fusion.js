// Written by AI on 2026-10-24 by model GPT-6.
import * as THREE from 'three';

// Geometry stage: native bridge meshes take precedence over duplicate BGT bridge
// structures and nearby paving. Source attributes and original meshes stay intact.
const CELL_METRES = 32;
const SURFACE_HEIGHT_TOLERANCE_METRES = 3;
const AREA_EPSILON = 0.00001;
const signedArea = points => points.reduce((area, point, index) => { const next = points[(index + 1) % points.length]; return area + point.x * next.z - next.x * point.z; }, 0) / 2;
const edgeSide = (point, start, end) => (end.x - start.x) * (point.z - start.z) - (end.z - start.z) * (point.x - start.x);
const boundsFor = points => ({ minX: Math.min(...points.map(p => p.x)), maxX: Math.max(...points.map(p => p.x)), minZ: Math.min(...points.map(p => p.z)), maxZ: Math.max(...points.map(p => p.z)) });
const intersects = (a, b) => a.maxX >= b.minX && a.minX <= b.maxX && a.maxZ >= b.minZ && a.minZ <= b.maxZ;
function cellsFor(bounds) {
  const cells = [];
  for (let x = Math.floor(bounds.minX / CELL_METRES); x <= Math.floor(bounds.maxX / CELL_METRES); x++) {
    for (let z = Math.floor(bounds.minZ / CELL_METRES); z <= Math.floor(bounds.maxZ / CELL_METRES); z++) cells.push(`${x}:${z}`);
  }
  return cells;
}
function interpolate(a, b, ratio) {
  return { x: a.x + (b.x - a.x) * ratio, y: a.y + (b.y - a.y) * ratio, z: a.z + (b.z - a.z) * ratio, weights: a.weights.map((weight, index) => weight + (b.weights[index] - weight) * ratio) };
}
function halfPlane(polygon, start, end, inside) {
  const output = [];
  for (let index = 0; index < polygon.length; index++) {
    const current = polygon[index], next = polygon[(index + 1) % polygon.length];
    const currentDistance = edgeSide(current, start, end), nextDistance = edgeSide(next, start, end);
    const currentInside = inside ? currentDistance >= 0 : currentDistance <= 0;
    const nextInside = inside ? nextDistance >= 0 : nextDistance <= 0;
    if (currentInside) output.push(current);
    if (currentInside !== nextInside) output.push(interpolate(current, next, currentDistance / (currentDistance - nextDistance)));
  }
  return output;
}
function subtractTriangle(polygon, triangle) {
  let remaining = polygon;
  const outside = [];
  for (let edge = 0; edge < 3 && remaining.length >= 3; edge++) {
    const start = triangle[edge], end = triangle[(edge + 1) % 3];
    const fragment = halfPlane(remaining, start, end, false);
    if (fragment.length >= 3 && Math.abs(signedArea(fragment)) > AREA_EPSILON) outside.push(fragment);
    remaining = halfPlane(remaining, start, end, true);
  }
  return { outside, overlap: remaining.length >= 3 && Math.abs(signedArea(remaining)) > AREA_EPSILON };
}
function* trianglesFor(mesh, geometry = mesh.geometry) {
  const positions = geometry.getAttribute('position'), indices = geometry.index;
  const transform = mesh.matrixWorld;
  for (let offset = 0; offset < (indices?.count ?? positions.count); offset += 3) {
    const vertexIndices = [0, 1, 2].map(i => indices ? indices.getX(offset + i) : offset + i);
    const points = vertexIndices.map((index, corner) => {
      const point = new THREE.Vector3().fromBufferAttribute(positions, index).applyMatrix4(transform);
      return { x: point.x, y: point.y, z: point.z, weights: [0, 1, 2].map(i => Number(i === corner)) };
    });
    yield { points, vertexIndices, bounds: boundsFor(points) };
  }
}
function featureAttributes(mesh, vertex) {
  const batch = mesh.geometry.getAttribute('_batchid');
  let parent = mesh;
  while (parent && !parent.batchTable) parent = parent.parent;
  if (!batch || !parent) return {};
  return parent.batchTable.getDataFromId(batch.getX(vertex))?.attributes || {};
}
function bridgeHeightAt(triangle, point) {
  const [a, b, c] = triangle;
  const denominator = edgeSide(c, a, b);
  const cWeight = edgeSide(point, a, b) / denominator;
  const bWeight = ((point.x - a.x) * (c.z - a.z) - (c.x - a.x) * (point.z - a.z)) / denominator;
  return a.y + bWeight * (b.y - a.y) + cWeight * (c.y - a.y);
}

export function createSourceFusion() {
  const groundModels = new Map(), bridgeModels = new Set(), groundRevisions = new WeakMap(), meshResults = new Map();
  let dirty = false, bridgeRevision = 0, bridgeGridRevision = -1, previousBridgeModels = [], diagnostics = {};
  const grid = new Map();
  let bridgeTriangles = 0;
  function restore(mesh, original) {
    if (mesh.geometry !== original) { mesh.geometry.dispose(); mesh.geometry = original; }
  }
  function removeGround(model) {
    for (const [mesh, original] of groundModels.get(model) || []) { restore(mesh, original); meshResults.delete(mesh); }
    groundModels.delete(model); dirty = true;
  }
  function update() {
    if (!dirty) return false;
    dirty = false;
    const started = performance.now();
    let removedStructures = 0, clippedTriangles = 0, processedMeshes = 0;
    if (bridgeGridRevision !== bridgeRevision) {
      bridgeGridRevision = bridgeRevision; grid.clear(); bridgeTriangles = 0;
      for (const model of bridgeModels) {
        model.updateWorldMatrix(true, true);
        model.traverse(mesh => {
          if (!mesh.isMesh) return;
          for (const triangle of trianglesFor(mesh)) {
            const [a, b, c] = triangle.points;
            const normal = new THREE.Vector3(b.x-a.x,b.y-a.y,b.z-a.z).cross(new THREE.Vector3(c.x-a.x,c.y-a.y,c.z-a.z));
            // Steep walls/cables are not a deck footprint. Both mesh windings occur.
            if (Math.abs(normal.y) < normal.length() * 0.7 || Math.abs(signedArea(triangle.points)) < AREA_EPSILON) continue;
            if (signedArea(triangle.points) < 0) triangle.points.reverse();
            for (const cell of cellsFor(triangle.bounds)) { if (!grid.has(cell)) grid.set(cell, []); grid.get(cell).push(triangle); }
            bridgeTriangles++;
          }
        });
      }
    }
    for (const [model, originals] of groundModels) {
      if (groundRevisions.get(model) === bridgeRevision) continue;
      groundRevisions.set(model, bridgeRevision);
      model.updateWorldMatrix(true, true);
      for (const [mesh, original] of originals) {
        restore(mesh, original);
        meshResults.delete(mesh);
        if (!grid.size) continue;
        const meshBounds = new THREE.Box3().setFromBufferAttribute(original.getAttribute('position')).applyMatrix4(mesh.matrixWorld);
        if (!cellsFor({ minX: meshBounds.min.x, maxX: meshBounds.max.x, minZ: meshBounds.min.z, maxZ: meshBounds.max.z }).some(cell => grid.has(cell))) continue;
        processedMeshes++;
        const positions = original.getAttribute('position'), sourceIndices = original.index;
        const indexCount = sourceIndices?.count ?? positions.count;
        const indexAt = offset => sourceIndices ? sourceIndices.getX(offset) : offset;
        const batchIds = original.getAttribute('_batchid'), attributesByBatch = new Map();
        const suppressedBatches = new Set(), changedTriangles = new Map();
        const vertex = new THREE.Vector3();
        for (let offset = 0; offset < indexCount; offset += 3) {
          const firstVertex = indexAt(offset), batchId = batchIds?.getX(firstVertex) ?? 0;
          if (suppressedBatches.has(batchId)) continue;
          if (!attributesByBatch.has(batchId)) attributesByBatch.set(batchId, featureAttributes(mesh, firstVertex));
          const attributes = attributesByBatch.get(batchId);
          const structure = attributes.KLASSE_IMG === 'Overbruggingsdeel';
          const paving = /verharding/i.test(attributes.FYSIEKVK || '') || /wegdeel/i.test(attributes.KLASSE_IMG || '');
          if (!structure && !paving) continue;
          const vertexIndices = [firstVertex, indexAt(offset + 1), indexAt(offset + 2)];
          const points = vertexIndices.map((index, corner) => {
            vertex.fromBufferAttribute(positions, index).applyMatrix4(mesh.matrixWorld);
            return { x: vertex.x, y: vertex.y, z: vertex.z, weights: [Number(corner === 0), Number(corner === 1), Number(corner === 2)] };
          });
          const bounds = boundsFor(points);
          const candidates = new Set(cellsFor(bounds).flatMap(cell => grid.get(cell) || []));
          let polygons = [points], changed = false;
          for (const candidate of candidates) {
            if (!intersects(bounds, candidate.bounds)) continue;
            if (!structure && !points.some(point => Math.abs(point.y - bridgeHeightAt(candidate.points, point)) <= SURFACE_HEIGHT_TOLERANCE_METRES)) continue;
            const next = [];
            for (const polygon of polygons) {
              const result = subtractTriangle(polygon, candidate.points);
              if (result.overlap) { changed = true; next.push(...result.outside); } else next.push(polygon);
            }
            polygons = next;
            if (!polygons.length || structure && changed) break;
          }
          if (structure && changed) suppressedBatches.add(batchId);
          if (changed) changedTriangles.set(offset, { vertexIndices, polygons });
        }
        if (!changedTriangles.size) continue;
        const attributeEntries = Object.entries(original.attributes);
        const appendedAttributes = Object.fromEntries(attributeEntries.map(([name]) => [name, []]));
        const outputIndices = [];
        let appendedVertexCount = 0;
        for (let offset = 0; offset < indexCount; offset += 3) {
          const batchId = batchIds?.getX(indexAt(offset)) ?? 0;
          if (suppressedBatches.has(batchId)) continue;
          const changed = changedTriangles.get(offset);
          if (!changed) { outputIndices.push(indexAt(offset), indexAt(offset + 1), indexAt(offset + 2)); continue; }
          for (const polygon of changed.polygons) {
            for (let corner = 1; corner < polygon.length - 1; corner++) {
              for (const point of [polygon[0], polygon[corner], polygon[corner + 1]]) {
                const originalCorner = point.weights.findIndex(weight => weight === 1);
                if (originalCorner !== -1) { outputIndices.push(changed.vertexIndices[originalCorner]); continue; }
                outputIndices.push(positions.count + appendedVertexCount++);
                for (const [name, attribute] of attributeEntries) {
                  for (let component = 0; component < attribute.itemSize; component++) {
                    const value = point.weights.reduce((sum, weight, index) => sum + weight * attribute.getComponent(changed.vertexIndices[index], component), 0);
                    appendedAttributes[name].push(value);
                  }
                }
              }
            }
          }
        }
        const fused = new THREE.BufferGeometry();
        for (const [name, attribute] of attributeEntries) {
          if (!appendedVertexCount) { fused.setAttribute(name, attribute); continue; }
          const values = new Float32Array((attribute.count + appendedVertexCount) * attribute.itemSize);
          if (!attribute.isInterleavedBufferAttribute && !attribute.normalized) values.set(attribute.array);
          else for (let index = 0; index < attribute.count; index++) {
            for (let component = 0; component < attribute.itemSize; component++) values[index * attribute.itemSize + component] = attribute.getComponent(index, component);
          }
          values.set(appendedAttributes[name], attribute.count * attribute.itemSize);
          fused.setAttribute(name, new THREE.Float32BufferAttribute(values, attribute.itemSize));
        }
        fused.setIndex(outputIndices);
        // Difference fragments stay inside source triangles, so source bounds remain valid.
        if (!original.boundingBox) original.computeBoundingBox();
        if (!original.boundingSphere) original.computeBoundingSphere();
        fused.boundingBox = original.boundingBox.clone(); fused.boundingSphere = original.boundingSphere.clone();
        fused.userData = { ...original.userData, sourceFusion: { primary: 'native-bridges', secondary: 'BGT', operation: 'projected-triangle-difference', surfaceHeightToleranceMetres: SURFACE_HEIGHT_TOLERANCE_METRES } };
        mesh.geometry = fused;
        const sourceBytes = attributeEntries.reduce((sum, [, attribute]) => sum + attribute.array.byteLength, 0);
        const additionalBytes = fused.index.array.byteLength + (appendedVertexCount ? Object.values(fused.attributes).reduce((sum, attribute) => sum + attribute.array.byteLength, 0) : 0);
        meshResults.set(mesh, { structures: suppressedBatches.size, triangles: changedTriangles.size, sourceBytes, additionalBytes, appendedVertexCount });
      }
    }
    let retainedSourceBytes = 0, additionalGeometryBytes = 0, appendedVertices = 0;
    for (const result of meshResults.values()) { removedStructures += result.structures; clippedTriangles += result.triangles; retainedSourceBytes += result.sourceBytes; additionalGeometryBytes += result.additionalBytes; appendedVertices += result.appendedVertexCount; }
    diagnostics = { bridgeModels: bridgeModels.size, bridgeTriangles, groundModels: groundModels.size, removedStructureFeatures: removedStructures, clippedSourceTriangles: clippedTriangles, processedMeshes, retainedSourceBytes, additionalGeometryBytes, appendedVertices, milliseconds: Math.round(performance.now() - started) };
    return true;
  }
  return {
    addGround(model) {
      const originals = new Map();
      model.traverse(mesh => { if (mesh.isMesh) originals.set(mesh, mesh.geometry); });
      groundModels.set(model, originals); groundRevisions.delete(model); dirty = true;
    },
    removeGround,
    setVisibleBridges(models) {
      if (models.length === previousBridgeModels.length && models.every(model => bridgeModels.has(model))) return;
      previousBridgeModels = models; bridgeRevision++; bridgeModels.clear(); models.forEach(model => bridgeModels.add(model)); dirty = true;
    },
    update,
    getDiagnostics: () => diagnostics,
    dispose() { for (const model of [...groundModels.keys()]) removeGround(model); bridgeModels.clear(); grid.clear(); previousBridgeModels = []; },
  };
}
