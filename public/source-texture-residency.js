// Written by AI on 2026-10-24 by model GPT-6 Astra.
import * as THREE from 'three';

// Keep native decoded images available for close views. GPU uploads follow the
// largest visible triangle's physical pixel footprint, including oblique UVs.
export function createSourceTextureResidency() {
  const nativeImages = new Map();
  const positions = [new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3()];
  const uvs = [new THREE.Vector2(), new THREE.Vector2(), new THREE.Vector2()];
  const projection = new THREE.Matrix4(), meshProjection = new THREE.Matrix4();
  let previousView = '', lastStatistics = {};
  return {
    update({ tiles, camera, physicalWidth, physicalHeight }) {
      const entries = [...tiles.lruCache.itemList].filter(tile => tile.internal?.renderer === tiles && tile.engineData?.scene);
      const visible = tiles.visibleTiles;
      const viewKey = [...camera.matrixWorld.elements, ...camera.projectionMatrix.elements, physicalWidth, physicalHeight,
        ...entries.flatMap(tile => [tile.engineData.scene.uuid, visible.has(tile)])].join(',');
      if (viewKey === previousView) return false;
      previousView = viewKey;
      projection.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
      const demand = new Map();
      for (const tile of entries) {
        const model = tile.engineData.scene;
        model.updateWorldMatrix(true, true);
        model.traverse(mesh => {
          if (!mesh.isMesh) return;
          const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
          for (const material of materials) {
            const texture = material.map;
            if (!texture?.image?.width) continue;
            if (!nativeImages.has(texture.source)) nativeImages.set(texture.source, texture.image);
            if (!demand.has(texture.source)) demand.set(texture.source, { textures: new Set(), scale: 0 });
            demand.get(texture.source).textures.add(texture);
          }
          if (!visible.has(tile) || !mesh.visible) return;
          const geometry = mesh.geometry, position = geometry.getAttribute('position'), uv = geometry.getAttribute('uv');
          if (!uv) return;
          meshProjection.multiplyMatrices(projection, mesh.matrixWorld);
          const indices = geometry.index, count = indices?.count ?? position.count;
          const groups = geometry.groups.length ? geometry.groups : [{ start: 0, count, materialIndex: 0 }];
          for (const group of groups) {
            const texture = materials[group.materialIndex]?.map;
            if (!texture?.image?.width) continue;
            const record = demand.get(texture.source), native = nativeImages.get(texture.source);
            if (texture.matrixAutoUpdate) texture.updateMatrix();
            for (let offset = group.start; offset < group.start + group.count; offset += 3) {
              for (let corner = 0; corner < 3; corner++) {
                const vertex = indices ? indices.getX(offset + corner) : offset + corner;
                positions[corner].fromBufferAttribute(position, vertex).applyMatrix4(meshProjection);
                uvs[corner].fromBufferAttribute(uv, vertex).applyMatrix3(texture.matrix);
              }
              if (['x', 'y'].some(axis => positions.every(point => point[axis] < -1.05) || positions.every(point => point[axis] > 1.05))) continue;
              const du1 = (uvs[1].x - uvs[0].x) * native.width, dv1 = (uvs[1].y - uvs[0].y) * native.height;
              const du2 = (uvs[2].x - uvs[0].x) * native.width, dv2 = (uvs[2].y - uvs[0].y) * native.height;
              const determinant = du1 * dv2 - du2 * dv1;
              if (Math.abs(determinant) < 1e-8) continue;
              const dx1 = (positions[1].x - positions[0].x) * physicalWidth / 2, dy1 = (positions[1].y - positions[0].y) * physicalHeight / 2;
              const dx2 = (positions[2].x - positions[0].x) * physicalWidth / 2, dy2 = (positions[2].y - positions[0].y) * physicalHeight / 2;
              const a = (dx1 * dv2 - dx2 * dv1) / determinant, b = (dx2 * du1 - dx1 * du2) / determinant;
              const c = (dy1 * dv2 - dy2 * dv1) / determinant, d = (dy2 * du1 - dy1 * du2) / determinant;
              const trace = a * a + b * b + c * c + d * d, area = a * d - b * c;
              const maximumStretch = Math.sqrt((trace + Math.sqrt(Math.max(0, trace * trace - 4 * area * area))) / 2);
              record.scale = Math.max(record.scale, Math.min(1, maximumStretch * 2));
            }
          }
        });
      }
      let changed = false, nativeBytes = 0, uploadedBytes = 0;
      for (const [source, record] of demand) {
        const native = nativeImages.get(source);
        const scale = Math.min(1, Math.max(1 / 16, 2 ** Math.ceil(Math.log2(record.scale || 1 / 16))));
        const width = Math.max(1, Math.ceil(native.width * scale)), height = Math.max(1, Math.ceil(native.height * scale));
        nativeBytes += native.width * native.height * 4;
        uploadedBytes += width * height * 4 * 4 / 3;
        if (source.data.width === width && source.data.height === height) continue;
        let image = native;
        if (scale < 1) {
          image = document.createElement('canvas'); image.width = width; image.height = height;
          const context = image.getContext('2d');
          context.drawImage(native, 0, 0, width, height);
        }
        for (const texture of record.textures) texture.dispose();
        source.data = image;
        for (const texture of record.textures) texture.needsUpdate = true;
        changed = true;
      }
      const residentSources = new Set(demand.keys());
      for (const source of nativeImages.keys()) if (!residentSources.has(source)) nativeImages.delete(source);
      lastStatistics = { sourceImages: demand.size, nativeDecodedRgbaBytes: Math.round(nativeBytes), uploadedRgbaBytesIncludingMips: Math.round(uploadedBytes), nativeDecodedImagesRetained: true };
      return changed;
    },
    diagnostics: () => lastStatistics,
    dispose() { nativeImages.clear(); },
  };
}
