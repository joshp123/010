# Native building primitive batching

Written by AI on 2026-10-24 by model GPT-6.

`public/building-batches.js` combines compatible sibling building primitives into one tile-local draw. It changes no source triangles, coordinates, normals, colours, feature IDs or transforms. Call it after the existing source colour/material assignment. It is independent of city loading, controls and style.

```js
const buildingBatches = createBuildingBatches();
// In native buildings load-model handling, after colorModel:
buildingBatches.addModel(event.scene);
// In buildings dispose-model handling:
buildingBatches.removeModel(event.scene);
// For the same-view visual/performance comparison:
buildingBatches.setEnabled(false); // Original primitive draws.
buildingBatches.setEnabled(true);  // One combined draw per compatible group.
```

The caller requests a frame after toggling. `diagnostics()` reports source/combined draw counts, unchanged triangle count, preparation time and memory allocation. `sourceForFace(mergedMesh, faceIndex)` maps a combined triangle back to its original mesh, original triangle index and source model. The `_batchid` attribute stays unchanged and resolves through the original model's batch table. Full-detail export can use the combined geometry because no approximation is introduced. `dispose()` restores original meshes and releases combined GPU geometry.

Actual retained native source tiles `buildings-model--rotterdam.b3dm` and `buildings-model--kop.b3dm` contain five and six primitive meshes respectively. All have the same sibling transform after loading and use the same building material after styling. Their position/normal data are interleaved float32, with a separate float32 feature-ID attribute. The module combines only matching parent, material, transform, attribute format, shadow/render-order/layer and culling settings. It skips instancing, skins, morph targets, partial draw ranges, material arrays and child-bearing meshes. Other geometry keeps its existing path.

The combined mesh stays under the same source parent with the exact original matrix. No world-coordinate baking or float rounding is needed. Each source geometry receives views into its exact section of the combined attribute arrays, plus its unchanged source index values in a separate small array. Detached source meshes remain available for reversible comparison and future interpretation. No global mega-mesh or cross-tile culling extent is created. Tile visibility and unloading continue through the existing parent model.

The actual source check compared every position, normal, colour, feature-ID value, triangle index and matrix component before/after. It also exercised source-face mapping, toggling and unload restoration. Results were five → one draws with 4,062 triangles and six → one draws with 4,994 triangles. Node preparation measured about 4.6 ms for the first tile and 0.9 ms for the second. These prove source equality and CPU preparation only; parent browser screenshots, rendered draw counts, pan latency and cache behavior determine whether this optimisation should ship.

Memory is a real tradeoff. The native loader retains a GLTF parser in tile metadata, whose decoded-buffer cache may retain old backing arrays even after source geometries share the combined views. The module does not clear undocumented loader internals. `conservativeAdditionalBytes` therefore counts the entire new attribute allocation plus combined and copied source indices: approximately 0.56 MB and 0.69 MB for these samples. Shared source geometry views prevent yet another attribute copy, but do not establish unchanged total heap usage. A visible building cache of roughly 80 MB can incur a substantial additional CPU allocation. Inspect actual browser/cache pressure before enabling this across the city.

The original native assets, geographic hierarchy, source licence and retained provenance remain unchanged. This module introduces no derived asset or new data source. Removing its two lifecycle calls restores the existing pipeline; independent application code remains MIT.
