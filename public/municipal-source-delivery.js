// Written by AI on 2026-10-25 by model GPT-6 Astra.
import * as THREE from 'three';

// Uses the same visible-triangle, two source texels per physical pixel demand
// as source-texture-residency. Unchanged native source is the close child.
function visibleMipDemand(tiles, model) {
  let demand = 0;
  const points = [new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3()];
  const uv = [new THREE.Vector2(), new THREE.Vector2(), new THREE.Vector2()];
  model.updateWorldMatrix(true, true);
  for (const camera of tiles.cameras) {
    const size = tiles.cameraMap.get(camera), projection = new THREE.Matrix4().multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
    model.traverse(mesh => {
      if (!mesh.isMesh || !mesh.visible) return;
      const geometry = mesh.geometry, position = geometry.getAttribute('position'), texcoord = geometry.getAttribute('uv');
      if (!texcoord) return;
      const matrix = new THREE.Matrix4().copy(mesh.matrixWorld);
      if (!model.parent) matrix.premultiply(tiles.group.matrixWorld);
      matrix.premultiply(projection);
      const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
      const count = geometry.index?.count ?? position.count;
      for (const group of geometry.groups.length ? geometry.groups : [{ start: 0, count, materialIndex: 0 }]) {
        const texture = materials[group.materialIndex]?.map;
        if (!texture?.image?.width) continue;
        const dimensions = materials[group.materialIndex]?.userData?.municipalMipDimensions || [texture.image.width, texture.image.height];
        if (texture.matrixAutoUpdate) texture.updateMatrix();
        for (let offset = group.start; offset < group.start + group.count; offset += 3) {
          for (let corner = 0; corner < 3; corner++) {
            const index = geometry.index ? geometry.index.getX(offset + corner) : offset + corner;
            points[corner].fromBufferAttribute(position, index).applyMatrix4(matrix);
            uv[corner].fromBufferAttribute(texcoord, index).applyMatrix3(texture.matrix);
          }
          if (['x', 'y'].some(axis => points.every(p => p[axis] < -1.05) || points.every(p => p[axis] > 1.05))) continue;
          const du1 = (uv[1].x - uv[0].x) * dimensions[0], dv1 = (uv[1].y - uv[0].y) * dimensions[1];
          const du2 = (uv[2].x - uv[0].x) * dimensions[0], dv2 = (uv[2].y - uv[0].y) * dimensions[1];
          const determinant = du1 * dv2 - du2 * dv1;
          if (Math.abs(determinant) < 1e-8) continue;
          const dx1 = (points[1].x - points[0].x) * size.width / 2, dy1 = (points[1].y - points[0].y) * size.height / 2;
          const dx2 = (points[2].x - points[0].x) * size.width / 2, dy2 = (points[2].y - points[0].y) * size.height / 2;
          const a = (dx1 * dv2 - dx2 * dv1) / determinant, b = (dx2 * du1 - dx1 * du2) / determinant;
          const c = (dy1 * dv2 - dy2 * dv1) / determinant, d = (dy2 * du1 - dy1 * du2) / determinant;
          const trace = a*a+b*b+c*c+d*d, area = a*d-b*c;
          demand = Math.max(demand, 2 * Math.sqrt((trace + Math.sqrt(Math.max(0, trace*trace-4*area*area))) / 2));
        }
      }
    });
  }
  return demand;
}

export function createMunicipalSourceDelivery(tiles) {
  const enabled = new URL(location.href).searchParams.get('sourceMips') === '256';
  let manifest = null;
  const demands = new WeakMap();
  tiles.addEventListener('dispose-model', event => demands.delete(event.tile));
  const ready = enabled ? fetch('/data/municipal-delivery/manifest.json').then(response => {
    if (!response.ok) throw new Error(`Municipal derived manifest ${response.status}`);
    return response.json();
  }).then(value => { manifest = value; }).catch(error => { console.warn('Municipal derived source unavailable; using native source', error); }) : Promise.resolve();
  return {
    ready,
    preprocessNode(tile, basePath) {
      if (!manifest || !tile.content?.uri || (tile.extras?.municipalDerived || tile.extras?.municipalNative)) return;
      const source = new URL(tile.content.uri, basePath + '/').href;
      if (!source.startsWith(manifest.sourceRoot)) return;
      const key = source.slice(manifest.sourceRoot.length), record = manifest.tiles[key];
      if (!record || tile.children?.length) return;
      const original = { boundingVolume: structuredClone(tile.boundingVolume), geometricError: 0, refine: 'REPLACE', content: { ...tile.content, uri: source }, extras: { municipalNative: true } };
      // The renderer treats equal parent/child errors as unconditional refinement;
      // keep native's final zero error below this parent. viewError supplies the
      // actual physical-texture demand instead of this structural value.
      tile.children = [original]; tile.refine = 'REPLACE'; tile.geometricError = 1;
      tile.content.uri = new URL(`/api/municipal-delivery/${key}`, location.origin).href;
      tile.extras = { ...tile.extras, municipalDerived: { source, key } };
    },
    viewError(tile, result) {
      if (!tile.extras?.municipalDerived) return;
      const model = tile.engineData?.scene;
      if (!model) { result.error = 0; return; }
      const view = [model.parent?.uuid, model.visible, ...tiles.cameras.map(camera => [...camera.matrixWorld.elements, ...camera.projectionMatrix.elements, tiles.cameraMap.get(camera).width, tiles.cameraMap.get(camera).height].join(','))].join(';');
      let entry = demands.get(tile);
      if (!entry || entry.model !== model || entry.view !== view) {
        entry = { model, view, demand: visibleMipDemand(tiles, model) }; demands.set(tile, entry);
      }
      result.error = entry.demand * tiles.errorTarget;
    },
    async fetch(uri, options) {
      const pathname = new URL(uri, location.href).pathname;
      if (!pathname.startsWith('/api/municipal-delivery/')) return fetch(uri, options);
      try {
        const response = await fetch(uri, options);
        if (response.ok) return response;
      } catch (error) {
        if (options?.signal?.aborted) throw error;
      }
      const key = pathname.slice('/api/municipal-delivery/'.length);
      return fetch(manifest.sourceRoot + key, options);
    },
  };
}
