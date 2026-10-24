# APARTMENT — bound source-preserving art review asset

Source IDs: BAG_0599100000670808. Namespace BAG. Geometry asset: apartment-review.glb. Exact RTC, original root node transform, source IDs/attributes, source SHA and every final texture hash are in assets/georeference-and-identities.json. Positions, normals, UVs and identity attributes compare exactly to selected municipal source geometry. Independently parsing the export reproduces the actual baked CPU render with maximum channel difference 0. This does not certify generated feature accuracy.

Apply RTC and root matrix exactly ONCE according to the metadata coordinate_chain. Do not apply diagnostic alignment.json. Replace/reconcile only these exact source IDs; do not overlay duplicate geometry. OST is not BAG. No deployment or runtime implementation changes made here.

Licence: CC BY4.0 Gemeente Rotterdam, https://hub.clearly.app/datasets/65ef2475fe2ac522c6ac7b63/information . Dataset https://www.3drotterdam.nl/datasource-data/3adbe5af-d05c-475a-b34c-59e69ba8dadc/tileset.json tile 18/268621/55475.b3dm. Source record dates are not claimed photography dates. Original source and prior candidates retained.

Schans66–80 has source-observed asymmetric windows, frames, stairwell and balconies. The source's tree-covered region is explicitly masked against invented generated openings; restrained same-surface masonry fills the unknown portion. A source-invalid party wall carrying roof photography receives adjacent material, no false roof features. The untouched raw proposal and confidence mask were delivered separately in 010-apartment-drawing-review.zip.

Remaining rejection: neutral large wall treatment and dense roof grain need runtime context; some small roof fittings and recess joins remain unverified. No emission map is supplied because an independently reviewed source-glazing inventory is not yet complete for this building. Do not invent a generic night window grid. Its day material can receive actual runtime lighting; unobserved openings stay unlit.

## Scaling evidence and limits

Coverage report measures texture CHANGES against source, not semantic truth or artistic acceptance. It reports actual depth-visible fractions over 12 bearings, plus sampled total triangle-surface coverage including hidden party walls. Changed material also includes conservative uncertain-region completion.

Municipal atlases mix features. These isolated review exports retain source UV layout and may depend on most of a source tile's atlas images even for one feature. Do not instantiate separate copies of these whole atlas sets for each building/tank in production. The adjoining-tile compiler should update shared source-tile atlases once and preserve source-ID/material binding. Texture residency, GPU compression and total scene memory require actual phone profiling; these review PNGs are not a proved final delivery format.

Latest drawing branch used 8 native generations for the row (5 canonical surfaces + missing surface sheet + glazing cleanup + roof correction), 4 for apartment, 2 for tank. This excludes earlier failed pilot branches and manual source review. Source-invalid surface classification and occlusion masks still required manual judgment. Generalizable geometry extraction/planar or cylindrical parameterization, original-UV compilation, identity/emission binding and export verification are implemented; reliable automatic source-confidence interpretation and city-scale inference/retry throughput remain unproved. Native calls needed no new paid API. Local-model quality must be tested independently; do not train/evaluate against generated fittings as ground truth.
