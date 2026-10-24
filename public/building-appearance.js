import * as THREE from 'three';

// Match identity, never vertex order, between municipal model editions.
export function normalizedBagId(value) {
  const match = String(value ?? '').match(/(?:^|\D)(\d{16})(?:\D|$)/);
  return match?.[1] ?? null;
}

export function appearanceTextureDiagnostics(models) {
  const textures = new Set(), sources = new Map(), dimensions = {};
  for (const model of models) model?.traverseVisible(mesh => {
    if (!mesh.isMesh) return;
    for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
      for (const texture of Object.values(material)) {
        if (!texture?.isTexture || textures.has(texture)) continue;
        textures.add(texture);
        const source = texture.source;
        if (!sources.has(source)) sources.set(source, { width: texture.image?.width || 0, height: texture.image?.height || 0, mipmaps: false, variants: new Set() });
        const record = sources.get(source);
        record.mipmaps ||= texture.generateMipmaps;
        // Vendored WebGLTextures.getTextureCacheKey: UV offset/repeat/rotation
        // are uniforms, so KHR_texture_transform clones share image storage.
        record.variants.add([texture.wrapS, texture.wrapT, texture.wrapR || 0,
          texture.magFilter, texture.minFilter, texture.anisotropy, texture.internalFormat,
          texture.format, texture.type, texture.generateMipmaps, texture.premultiplyAlpha,
          texture.flipY, texture.unpackAlignment, texture.colorSpace].join());
      }
    }
  });
  let decodedRgbaBytes = 0, mipBytes = 0, sourceSamplerVariants = 0;
  for (const { width, height, mipmaps, variants } of sources.values()) {
    const key = `${width}x${height}`; dimensions[key] = (dimensions[key] || 0) + 1;
    decodedRgbaBytes += width * height * 4;
    sourceSamplerVariants += variants.size;
    let w = width, h = height;
    if (w && h) while (true) {
      mipBytes += w * h * 4;
      if (!mipmaps || (w === 1 && h === 1)) break;
      w = Math.max(1, Math.floor(w / 2)); h = Math.max(1, Math.floor(h / 2));
    }
  }
  return { count: textures.size, textureObjects: textures.size, uniqueImageSources: sources.size,
    sourceSamplerVariants, dimensions, decodedRgbaBytes, decodedRgbaBytesIncludingMips: mipBytes,
    memoryBasis: 'RGBA8 estimate per unique Texture.Source, not measured GPU allocation; sampler variants may need separate uploads' };

}

function batchTableFor(mesh) {
  for (let node = mesh; node; node = node.parent) if (node.batchTable) return node.batchTable;
  return null;
}

export function normalizedTankId(value) {
  return /^OST_\d+$/.test(String(value ?? '')) ? String(value) : null;
}

// An illustrated feature replaces only its exact, currently visible native
// appearance. Other native features remain useful source-backed city detail.
export function createAppearancePriorityReconciliation() {
  const originalVisibility = new WeakMap();
  return {
    update(nativeModels, illustratedModels) {
      const illustrated = new Set();
      for (const model of illustratedModels) model?.traverseVisible(mesh => {
        if (!mesh.isMesh) return;
        const id = normalizedTankId(mesh.userData.featureId);
        if (id) illustrated.add(id);
      });
      let changed = false;
      // Traverse hidden meshes too: a previously overridden feature must recover
      // when its illustrated tile unloads or ceases to be visible.
      for (const model of nativeModels) model?.traverse(mesh => {
        if (!mesh.isMesh) return;
        const id = normalizedTankId(mesh.userData.featureId);
        if (!id) return;
        if (!originalVisibility.has(mesh)) originalVisibility.set(mesh, mesh.visible);
        const visible = originalVisibility.get(mesh) && !illustrated.has(id);
        if (mesh.visible !== visible) { mesh.visible = visible; changed = true; }
      });
      return changed;
    },
  };
}

export function createTankAppearanceReconciliation() {
  return createBuildingAppearanceReconciliation(null, { tanks: true });
}

