import * as THREE from 'three';

// Match identity, never vertex order, between municipal model editions.
export function normalizedBagId(value) {
  const match = String(value ?? '').match(/(?:^|\D)(\d{16})(?:\D|$)/);
  return match?.[1] ?? null;
}

function batchTableFor(mesh) {
  for (let node = mesh; node; node = node.parent) if (node.batchTable) return node.batchTable;
  return null;
}

export function createBuildingAppearanceReconciliation(batches) {
  const models = new Map();
  let replaced = new Set();
  let hiddenTriangles = 0;
  function apply(entry) {
    for (const record of entry.meshes) {
      const { mesh, indices, triangleIds } = record;
      if (!triangleIds.some(id => replaced.has(id))) {
        mesh.geometry.setIndex(new THREE.BufferAttribute(indices.slice(), 1));
        continue;
      }
      const keep = [];
      for (let t = 0; t < triangleIds.length; t++) {
        if (!replaced.has(triangleIds[t])) keep.push(indices[t * 3], indices[t * 3 + 1], indices[t * 3 + 2]);
      }
      mesh.geometry.setIndex(new THREE.BufferAttribute(new indices.constructor(keep), 1));
    }
  }
  return {
    addModel(model) {
      const meshes = [];
      model.traverse(mesh => {
        if (!mesh.isMesh) return;
        const geometry = mesh.geometry, ids = geometry.getAttribute('_batchid'), table = batchTableFor(mesh);
        if (!ids || !table) return;
        const count = geometry.index?.count ?? geometry.getAttribute('position').count;
        const indices = geometry.index ? geometry.index.array.slice() : Uint32Array.from({ length: count }, (_, i) => i);
        const lookup = new Map();
        const triangleIds = [];
        for (let i = 0; i < count; i += 3) {
          const id = ids.getX(indices[i]);
          if (!lookup.has(id)) {
            let attributes = {};
            try { attributes = table.getDataFromId(id)?.attributes || {}; } catch {}
            lookup.set(id, normalizedBagId(attributes.GEBOUWNUMMER || attributes.gebouwnummer || attributes['gml:id']));
          }
          triangleIds.push(lookup.get(id));
        }
        meshes.push({ mesh, indices, triangleIds });
      });
      const entry = { model, meshes }; models.set(model, entry); apply(entry);
    },
    removeModel(model) { models.delete(model); },
    setVisibleModels(visibleModels) {
      const next = new Set();
      for (const model of visibleModels) model.traverseVisible(mesh => {
        const id = normalizedBagId(mesh.userData.bagId);
        if (mesh.isMesh && id) next.add(id);
      });
      if (next.size === replaced.size && [...next].every(id => replaced.has(id))) return false;
      replaced = next; hiddenTriangles = 0;
      for (const entry of models.values()) {
        batches.removeModel(entry.model);
        apply(entry);
        hiddenTriangles += entry.meshes.reduce((n, record) => n + record.triangleIds.filter(id => replaced.has(id)).length, 0);
        batches.addModel(entry.model);
      }
      return true;
    },
    diagnostics() { return { visibleSourceBuildings: replaced.size, hiddenNewerTriangles: hiddenTriangles, preparedScope: 'bounded source-appearance pilot; not municipality-wide' }; },
  };
}

// The offline atlas is the replaceable interpretation. Keep its measured UVs,
// roof/facade distinctions and colours; no generic window grid or random paint.
export function prepareAppearanceModel(model, { applyLighting, applyCutaway }) {
  const seen = new Set();
  model.traverse(mesh => {
    if (!mesh.isMesh) return;
    mesh.castShadow = mesh.receiveShadow = true;
    for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
      if (seen.has(material)) continue;
      seen.add(material);
      material.roughness = 1; material.metalness = 0;
      material.flatShading = true;
      if (material.map) {
        material.map.magFilter = THREE.NearestFilter;
        material.map.minFilter = THREE.LinearMipmapLinearFilter;
        material.map.colorSpace = THREE.SRGBColorSpace;
        material.map.needsUpdate = true;
      }
      applyLighting(material); applyCutaway(material);
      material.needsUpdate = true;
    }
  });
}
