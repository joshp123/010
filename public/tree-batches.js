import * as THREE from 'three';

// Batch only byte-equivalent render geometry. Original tile meshes, metadata and
// instance transforms remain owned by the tile loader and object-detail module.
function geometryKey(geometry) {
  let hash = 2166136261;
  const numberBytes = new DataView(new ArrayBuffer(8));
  const attributes = [...Object.entries(geometry.attributes).sort(([a], [b]) => a.localeCompare(b)), ['index', geometry.index]].filter(([, attribute]) => attribute);
  const layout = attributes.map(([name, attribute]) => `${name}:${attribute.count}:${attribute.itemSize}:${attribute.normalized}:${attribute.array.constructor.name}`).join('|');
  for (const [, attribute] of attributes) for (let index = 0; index < attribute.count; index++) for (let component = 0; component < attribute.itemSize; component++) {
    numberBytes.setFloat64(0, attribute.getComponent(index, component));
    for (let byte = 0; byte < 8; byte++) hash = Math.imul(hash ^ numberBytes.getUint8(byte), 16777619);
  }
  return `${layout}:${geometry.drawRange.start}:${geometry.drawRange.count}:${JSON.stringify(geometry.groups)}:${hash >>> 0}`;
}

function sameGeometry(first, second) {
  for (const name of [...Object.keys(first.attributes), 'index']) {
    const a = name === 'index' ? first.index : first.attributes[name], b = name === 'index' ? second.index : second.attributes[name];
    if (!a || !b) { if (a !== b) return false; continue; }
    for (let index = 0; index < a.count; index++) for (let component = 0; component < a.itemSize; component++) {
      if (!Object.is(a.getComponent(index, component), b.getComponent(index, component))) return false;
    }
  }
  return true;
}

