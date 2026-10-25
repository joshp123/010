// Written by AI on 2026-10-24 by model GPT-6.
import * as THREE from 'three';

const GRID_DIVISIONS = [2, 4, 8, 16];
const triangleCount = geometry => (geometry.index?.count ?? geometry.getAttribute('position').count) / 3;
const geometryBytes = geometry => Object.values(geometry.attributes).reduce((sum, attribute) => sum + attribute.array.byteLength, geometry.index?.array.byteLength || 0);

// Collapse only vertices in the same spatial cell and with the same feature and
// colour. Each representative is an original source vertex. Every retained
// triangle therefore has a measured displacement bound; no replacement shape is
// invented. Per-axis grids retain narrow shafts rather than flattening them.
function clusterGeometry(source, divisions) {
  const position = source.getAttribute('position');
  source.computeBoundingBox();
  const minimum = source.boundingBox.min, size = source.boundingBox.getSize(new THREE.Vector3());
  const feature = source.getAttribute('_batchid'), color = source.getAttribute('color');
  const representatives = [], vertexRemap = new Uint32Array(position.count), cells = new Map(), centreDistances = [];
  let maximumDisplacement = 0;
  for (let vertex = 0; vertex < position.count; vertex++) {
    const coordinates = [position.getX(vertex), position.getY(vertex), position.getZ(vertex)];
    const cell = coordinates.map((value, axis) => {
      const lower = minimum.getComponent(axis), extent = size.getComponent(axis);
      return extent ? Math.round((value - lower) / extent * divisions) : 0;
    });
    if (feature) cell.push(feature.getX(vertex));
    if (color) for (let component = 0; component < color.itemSize; component++) cell.push(color.getComponent(vertex, component));
    const key = cell.join(',');
    let target = cells.get(key);
    const distanceToCentre = coordinates.reduce((sum, value, axis) => sum + (value - minimum.getComponent(axis) - cell[axis] * size.getComponent(axis) / divisions) ** 2, 0);
    if (target === undefined) { target = representatives.length; representatives.push(vertex); centreDistances.push(distanceToCentre); cells.set(key, target); }
    else if (distanceToCentre < centreDistances[target]) { representatives[target] = vertex; centreDistances[target] = distanceToCentre; }
    vertexRemap[vertex] = target;
  }
  for (let vertex = 0; vertex < position.count; vertex++) {
    const representative = representatives[vertexRemap[vertex]];
    maximumDisplacement = Math.max(maximumDisplacement, Math.hypot(position.getX(vertex) - position.getX(representative), position.getY(vertex) - position.getY(representative), position.getZ(vertex) - position.getZ(representative)));
  }
  const indices = [], groups = [], seenTriangles = new Set();
  const sourceGroups = source.groups.length ? source.groups : [{ start: 0, count: source.index?.count ?? position.count, materialIndex: 0 }];
  for (const group of sourceGroups) {
    const start = indices.length;
    for (let offset = group.start; offset < group.start + group.count; offset += 3) {
      const vertices = [0, 1, 2].map(corner => vertexRemap[source.index ? source.index.getX(offset + corner) : offset + corner]);
      if (vertices[0] === vertices[1] || vertices[1] === vertices[2] || vertices[0] === vertices[2]) continue;
      // Preserve winding, including double-sided source faces.
      const smallest = vertices.indexOf(Math.min(...vertices));
      const key = `${group.materialIndex}:${vertices[smallest]},${vertices[(smallest + 1) % 3]},${vertices[(smallest + 2) % 3]}`;
      if (seenTriangles.has(key)) continue;
      seenTriangles.add(key); indices.push(...vertices);
    }
    if (indices.length > start) groups.push({ start, count: indices.length - start, materialIndex: group.materialIndex });
  }
  if (!indices.length || indices.length >= (source.index?.count ?? position.count) * 0.9) return null;
  const geometry = new THREE.BufferGeometry();
  for (const [name, attribute] of Object.entries(source.attributes)) {
    if (name === 'normal') continue;
    const values = new attribute.array.constructor(representatives.length * attribute.itemSize);
    const result = new THREE.BufferAttribute(values, attribute.itemSize, attribute.normalized);
    for (let vertex = 0; vertex < representatives.length; vertex++) {
      for (let component = 0; component < attribute.itemSize; component++) result.setComponent(vertex, component, attribute.getComponent(representatives[vertex], component));
    }
    geometry.setAttribute(name, result);
  }
  geometry.setIndex(indices);
  if (source.getAttribute('normal')) geometry.computeVertexNormals();
  for (const group of groups) geometry.addGroup(group.start, group.count, group.materialIndex);
  geometry.userData = { ...source.userData, screenSpaceApproximation: { divisions, maximumDisplacement } };
  // Source bounds remain conservative for culling and tile/lamp metadata.
  geometry.boundingBox = source.boundingBox.clone();
  if (!source.boundingSphere) source.computeBoundingSphere();
  geometry.boundingSphere = source.boundingSphere.clone();
  return { geometry, maximumDisplacement };
}

