import * as THREE from 'three';

function attributeLayout(geometry) {
  return Object.entries(geometry.attributes).sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([name, attribute]) => [name, attribute.itemSize, attribute.normalized, attribute.isInterleavedBufferAttribute ? attribute.data.array.constructor.name : attribute.array.constructor.name].join(':')).join('|');
}

// Tile-local, reversible concatenation. Sibling transforms stay unchanged;
// source geometries share attribute views with the combined draw geometry.
export function createBuildingBatches() {
  const models = new Map(), mergedMeshes = new WeakMap();
  let enabled = true;

  function show(record, batched) {
    const { parent, merged, sources } = record;
    if (batched) {
      for (const source of sources) source.mesh.removeFromParent();
      parent.add(merged);
      // TilesGroup deliberately skips descendants while its own world matrix
      // is unchanged. A replacement draw added after tile activation therefore
      // cannot rely on the next scene traversal to inherit the tile transform.
      merged.updateWorldMatrix(true, false, true);
    } else {
      merged.removeFromParent();
      for (const source of sources) {
        parent.add(source.mesh);
        source.mesh.updateWorldMatrix(true, false, true);
      }
    }
  }

  function addModel(model) {
    if (models.has(model)) return;
    const started = performance.now(), groups = new Map(), records = [];
    model.traverse(mesh => {
      if (!mesh.isMesh || mesh.isInstancedMesh || mesh.isSkinnedMesh || !mesh.visible || mesh.children.length || Array.isArray(mesh.material)) return;
      const geometry = mesh.geometry;
      if (!geometry.getAttribute('position') || Object.keys(geometry.morphAttributes).length || geometry.groups.length > 1) return;
      const elementCount = geometry.index?.count ?? geometry.getAttribute('position').count;
      if (geometry.drawRange.start !== 0 || geometry.drawRange.count < elementCount) return;
      if (geometry.groups.length && (geometry.groups[0].start !== 0 || geometry.groups[0].count !== elementCount)) return;
      if (mesh.matrixAutoUpdate) mesh.updateMatrix();
      const key = [mesh.parent.id, mesh.material.id, mesh.customDepthMaterial?.id ?? '', mesh.matrix.elements.join(','), mesh.castShadow, mesh.receiveShadow, mesh.renderOrder, mesh.layers.mask, mesh.frustumCulled, attributeLayout(geometry)].join(';');
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(mesh);
    });
    for (const meshes of groups.values()) {
      if (meshes.length < 2) continue;
      const first = meshes[0], geometry = new THREE.BufferGeometry();
      const vertexCount = meshes.reduce((sum, mesh) => sum + mesh.geometry.getAttribute('position').count, 0);
      const indexCount = meshes.reduce((sum, mesh) => sum + (mesh.geometry.index?.count ?? mesh.geometry.getAttribute('position').count), 0);
      const indices = vertexCount > 65535 ? new Uint32Array(indexCount) : new Uint16Array(indexCount);
      const sources = [];
      let vertexOffset = 0, indexOffset = 0, retainedSourceIndexBytes = 0;
      for (const [name, firstAttribute] of Object.entries(first.geometry.attributes)) {
        const ArrayType = firstAttribute.isInterleavedBufferAttribute ? firstAttribute.data.array.constructor : firstAttribute.array.constructor;
        geometry.setAttribute(name, new THREE.BufferAttribute(new ArrayType(vertexCount * firstAttribute.itemSize), firstAttribute.itemSize, firstAttribute.normalized));
      }
      for (const mesh of meshes) {
        const sourceGeometry = mesh.geometry, count = sourceGeometry.getAttribute('position').count;
        const sourceIndex = sourceGeometry.index;
        const countIndices = sourceIndex?.count ?? count;
        const indexCopy = sourceIndex ? new sourceIndex.array.constructor(sourceIndex.array) : null;
        retainedSourceIndexBytes += indexCopy?.byteLength || 0;
        for (let index = 0; index < countIndices; index++) indices[indexOffset + index] = (indexCopy ? indexCopy[index] : index) + vertexOffset;
        // Release any previous GPU buffers before replacing their attribute views.
        sourceGeometry.dispose();
        for (const [name, attribute] of Object.entries(sourceGeometry.attributes)) {
          const target = geometry.getAttribute(name), components = attribute.itemSize;
          if (attribute.isInterleavedBufferAttribute) {
            const array = attribute.data.array, stride = attribute.data.stride;
            for (let vertex = 0; vertex < count; vertex++) for (let component = 0; component < components; component++) target.array[(vertexOffset + vertex) * components + component] = array[vertex * stride + attribute.offset + component];
          } else target.array.set(attribute.array, vertexOffset * components);
          const view = target.array.subarray(vertexOffset * components, (vertexOffset + count) * components);
          sourceGeometry.setAttribute(name, new THREE.BufferAttribute(view, components, target.normalized));
        }
        // A copied small source index releases the original GLB backing buffer;
        // source position/normal/colour/feature bytes now live only once.
        if (indexCopy) sourceGeometry.setIndex(new THREE.BufferAttribute(indexCopy, 1));
        sources.push({ mesh, firstTriangle: indexOffset / 3, triangleCount: countIndices / 3 });
        vertexOffset += count; indexOffset += countIndices;
      }
      geometry.setIndex(new THREE.BufferAttribute(indices, 1));
      geometry.computeBoundingBox(); geometry.computeBoundingSphere();
      const merged = new THREE.Mesh(geometry, first.material);
      merged.name = 'Native building primitives · combined draw';
      merged.matrixAutoUpdate = false; merged.matrix.copy(first.matrix);
      merged.customDepthMaterial = first.customDepthMaterial;
      merged.castShadow = first.castShadow; merged.receiveShadow = first.receiveShadow;
      merged.renderOrder = first.renderOrder; merged.layers.mask = first.layers.mask; merged.frustumCulled = first.frustumCulled;
      merged.userData = { ...first.userData, sourcePrimitiveCount: meshes.length };
      const attributeBytes = Object.values(geometry.attributes).reduce((sum, attribute) => sum + attribute.array.byteLength, 0);
      const record = { model, parent: first.parent, merged, sources, vertexCount, triangleCount: indexCount / 3, additionalIndexBytes: indices.byteLength, attributeBytes, retainedSourceIndexBytes };
      mergedMeshes.set(merged, record); records.push(record);
    }
    models.set(model, { records, buildMilliseconds: performance.now() - started });
    for (const record of records) show(record, enabled);
  }

  function removeModel(model) {
    const entry = models.get(model);
    if (!entry) return;
    for (const record of entry.records) { show(record, false); record.merged.geometry.dispose(); mergedMeshes.delete(record.merged); }
    models.delete(model);
  }

  function sourceForFace(mesh, faceIndex) {
    const record = mergedMeshes.get(mesh);
    if (!record) return null;
    const source = record.sources.find(source => faceIndex >= source.firstTriangle && faceIndex < source.firstTriangle + source.triangleCount);
    return source ? { mesh: source.mesh, faceIndex: faceIndex - source.firstTriangle, model: record.model } : null;
  }

  return {
    addModel, removeModel, sourceForFace,
    setEnabled(value) { if (enabled !== value) { enabled = value; for (const entry of models.values()) for (const record of entry.records) show(record, enabled); } },
    diagnostics() {
      const entries = [...models.values()], records = entries.flatMap(entry => entry.records);
      const sourceDraws = records.reduce((sum, record) => sum + record.sources.length, 0);
      return { enabled, models: models.size, groups: records.length, sourceDraws, combinedDraws: records.length, savedDraws: enabled ? sourceDraws - records.length : 0, triangles: records.reduce((sum, record) => sum + record.triangleCount, 0), combinedAttributeBytes: records.reduce((sum, record) => sum + record.attributeBytes, 0), conservativeAdditionalBytes: records.reduce((sum, record) => sum + record.attributeBytes + record.additionalIndexBytes + record.retainedSourceIndexBytes, 0), additionalIndexBytes: records.reduce((sum, record) => sum + record.additionalIndexBytes, 0), retainedSourceIndexBytes: records.reduce((sum, record) => sum + record.retainedSourceIndexBytes, 0), buildMilliseconds: entries.reduce((sum, entry) => sum + entry.buildMilliseconds, 0) };
    },
    dispose() { for (const model of [...models.keys()]) removeModel(model); },
  };
}
