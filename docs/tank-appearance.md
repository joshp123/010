# Bounded native port tank appearance

Reproduce offline with `python scripts/prepare-tank-appearance.py`, then verify
with `python tests/tank-appearance.py`. The helper reads the already-retained
current municipal source; it does not acquire additional city coverage.

Runtime interface: `/data/current-tank-appearance/tileset.json`. Layer kind is
`tanks`; mesh/node `extras.featureId` contains the literal source `OST_*` ID,
and content `extras.featureIds` lists visible feature identities. There are no
`bagId`, `bagIds` or fabricated `BAG_` fields. Original batch attributes, source
hashes and native metadata remain in `source-data/current-tank-evidence`.
The helper reuses existing primitive compaction, texture sampling LOD, source
UV-island residency and deployable-output checks through an explicit tank kind.
It introduces no parallel rendering framework or artistic filters.

A512px context parent uses a source-derived physical sampling error and REPLACE
children containing each tank's unchanged native source pixels. Parent RTC
translation is inherited exactly once. Native leaf bounds are tight oriented
boxes in the inherited source frame. Source positions, normals, original UVs
(before reversible per-feature packing), material values and image pixels are
preserved. The shared reference plus14native leaves and context model are16
valid GLBs; the largest is20,615,880bytes, below the25MiB asset limit.
All14finest contents together decode to103.86MiB including mipmaps; this is not
a measured view's residency. No native image downsampling is used.

**Replacement is exact, not geographic guessing.** The old runtime endpoint
`c70023a7-2878-41e9-bb81-a7c454bc310a` has exactly the same14OSTIDs in its
16/67119/13875.b3dm leaf. Evidence and original bytes are retained under
`source-data/tank-reconciliation`. Hide only matching old tank primitives while
the corresponding replacement content is actually visible. Restore them when
replacement disappears; keep old tanks elsewhere. Do not use building/BAG
reconciliation, draw both editions, or overwrite source PBR maps with the old
uniform tank colour. Scene binding and visual review belong to the manager.

Attribution: **Gemeente Rotterdam — 3D Rotterdam, CC BY4.0**. The exact current
resource25da2fa9-d5b7-4d44-b100-7ab3b3bf51dc is documented in
`source-data/current-tank-evidence/catalogue-evidence.json`. Model creationDate
2024-05-23 is not established photography date. Roof spokes/seams and ladder
markings are photographed evidence, not necessarily modelled geometry. This is
a source-rich port foundation, not a finished miniature-art claim.

Verification covers2,996expanded source/leaf triangles,22exact source RGB
images,1,512exact source pixel crops, inverse UV accuracy under.001source pixel,
per-feature bounding boxes, namespace integrity and file limits. All16GLBs pass
Khronos validation with zero errors/warnings. Current building compaction tests
also pass after the narrowly optional feature-kind extension.

## Runtime candidate integration

`?appearance=current&tanks=current` enables this separate tank review layer alongside the current building
pilot. Other appearance modes keep the original tank layer without requesting the
prepared tank tiles. The new layer uses the shared cache, source-sampling error
of one screen pixel, and optional-appearance loading priority after essential city
layers. Source PBR maps pass through the same fixture lighting, metro cutaway and
shadow hooks as the building appearance path.

The tank wrapper matches only literal `OST_*` values from the original batch
record's `id` to prepared mesh `featureId`. It uses no building batching or BAG
normalization. Visible replacement meshes suppress exact matching old triangles;
hiding or unloading the replacement restores the original indices. Diagnostics
are separate under `tankAppearance`, including visible source tanks, hidden old
triangles and visible texture dimensions/memory. About credits the current
textured buildings and tanks under the existing CC BY4.0 attribution.

`node tests/tank-appearance-runtime.mjs` parses the actual retained old B3DM and
prepared current GLBs through production loaders. It verifies all14pilot features
hide2,996old triangles,1,354adjacent triangles remain, individual leaves replace
only their own OST, late old loads inherit suppression, unload restores exact
indices, and source maps/lighting/cutaway/shadow preparation survive. These are
loader and CPU tests; the manager still owns actual GPU scene acceptance at
51.889845N,4.349129E.