export function createObjectDetail({ maximumPixelError = 1, buildBudgetMilliseconds = 4 } = {}) {
  const models = new Map(), sources = new Map(), instanceMatrix = new THREE.Matrix4();
  let lastUpdate = { changed: false, pending: false, buildMilliseconds: 0 };
  function addModel(model) {
    if (models.has(model)) return;
    const meshes = [];
    model.traverse(mesh => {
      if (!mesh.isMesh || mesh.isSkinnedMesh || mesh.geometry.morphAttributes.position || !mesh.geometry.getAttribute('position')) return;
      const source = mesh.geometry;
      let record = sources.get(source);
      if (!record) { record = { source, references: 0, levels: [], nextGrid: 0 }; sources.set(source, record); }
      record.references++;
      let instanceScale = 1, instances = null;
      if (mesh.isInstancedMesh) {
        instanceScale = 0;
        if (!source.boundingSphere) source.computeBoundingSphere();
        if (!mesh.boundingSphere) mesh.computeBoundingSphere();
        const bounds = new Float64Array(mesh.count * 4), sphere = new THREE.Sphere();
        for (let index = 0; index < mesh.count; index++) {
          mesh.getMatrixAt(index, instanceMatrix); instanceScale = Math.max(instanceScale, instanceMatrix.getMaxScaleOnAxis());
          sphere.copy(source.boundingSphere).applyMatrix4(instanceMatrix);
          bounds.set([sphere.center.x, sphere.center.y, sphere.center.z, sphere.radius], index * 4);
        }
        if (!Object.values(source.attributes).some(attribute => attribute.isInstancedBufferAttribute)) instances = {
          count: mesh.count, matrices: mesh.instanceMatrix.array.slice(), colors: mesh.instanceColor?.array.slice(), bounds, sourceIndices: new Uint32Array(mesh.count), compacted: false,
        };
      }
      meshes.push({ mesh, record, instanceScale, instances });
    });
    models.set(model, meshes);
  }
  function removeModel(model) {
    for (const { mesh, record, instances } of models.get(model) || []) {
      restoreInstances(mesh, instances);
      mesh.geometry = record.source;
      if (--record.references === 0) {
        for (const level of record.levels) level.geometry.dispose();
        sources.delete(record.source);
      }
    }
    models.delete(model);
  }
  function restoreInstances(mesh, instances) {
    if (!instances?.compacted) return;
    mesh.instanceMatrix.array.set(instances.matrices); mesh.instanceMatrix.needsUpdate = true;
    if (instances.colors) { mesh.instanceColor.array.set(instances.colors); mesh.instanceColor.needsUpdate = true; }
    mesh.count = instances.count; instances.compacted = false;
    delete mesh.userData.objectDetailSourceInstanceIndices;
  }
  function update(camera, viewportHeight, { fullDetail = false, cullingCameras = [] } = {}) {
    if (!camera.isOrthographicCamera) fullDetail = true;
    const pixelsPerWorldUnit = viewportHeight * camera.zoom / (camera.top - camera.bottom);
    // Supply every render camera (main, reflection and shadow) to enable exact
    // instance culling. Omitting the list keeps every source instance.
    const frustums = fullDetail ? [] : cullingCameras.map(view => new THREE.Frustum().setFromProjectionMatrix(new THREE.Matrix4().multiplyMatrices(view.projectionMatrix, view.matrixWorldInverse)));
    const instanceSphere = new THREE.Sphere();
    const started = performance.now();
    let changed = false, pending = false, buildMilliseconds = 0;
    for (const meshes of models.values()) for (const { mesh, record, instanceScale, instances } of meshes) {
      if (instances && frustums.length) {
        let visibleCount = 0;
        for (let index = 0; index < instances.count; index++) {
          instanceSphere.center.fromArray(instances.bounds, index * 4); instanceSphere.radius = instances.bounds[index * 4 + 3];
          instanceSphere.applyMatrix4(mesh.matrixWorld);
          if (!frustums.some(frustum => frustum.intersectsSphere(instanceSphere))) continue;
          mesh.instanceMatrix.array.set(instances.matrices.subarray(index * 16, index * 16 + 16), visibleCount * 16);
          if (instances.colors) mesh.instanceColor.array.set(instances.colors.subarray(index * 3, index * 3 + 3), visibleCount * 3);
          instances.sourceIndices[visibleCount] = index;
          visibleCount++;
        }
        changed ||= mesh.count !== visibleCount;
        mesh.count = visibleCount; instances.compacted = true; mesh.userData.objectDetailSourceInstanceIndices = instances.sourceIndices; mesh.instanceMatrix.needsUpdate = true;
        if (instances.colors) mesh.instanceColor.needsUpdate = true;
      } else { if (instances?.compacted) changed = true; restoreInstances(mesh, instances); }
      let geometry = record.source;
      if (!fullDetail && !record.source.userData.preserveTextureProjection) {
        const pixelsPerSourceUnit = pixelsPerWorldUnit * mesh.matrixWorld.getMaxScaleOnAxis() * instanceScale;
        const maximumSourceError = maximumPixelError / pixelsPerSourceUnit;
        // Do not spend CPU making approximations of already tiny prototypes.
        if (triangleCount(record.source) > 64 && record.nextGrid < GRID_DIVISIONS.length) {
          if (buildMilliseconds < buildBudgetMilliseconds) {
            const buildStarted = performance.now();
            const level = clusterGeometry(record.source, GRID_DIVISIONS[record.nextGrid++]);
            if (level) record.levels.push(level);
            buildMilliseconds += performance.now() - buildStarted;
          }
          if (record.nextGrid < GRID_DIVISIONS.length) pending = true;
        }
        for (const level of record.levels) {
          if (level.maximumDisplacement <= maximumSourceError && triangleCount(level.geometry) < triangleCount(geometry)) geometry = level.geometry;
        }
      }
      if (mesh.geometry !== geometry) { mesh.geometry = geometry; changed = true; }
    }
    lastUpdate = { changed, pending, buildMilliseconds, updateMilliseconds: performance.now() - started };
    return lastUpdate;
  }
  function diagnostics() {
    let originalTriangles = 0, renderedTriangles = 0, additionalGeometryBytes = 0, instanceSnapshotBytes = 0, approximatedMeshes = 0, originalInstances = 0, submittedInstances = 0;
    for (const meshes of models.values()) for (const { mesh, record, instances } of meshes) {
      const sourceCount = instances?.count ?? (mesh.isInstancedMesh ? mesh.count : 1), visibleCount = mesh.isInstancedMesh ? mesh.count : 1;
      originalInstances += sourceCount; submittedInstances += visibleCount;
      if (instances) instanceSnapshotBytes += instances.matrices.byteLength + instances.bounds.byteLength + instances.sourceIndices.byteLength + (instances.colors?.byteLength || 0);
      originalTriangles += triangleCount(record.source) * sourceCount;
      renderedTriangles += triangleCount(mesh.geometry) * visibleCount;
      if (mesh.geometry !== record.source) approximatedMeshes++;
    }
    for (const record of sources.values()) for (const level of record.levels) additionalGeometryBytes += geometryBytes(level.geometry);
    return { models: models.size, sourceGeometries: sources.size, originalTriangles, renderedTriangles, approximatedMeshes, additionalGeometryBytes, instanceSnapshotBytes, originalInstances, submittedInstances, maximumPixelError, ...lastUpdate };
  }
  function dispose() { for (const model of [...models.keys()]) removeModel(model); }
  return { addModel, removeModel, update, diagnostics, dispose };
}
