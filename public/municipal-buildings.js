// Written by AI on 2026-10-24 by model GPT-6 Astra.
import * as THREE from 'three';
import { normalizedBagId } from './building-appearance.js';
import { UNLOADED, LOADED } from './vendor/3d-tiles-renderer/build/index.core.js';

function batchTableFor(mesh) {
  for (let node = mesh; node; node = node.parent) if (node.batchTable) return node.batchTable;
  return null;
}

// Keep the source material batches intact. Exact BAG replacements change only
// triangle indices; atlas pixels, UVs, normals, node transforms and RTC stay put.
export function createMunicipalBuildingVisibility() {
  const models = new Map();
  let replaced = new Set();
  function apply(record) {
    const visibleIds = new Set();
    for (const entry of record.meshes) {
      if (!entry.bagIds.some(id => replaced.has(id))) {
        for (const id of entry.bagIds) visibleIds.add(id);
        entry.mesh.geometry.setIndex(entry.original.index || new THREE.BufferAttribute(entry.indices, 1));
        entry.mesh.geometry.clearGroups();
        for (const group of entry.original.groups) entry.mesh.geometry.addGroup(group.start, group.count, group.materialIndex);
        continue;
      }
      const keep = [], groups = entry.original.groups;
      entry.mesh.geometry.clearGroups();
      let groupStart = 0, groupMaterial = null;
      for (let triangle = 0; triangle < entry.identities.length; triangle++) {
        const id = entry.identities[triangle];
        if (id && replaced.has(id)) continue;
        if (id) visibleIds.add(id);
        if (groups.length) {
          const material = groups.find(group => triangle * 3 >= group.start && triangle * 3 < group.start + group.count)?.materialIndex ?? 0;
          if (groupMaterial !== material) {
            if (groupMaterial !== null) entry.mesh.geometry.addGroup(groupStart, keep.length - groupStart, groupMaterial);
            groupStart = keep.length; groupMaterial = material;
          }
        }
        keep.push(entry.indices[triangle * 3], entry.indices[triangle * 3 + 1], entry.indices[triangle * 3 + 2]);
      }
      if (groupMaterial !== null) entry.mesh.geometry.addGroup(groupStart, keep.length - groupStart, groupMaterial);
      entry.mesh.geometry.setIndex(new THREE.BufferAttribute(new entry.indices.constructor(keep), 1));
    }
    record.visibleIds = visibleIds;
  }
  return {
    addModel(model) {
      if (models.has(model)) return;
      const meshes = [];
      model.traverse(mesh => {
        if (!mesh.isMesh) return;
        const geometry = mesh.geometry, batchIds = geometry.getAttribute('_batchid'), table = batchTableFor(mesh);
        if (!batchIds || !table) return;
        // Preserve the tile renderer's original geometry for its disposal path.
        // Every owned clone shares the unchanged attributes/materials.
        const clone = new THREE.BufferGeometry();
        for (const [name, attribute] of Object.entries(geometry.attributes)) clone.setAttribute(name, attribute);
        clone.morphAttributes = geometry.morphAttributes; clone.morphTargetsRelative = geometry.morphTargetsRelative;
        clone.boundingBox = geometry.boundingBox?.clone() || null; clone.boundingSphere = geometry.boundingSphere?.clone() || null;
        mesh.geometry = clone;
        const count = geometry.index?.count ?? geometry.getAttribute('position').count;
        const indices = geometry.index ? geometry.index.array.slice() : Uint32Array.from({ length: count }, (_, index) => index);
        const identities = [], lookup = new Map();
        for (let offset = 0; offset < count; offset += 3) {
          const batch = batchIds.getX(indices[offset]);
          if (!lookup.has(batch)) {
            const data = table.getDataFromId(batch) || {}, attributes = data.attributes || {};
            lookup.set(batch, normalizedBagId(attributes.gebouwnummer || attributes.GEBOUWNUMMER || attributes['gml:id'] || data.id));
          }
          identities.push(lookup.get(batch));
        }
        meshes.push({ mesh, original: geometry, indices, identities, bagIds: [...new Set(identities.filter(Boolean))] });
      });
      const record = { meshes, visibleIds: new Set() }; models.set(model, record); apply(record);
    },
    removeModel(model) {
      const record = models.get(model);
      if (!record) return;
      for (const entry of record.meshes) { entry.mesh.geometry.dispose(); entry.mesh.geometry = entry.original; }
      models.delete(model);
    },
    setSuppressedBags(ids) {
      const next = new Set([...ids].map(normalizedBagId).filter(Boolean));
      if (next.size === replaced.size && [...next].every(id => replaced.has(id))) return false;
      replaced = next;
      for (const record of models.values()) apply(record);
      return true;
    },
    visibleBagIds(visibleModels) {
      const ids = new Set();
      for (const model of visibleModels) for (const id of models.get(model)?.visibleIds || []) ids.add(id);
      return ids;
    },
    diagnostics() {
      return { loadedModels: models.size, sourceBuildings: new Set([...models.values()].flatMap(record => record.meshes.flatMap(entry => entry.bagIds))).size, replacedBuildings: replaced.size };
    },
  };
}

// The municipal source already supplies real coarser models (levels15–17).
// Enter a neighbourhood through its first available source model, then refine
// that same hierarchy. Leaf-first loading otherwise requests scores of models
// before their ordinary streets have any source appearance at all.
export function configureMunicipalBuildingStreaming(tiles, municipalCache) {
  if (municipalCache) {
    municipalCache.maxBytesSize = 128 * 1024 * 1024;
    municipalCache.minBytesSize = municipalCache.maxBytesSize * 0.8;
    municipalCache.unloadPriorityCallback = tiles.lruCache.unloadPriorityCallback;
    tiles.lruCache = municipalCache;
  }
  const calculateViewError = tiles.calculateTileViewError.bind(tiles);
  tiles.loadAncestors = false;
  tiles.loadSiblings = false;
  tiles.calculateTileViewError = (tile, result) => {
    calculateViewError(tile, result);
    // An unloaded renderable parent is the next useful source view. Once it is
    // resident, its original screen-space error selects finer source children.
    // The renderer keeps the visible parent until those children are ready.
    if (tile.internal.hasRenderableContent && tile.internal.loadingState >= UNLOADED && tile.internal.loadingState < LOADED) {
      result.error = Math.min(result.error, tiles.errorTarget);
    }
  };
  return municipalCache;
}
