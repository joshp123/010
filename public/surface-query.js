import * as THREE from 'three';

const CELL_METRES = 32;
const MAXIMUM_TRIANGLE_CELLS = 64;
const cellKey = (x, z) => `${x}:${z}`;

// Exact vertical intersections with the current visible source geometry.
// The grid stores source index offsets, never sampled or quantized heights.
export function createSurfaceQuery() {
  const records = new Map();
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
  const edge = new THREE.Vector3(), normal = new THREE.Vector3(), hit = new THREE.Vector3();
  const ray = new THREE.Ray(new THREE.Vector3(), new THREE.Vector3(0, -1, 0));
  const counters = { builds: 0, buildMilliseconds: 0, queries: 0, testedTriangles: 0 };

  function build(mesh) {
    const started = performance.now();
    const geometry = mesh.geometry, position = geometry.getAttribute('position'), index = geometry.index;
    const start = geometry.drawRange.start, end = Math.min(index?.count ?? position.count, start + geometry.drawRange.count);
    const matrix = mesh.matrixWorld.clone(), cells = new Map(), largeTriangles = [];
    for (let offset = start; offset + 2 < end; offset += 3) {
      a.fromBufferAttribute(position, index ? index.getX(offset) : offset).applyMatrix4(matrix);
      b.fromBufferAttribute(position, index ? index.getX(offset + 1) : offset + 1).applyMatrix4(matrix);
      c.fromBufferAttribute(position, index ? index.getX(offset + 2) : offset + 2).applyMatrix4(matrix);
      const minX = Math.floor(Math.min(a.x, b.x, c.x) / CELL_METRES), maxX = Math.floor(Math.max(a.x, b.x, c.x) / CELL_METRES);
      const minZ = Math.floor(Math.min(a.z, b.z, c.z) / CELL_METRES), maxZ = Math.floor(Math.max(a.z, b.z, c.z) / CELL_METRES);
      if ((maxX - minX + 1) * (maxZ - minZ + 1) > MAXIMUM_TRIANGLE_CELLS) largeTriangles.push(offset);
      else for (let x = minX; x <= maxX; x++) for (let z = minZ; z <= maxZ; z++) {
        const key = cellKey(x, z);
        if (!cells.has(key)) cells.set(key, []);
        cells.get(key).push(offset);
      }
    }
    let indexBytes = 0;
    for (const [key, offsets] of cells) { const compact = Uint32Array.from(offsets); cells.set(key, compact); indexBytes += compact.byteLength; }
    const large = Uint32Array.from(largeTriangles); indexBytes += large.byteLength;
    counters.builds++; counters.buildMilliseconds += performance.now() - started;
    return { geometry, position, index, positionVersion: position.version ?? position.data?.version, indexVersion: index?.version, start, count: geometry.drawRange.count, matrix, cells, large, indexBytes, triangles: (end - start) / 3 };
  }

  function setModels(models) {
    const present = new Set();
    let changed = false;
    for (const model of models) {
      model.updateWorldMatrix(true, true);
      model.traverseVisible(mesh => {
        if (!mesh.isMesh) return;
        present.add(mesh);
        const previous = records.get(mesh), geometry = mesh.geometry, position = geometry.getAttribute('position');
        if (!previous || previous.geometry !== geometry || previous.index !== geometry.index || previous.position !== position || previous.positionVersion !== (position.version ?? position.data?.version) || previous.indexVersion !== geometry.index?.version || previous.start !== geometry.drawRange.start || previous.count !== geometry.drawRange.count || !previous.matrix.equals(mesh.matrixWorld)) {
          records.set(mesh, build(mesh)); changed = true;
        }
      });
    }
    for (const mesh of records.keys()) if (!present.has(mesh)) { records.delete(mesh); changed = true; }
    return changed;
  }

  function heightAt(x, z, minimumHeight, maximumHeight) {
    counters.queries++;
    ray.origin.set(x, maximumHeight, z);
    const key = cellKey(Math.floor(x / CELL_METRES), Math.floor(z / CELL_METRES));
    let highest = null;
    for (const record of records.values()) {
      const { position, index, matrix } = record;
      for (const offsets of [record.cells.get(key), record.large]) {
        if (!offsets) continue;
        for (const offset of offsets) {
          counters.testedTriangles++;
          a.fromBufferAttribute(position, index ? index.getX(offset) : offset).applyMatrix4(matrix);
          b.fromBufferAttribute(position, index ? index.getX(offset + 1) : offset + 1).applyMatrix4(matrix);
          c.fromBufferAttribute(position, index ? index.getX(offset + 2) : offset + 2).applyMatrix4(matrix);
          normal.subVectors(b, a).cross(edge.subVectors(c, a));
          if (normal.y * normal.y <= normal.lengthSq() * 0.09) continue;
          if (ray.intersectTriangle(a, b, c, false, hit) && hit.y > minimumHeight && (highest === null || hit.y > highest)) highest = hit.y;
        }
      }
    }
    return highest;
  }

  function nearestHeightAt(x, z, minimumHeight, maximumHeight, maximumDistance) {
    let nearestDistanceSquared = maximumDistance * maximumDistance, nearestHeight = null;
    const keys = [];
    for (let cellX = Math.floor((x - maximumDistance) / CELL_METRES); cellX <= Math.floor((x + maximumDistance) / CELL_METRES); cellX++) {
      for (let cellZ = Math.floor((z - maximumDistance) / CELL_METRES); cellZ <= Math.floor((z + maximumDistance) / CELL_METRES); cellZ++) keys.push(cellKey(cellX, cellZ));
    }
    for (const { position, index, matrix, cells, large } of records.values()) {
      const visited = new Set();
      for (const offsets of [...keys.map(key => cells.get(key)), large]) {
        if (!offsets) continue;
        for (const offset of offsets) {
          if (visited.has(offset)) continue;
          visited.add(offset);
          a.fromBufferAttribute(position, index ? index.getX(offset) : offset).applyMatrix4(matrix);
          b.fromBufferAttribute(position, index ? index.getX(offset + 1) : offset + 1).applyMatrix4(matrix);
          c.fromBufferAttribute(position, index ? index.getX(offset + 2) : offset + 2).applyMatrix4(matrix);
          normal.subVectors(b, a).cross(edge.subVectors(c, a));
          if (normal.y * normal.y <= normal.lengthSq() * 0.09) continue;
          for (const [start, end] of [[a, b], [b, c], [c, a]]) {
            const dx = end.x - start.x, dz = end.z - start.z, lengthSquared = dx * dx + dz * dz;
            const fraction = lengthSquared ? Math.max(0, Math.min(1, ((x - start.x) * dx + (z - start.z) * dz) / lengthSquared)) : 0;
            const height = start.y + (end.y - start.y) * fraction;
            const distanceSquared = (start.x + dx * fraction - x) ** 2 + (start.z + dz * fraction - z) ** 2;
            if (height > minimumHeight && height < maximumHeight && distanceSquared <= nearestDistanceSquared) {
              nearestDistanceSquared = distanceSquared; nearestHeight = height;
            }
          }
        }
      }
    }
    return nearestHeight;
  }

  return {
    setModels, heightAt, nearestHeightAt,
    diagnostics: () => ({ ...counters, meshes: records.size, triangles: [...records.values()].reduce((sum, record) => sum + record.triangles, 0), indexBytes: [...records.values()].reduce((sum, record) => sum + record.indexBytes, 0) }),
    dispose() { records.clear(); },
  };
}
