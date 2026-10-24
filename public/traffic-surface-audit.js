import * as THREE from 'three';

// On-demand inspection of the actual loaded meshes, not a second source map.
// Colours are pre-lighting material/vertex colours; this is not framebuffer QA.
export function inspectTrafficSurfaces({ samples, tilesets, camera, width, height }) {
  const roots = [];
  for (const tiles of tilesets) {
    if (!tiles.group.visible || !['ground', 'streets', 'yards', 'bridges', 'bridgeSurfaces', 'industrialTerrain', 'greenTerrain'].includes(tiles.kind)) continue;
    for (const tile of tiles.visibleTiles) if (tile.engineData.scene) roots.push({ kind: tiles.kind, model: tile.engineData.scene });
  }
  const ray = new THREE.Raycaster();
  function hits() {
    return roots.flatMap(({ kind, model }) => ray.intersectObject(model, true).filter(hit => {
      for (let node = hit.object; node; node = node.parent) if (!node.visible) return false;
      return hit.object.isMesh;
    }).map(hit => ({ ...hit, kind }))).sort((a, b) => a.distance - b.distance).slice(0, 6).map(hit => {
      const mesh = hit.object, geometry = mesh.geometry;
      const material = Array.isArray(mesh.material) ? mesh.material[hit.face.materialIndex] : mesh.material;
      const colour = material.color?.clone() || new THREE.Color(1, 1, 1);
      const colours = geometry.getAttribute('color');
      if (material.vertexColors && colours) {
        const vertex = new THREE.Color().setRGB(0, 0, 0);
        for (const i of [hit.face.a, hit.face.b, hit.face.c]) vertex.add(new THREE.Color().fromBufferAttribute(colours, i));
        colour.multiply(vertex.multiplyScalar(1 / 3));
      }
      let tableNode = mesh;
      while (tableNode && !tableNode.batchTable) tableNode = tableNode.parent;
      const ids = geometry.getAttribute('_batchid');
      let attributes = null;
      if (ids && tableNode) try { attributes = tableNode.batchTable.getDataFromId(ids.getX(hit.face.a))?.attributes || null; } catch {}
      return { layer: hit.kind, mesh: mesh.name, surfaceKind: mesh.userData.surfaceKind || null,
        point: hit.point.toArray(), distance: hit.distance, colourBeforeLighting: '#' + colour.getHexString(),
        polygonOffset: material.polygonOffset, renderOrder: mesh.renderOrder, attributes };
    });
  }
  return samples.map(sample => {
    const position = new THREE.Vector3().fromArray(sample.worldBasePosition);
    const ndc = position.clone().project(camera);
    ray.setFromCamera(new THREE.Vector2(ndc.x, ndc.y), camera);
    const cameraSurfaces = hits();
    ray.set(position.clone().add(new THREE.Vector3(0, 50, 0)), new THREE.Vector3(0, -1, 0));
    return { ...sample, screenCSS: [(ndc.x + 1) * width / 2, (1 - ndc.y) * height / 2], cameraSurfaces, verticalSurfaces: hits() };
  });
}
