# Measured terrain at middle distance

Written by AI on 2026-10-24 by model GPT-6.

Run `python3 scripts/build-green-terrain.py` in the existing project environment with NumPy, pyproj and Shapely. The output is standard 3D Tiles/glTF under `public/data/green-terrain/`. Native municipal BGT supplies measured shape and surface classes. No photographic images or flat replacement surface are generated.

## Source and selection

The builder reads the native ground tileset `0025cb58-e0f5-4169-bb4c-5339a3bc2a7e` at 3drotterdam.nl. Original decoded bytes, HTTP headers, acquisition times and hashes are retained in the ignored SSD cache `work/data-cache/green-terrain/`; compressed cache size was approximately 212 MB for this build. Municipality and BRT source collection acquisition reuse the existing pipeline and raw response cache.

A tile is selected when surveyed BRT forest, grass, heath, dune or sand covers at least 40% of its municipal portion, or surveyed dunes cover at least 0.5%. Native height bounds must contain valid elevations. This selects useful green/coastal areas across the municipality rather than rendering special cases for named places. BRT only selects source tiles; the emitted geometry and class boundaries come from the native BGT mesh.

Only native green, sand, footway, cycleway and ordinary roadway features are retained. Buildings, water and bridge structures are excluded. Triangles containing geographic heights below -30 m are omitted. Examined source records contain the -99.99 missing-height sentinel and intermediate -50/-66 m ramps. Near-zero-plan-area vertical curtains (minimum horizontal triangle altitude below 5 cm and height range above 1 m) are also omitted. This is a model-reviewed repair of this native 2D terrain source, not a publisher validity contract or a height-datum change. Ordinary negative terrain remains; actual kade/muur and structural classes are excluded from this stage rather than filtered as ground. Original cached source bytes remain unchanged. Triangles crossing the exact municipal boundary are omitted conservatively; they are not stretched across neighbouring territory or water. This can leave narrow boundary gaps for the overview to fill.

The inventory selected 280 tiles. The output contains 230 tiles, 652 meshes and 3,469,303 triangles. The other 50 tiles have no eligible valid measured surfaces after filtering; all omissions are explicit in the manifest. There were no acquisition or decoding failures. This is selected municipal green/coastal coverage, not every ground feature in Rotterdam.

## Geometry and rendering contract

Mesh metadata uses `surfaceKind`: `green`, `sand`, `footway`, `cycleway` or `road`. The coordinate frame and tileset transform match the prepared streets: glTF X east, Y up, Z south at 51.915 N / 4.49 E, with ENU tile bounds. Presentation assigns materials; none are baked into the geometry.

Interior source vertices can be clustered in 2 m horizontal / 0.25 m vertical cells. Clusters that add an open edge or reverse a face are undone. Original boundary edges, including the edges of holes, remain unchanged before quantisation. This conservative pass reduced the retained 3,644,467 source triangles by 4.8%; the main delivery saving comes from selecting source classes, indexing and standard 16-bit glTF quantisation. The largest measured quantisation bound is 5.77 cm. Recorded clustering displacements describe moved source vertices, not a universal bound on interpolated surface error.

The output is 43.84 MB raw and 32.97 MB gzip across the municipality. The original included native tiles contain substantially more geometry and metadata; this output still needs ordinary visible-tile streaming. Do not preload all children or claim a measured load-time improvement from these size figures.

Use this layer at middle distance and the full native ground at close range. Avoid rendering both at once. Some measured park surfaces lie below the flat overview; give measured terrain priority where it is available rather than changing its source height. That reconciliation belongs in the renderer and needs visual verification. The build does not alter the existing scene or materials.

## Dates, attribution and verification

The observed native ground edition dates are 2017–2019. Individual retained BGT `INWIN` record dates span 2008-07-28 to 2019-08-29. The tileset HTTP Last-Modified header is 2023-06-27; that is an inventory file date. These dates mean different things; none establishes a current terrain survey. Native geometry can contain older features, source errors and missing heights.

Credit Gemeente Rotterdam for the public-domain native 3D model. Credit Kadaster / PDOK for BRT and municipal boundaries under CC BY 4.0. The output manifest retains per-tile source URLs, hashes, response dates, feature counts and record dates. See [the source inventory](data-sources.md).

Every output GLB parsed with the vendored GLTFLoader; all surface classes survived and decoded positions fit child bounds within 1.96 mm. At 4.125 E / 51.995 N, the compact dune surface is 5.299 m against the original 5.292 m. At 4.124 E / 51.9945 N, the cycleway is 6.227 m in both. A source hole at 4.1235 E / 51.994 N stays empty. These are actual geometry checks, not visual acceptance of the integrated map. Probe and validation reports are retained in `work/source-quality/height/`.

The integrated renderer draws flat overview, street and yard layers first without writing depth. Measured ground then supplies depth and occlusion. This gives surveyed low park surfaces priority without raising their coordinates or baking a geographic mask. The compact terrain is active at spans 1.4–12 km; the complete native ground replaces it below 1.4 km.

The coast spike was traced to coincident geographic positions at 4.1059567613 E / 51.9872687249 N with decoded heights 9.48 m and -63.50 m: an approximately 73 m vertical source curtain. Local tangent Y is not geographic height; Earth curvature must not be mistaken for a missing-height artifact. The repair uses ECEF-to-geographic heights and projected triangle shape. Per-tile diagnostic counts cover all decoded source triangles in emitted tiles before semantic/boundary selection; they are not an additional rendered-triangle saving.

## Delivery partitioning

The runtime assets now pass through [exact spatial subdivision](prepared-mesh-subdivision.md). Dense meshes are partitioned into 250 m cells after reconstruction; triangle/attribute values and LOD semantics are preserved. The source-builder size figures above describe the retained pre-subdivision assets, not the current delivery totals.
