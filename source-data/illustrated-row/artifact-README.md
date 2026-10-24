# Eight-building retained-3D appearance candidate — review only

Open `row-review.glb` with the adjacent `textures/` directory intact. It draws ONLY the eight BAG buildings in `georeference-and-identities.json`. 678 original source triangles; source positions, normals, UVs and batch IDs retained. Indexed draw lists select the eight buildings. Each PNG is under 3.2 MB; geometry GLB is 250,648 bytes. Texture PNGs total 25.04 MB; this is not a production GPU-memory budget or municipal throughput result.

`verification.json`: independent parsing of this delivered GLB and its external textures reconstructed source geometry/UV arrays exactly and reproduced the actual review render with ZERO differing pixels. This verifies export fidelity, NOT that generated architecture is correct.

## Placement

Dataset: https://www.3drotterdam.nl/datasource-data/3adbe5af-d05c-475a-b34c-59e69ba8dadc/tileset.json
Tile: `18/268620/55473.b3dm`
RTC ECEF metres: `[3931031.386085533, 305724.43749486655, 4996588.717016839]`.

Use exact root matrix, source hash and batch-to-BAG/attribute mapping in `georeference-and-identities.json`. Root matrix remains in GLB. For a source POSITION, the ECEF chain is RTC + glTF Y-up-to-Z-up × original root-node matrix × POSITION. Apply each transform ONCE. CESIUM_RTC repeats the original B3DM feature-table RTC; a loader that handles it should not add RTC again. Original child matrices are identity. Do not apply the separate legacy diagnostic alignment.json to this delivery.

## Appearance status

The revised roof removes the large unsupported orange tile areas. The cleaned rear removes most photographic branches. Five source-invalid vertical party-wall planes (photographs of neighbouring roofs projected onto walls) use restrained continuous neutral material, with no fabricated openings. Their exact triangle membership and interpretation are retained separately. This is a diagnostic manual classification; automated municipal classification remains unproved.

Still NOT accepted: uncertain rear openings revealed by model branch removal; generated sign lettering, interiors and small equipment details; residual seams/recesses and some source projection artifacts; full-block verified emission/glazing inventory; adjoining ground/trees/water coherence; actual runtime review and city-wide throughput. Treat generated text as illustrative markings, not searchable/business facts. Do not silently promote this review candidate to production.

## Replaceability / provenance

Raw municipal source remains authoritative and is retained separately in the supplied original source archive. Native painted surface inputs, correction prompts, per-plane source comparisons and actual multi-bearing renders are in this ZIP's `evidence/` directory. Their JPEG copies are for visual review; original PNGs remain in saved workspace. Compilation scripts are included for examination. Material appearance can be replaced independently of geography, building IDs, routing, transit or terrain. No main implementation source or deployment was changed.

Municipal source: **CC BY 4.0 Gemeente Rotterdam**, https://hub.clearly.app/datasets/65ef2475fe2ac522c6ac7b63/information . Changes: model-assisted illustrated materials and restrained material completion; source geometry/UVs retained. Model creationDate does not establish photography capture date.