export function createBuildingAppearanceReconciliation(batches, { tanks = false } = {}) {
  const normalize = tanks ? normalizedTankId : normalizedBagId;
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
            let data = {};
            try { data = table.getDataFromId(id) || {}; } catch {}
            const attributes = data.attributes || {};
            lookup.set(id, tanks ? normalizedTankId(data.id) : normalizedBagId(attributes.GEBOUWNUMMER || attributes.gebouwnummer || attributes['gml:id']));
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
        const id = normalize(tanks ? mesh.userData.featureId : mesh.userData.bagId);
        if (mesh.isMesh && id) next.add(id);
      });
      if (next.size === replaced.size && [...next].every(id => replaced.has(id))) return false;
      replaced = next; hiddenTriangles = 0;
      for (const entry of models.values()) {
        batches?.removeModel(entry.model);
        apply(entry);
        hiddenTriangles += entry.meshes.reduce((n, record) => n + record.triangleIds.filter(id => replaced.has(id)).length, 0);
        batches?.addModel(entry.model);
      }
      return true;
    },
    diagnostics() {
      hiddenTriangles = [...models.values()].reduce((sum, entry) => sum + entry.meshes.reduce((n, record) => n + record.triangleIds.filter(id => replaced.has(id)).length, 0), 0);
      return tanks
        ? { visibleSourceTanks: replaced.size, hiddenOlderTriangles: hiddenTriangles, preparedScope: 'bounded OST tank pilot; not municipality-wide' }
        : { visibleSourceBuildings: replaced.size, hiddenNewerTriangles: hiddenTriangles, preparedScope: 'bounded source-appearance pilot; not municipality-wide' };
    },
  };
}

// The offline atlas is the replaceable interpretation. Keep its measured UVs,
// roof/facade distinctions and colours; no generic window grid or random paint.
export function prepareAppearanceModel(model, { applyLighting, applyCutaway, night }) {
  const seen = new Set();
  model.traverse(mesh => {
    if (!mesh.isMesh) return;
    mesh.castShadow = mesh.receiveShadow = true;
    for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
      if (seen.has(material)) continue;
      seen.add(material);
      material.roughness = 1; material.metalness = 0;
      material.flatShading = true;
      // The native KHR_techniques edition did not consistently encode culling
      // state in glTF PBR. Match the existing municipal renderer's two-sided
      // surfaces: front-face winding must not erase whole source facades.
      material.side = THREE.DoubleSide;
      if (material.map) {
        material.map.magFilter = THREE.NearestFilter;
        material.map.minFilter = THREE.LinearMipmapLinearFilter;
        material.map.colorSpace = THREE.SRGBColorSpace;
        material.map.needsUpdate = true;
      }
      // The fixture field consumes this varying. Standard glTF materials do
      // not have the city material's shader prelude; supply the same world
      // coordinate contract before composing lighting and cutaway hooks.
      const compile = material.onBeforeCompile;
      material.onBeforeCompile = function(shader, renderer) {
        compile.call(this, shader, renderer);
        // Cropped emission has black borders; clamp wrapping alone could
        // repeat its mip-edge texels outside the observed source rectangle.
        if (material.userData.emissionCropGuard && material.emissiveMap) {
          shader.fragmentShader = shader.fragmentShader.replace('#include <emissivemap_fragment>',
            `#ifdef USE_EMISSIVEMAP
             if (any(lessThan(vEmissiveMapUv, vec2(0.0))) || any(greaterThan(vEmissiveMapUv, vec2(1.0)))) totalEmissiveRadiance = vec3(0.0);
             #endif
             #include <emissivemap_fragment>`);
        }
        // Only gate the glTF source emission. Fixture lighting appends its
        // contribution after emissivemap_fragment, so it is not gated twice.
        if (night && material.emissive) {
          shader.uniforms.appearanceSourceNight = night;
          shader.fragmentShader = 'uniform float appearanceSourceNight;\n' + shader.fragmentShader;
          shader.fragmentShader = shader.fragmentShader.replace('#include <emissivemap_fragment>',
            'totalEmissiveRadiance *= clamp(appearanceSourceNight, 0.0, 1.0);\n#include <emissivemap_fragment>');
        }
        shader.vertexShader = 'varying vec3 cityWorldPosition;\n' + shader.vertexShader;
        shader.fragmentShader = 'varying vec3 cityWorldPosition;\n' + shader.fragmentShader;
        shader.vertexShader = shader.vertexShader.replace('#include <begin_vertex>', `#include <begin_vertex>
          vec4 appearanceVertex = vec4(transformed, 1.0);
          #ifdef USE_INSTANCING
          appearanceVertex = instanceMatrix * appearanceVertex;
          #endif
          cityWorldPosition = (modelMatrix * appearanceVertex).xyz;`);
      };
      material.customProgramCacheKey = () => `010-source-appearance-world-v2-source-night-${Boolean(night && material.emissive)}-crop-${Boolean(material.userData.emissionCropGuard && material.emissiveMap)}`;
      applyLighting(material); applyCutaway(material);
      material.needsUpdate = true;
    }
  });
}