export function createTreeBatches(scene) {
  const models = new Map(), groups = new Map(), geometryGroups = new WeakMap();
  const instanceMatrix = new THREE.Matrix4(), worldMatrix = new THREE.Matrix4();
  let lastUpdate = { updateMilliseconds: 0, visibleSourceMeshes: 0, submittedInstances: 0, activeBatches: 0 };

  function addModel(model) {
    if (models.has(model)) return;
    const records = [];
    model.traverse(mesh => {
      if (!mesh.isInstancedMesh || mesh.instanceColor || mesh.morphTexture || Array.isArray(mesh.material) || Object.values(mesh.geometry.attributes).some(attribute => attribute.isInstancedBufferAttribute)) return;
      records.push({ mesh, sourceVisible: mesh.visible, capacity: mesh.instanceMatrix.count, groups: new Set() });
    });
    models.set(model, records);
  }

  function groupFor(record) {
    const { mesh } = record;
    if (record.currentGeometry === mesh.geometry) return record.currentGroup;
    let candidates = geometryGroups.get(mesh.geometry);
    if (!candidates) {
      const key = geometryKey(mesh.geometry);
      candidates = groups.get(key) || [];
      if (!groups.has(key)) groups.set(key, candidates);
      geometryGroups.set(mesh.geometry, candidates);
    }
    let group = candidates.find(candidate => candidate.material === mesh.material && candidate.customDepthMaterial === mesh.customDepthMaterial && candidate.castShadow === mesh.castShadow && candidate.receiveShadow === mesh.receiveShadow && sameGeometry(candidate.geometry, mesh.geometry));
    if (!group) {
      group = { geometry: mesh.geometry.clone(), material: mesh.material, customDepthMaterial: mesh.customDepthMaterial, castShadow: mesh.castShadow, receiveShadow: mesh.receiveShadow, records: new Set(), capacity: 0, mesh: null, count: 0, ranges: [], inputs: [] };
      candidates.push(group);
    }
    if (!record.groups.has(group)) { record.groups.add(group); group.records.add(record); group.capacity += record.capacity; }
    record.currentGeometry = mesh.geometry; record.currentGroup = group;
    return group;
  }

  function removeModel(model) {
    for (const record of models.get(model) || []) {
      record.mesh.visible = record.sourceVisible;
      for (const group of record.groups) {
        group.records.delete(record); group.capacity -= record.capacity;
        if (group.records.size) continue;
        if (group.mesh) { scene.remove(group.mesh); group.mesh.dispose(); }
        group.geometry.dispose();
        for (const candidates of groups.values()) {
          const index = candidates.indexOf(group);
          if (index !== -1) candidates.splice(index, 1);
        }
      }
    }
    models.delete(model);
  }

  function update(visibleModels) {
    const started = performance.now();
    for (const candidates of groups.values()) for (const group of candidates) { group.count = 0; group.ranges.length = 0; group.inputs.length = 0; }
    let visibleSourceMeshes = 0, submittedInstances = 0;
    for (const [model, records] of models) for (const record of records) {
      const { mesh } = record;
      let visible = visibleModels.has(model) && record.sourceVisible;
      for (let parent = mesh.parent; visible && parent; parent = parent.parent) visible = parent.visible;
      // Cached tile models can be detached; the loader's selected set is authoritative.
      mesh.visible = false;
      if (!visible || !mesh.count) continue;
      const group = groupFor(record);
      group.inputs.push(mesh);
      visibleSourceMeshes++; submittedInstances += mesh.count;
    }
    let activeBatches = 0;
    for (const candidates of groups.values()) for (const group of candidates) {
      if (!group.inputs.length) { if (group.mesh) { group.mesh.count = 0; group.mesh.visible = false; } continue; }
      if (!group.mesh || group.mesh.instanceMatrix.count < group.capacity) {
        if (group.mesh) { scene.remove(group.mesh); group.mesh.dispose(); }
        group.mesh = new THREE.InstancedMesh(group.geometry, group.material, group.capacity);
        group.mesh.name = 'Source tree prototype batch';
        group.mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
        group.mesh.customDepthMaterial = group.customDepthMaterial;
        group.mesh.castShadow = group.castShadow; group.mesh.receiveShadow = group.receiveShadow;
        // object-detail has already culled against the union of render cameras.
        group.mesh.frustumCulled = false;
        scene.add(group.mesh);
      }
      for (const mesh of group.inputs) {
        const start = group.count;
        for (let index = 0; index < mesh.count; index++) {
          mesh.getMatrixAt(index, instanceMatrix);
          worldMatrix.multiplyMatrices(mesh.matrixWorld, instanceMatrix);
          group.mesh.setMatrixAt(group.count++, worldMatrix);
        }
        group.ranges.push({ start, count: mesh.count, sourceMesh: mesh, sourceInstanceIndices: mesh.userData.objectDetailSourceInstanceIndices || null });
      }
      group.mesh.count = group.count; group.mesh.visible = group.count > 0;
      group.mesh.userData.sourceInstanceRanges = group.ranges;
      if (group.count) { group.mesh.instanceMatrix.needsUpdate = true; activeBatches++; }
    }
    lastUpdate = { updateMilliseconds: performance.now() - started, visibleSourceMeshes, submittedInstances, activeBatches };
    return lastUpdate;
  }

  function diagnostics() {
    let prototypeCopies = 0, instanceBufferBytes = 0, geometryBytes = 0;
    for (const candidates of groups.values()) for (const group of candidates) {
      prototypeCopies++;
      instanceBufferBytes += group.mesh?.instanceMatrix.array.byteLength || 0;
      geometryBytes += Object.values(group.geometry.attributes).reduce((sum, attribute) => sum + attribute.array.byteLength, group.geometry.index?.array.byteLength || 0);
    }
    return { models: models.size, prototypeCopies, instanceBufferBytes, geometryBytes, ...lastUpdate };
  }

  function dispose() { for (const model of [...models.keys()]) removeModel(model); groups.clear(); }
  return { addModel, removeModel, update, diagnostics, dispose };
}
