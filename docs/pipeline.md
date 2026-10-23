# Rebuild from the sources

Written by AI on 2026-10-24 by model GPT-6 Astra.

Start with [the requirements](../requirements/README.md) and [the user's words](../requirements/steering.md). They are authoritative. The implementation is an unfinished attempt, not the specification. In particular, detailed stylisation is the goal; displaying raw aerial photographs beside stylised buildings was tried and rejected.

## Inputs and transformations

| Stage | Current implementation | Replacement boundary |
|---|---|---|
| Public geographic sources | Exact endpoints, licenses, dates and sampled formats in [data-sources.md](data-sources.md) | Acquire a better source while retaining its original bytes, coordinates, object identifiers and provenance. |
| Municipality and distant terrain | `python3 scripts/fetch-data.py` reads Kadaster geometry, clips it to Rotterdam and produces `dist/data/` | Re-run or replace this transform. The raw API responses are cached separately in `work/data-cache/`; do not reconstruct them from the simplified output. |
| Detailed city geometry | `dist/scene.js` streams the municipality's standard 3D Tiles/glTF assets | The source geometry supplies shape and placement. Preserve the source mesh independently of presentation. No photographic atlas can safely be transferred by vertex index to a different edition of a mesh. |
| Streets between close-up and city scale | `python3 scripts/fetch-data.py --transport-only` retains a compressed GeoJSON source; `node scripts/build-streets.mjs` produces standard 3D Tiles/glTF | Rebuild from `source-data/transport-network.geojson.gz`. Surface classes stay in mesh metadata; colour stays in the style module. The manifest records source hash, coordinates, exclusions, width assumptions and quantisation bounds. |
| Large yards and terminal infrastructure | `python3 scripts/fetch-industrial-ground.py --rebuild` and `node scripts/build-industrial-ground.mjs` produce surveyed BGT paving and crane-track tiles | Original geometry and attributes remain in `source-data/industrial-ground.geojson.gz`. See [industrial-ground.md](industrial-ground.md) for selection and source semantics. |
| Bridge deck surfaces | `python3 scripts/build-bridge-surfaces.py` clips retained road, cycleway and tram footprints to hash-pinned, reviewed native deck triangles | See [bridge-surfaces.md](bridge-surfaces.md). Reviewed component selections are replaceable source interpretation, not renderer exceptions. Unreviewed decks remain explicitly omitted. |
| Streetlights | `node scripts/build-lamps.mjs` acquires all advertised source tiles and extracts source pole origins and head positions into compact standard 3D Tiles/glTF | Exact source URLs, hashes, acquisition dates and omissions are recorded in the generated manifest. Raw source tiles and prototypes remain in the SSD cache. Straight distant shafts and emitted light are illustrations; original pole geometry streams below 700 m span. |
| Surrounding context | `python3 scripts/fetch-context-land.py` retains a pinned Natural Earth coastline outside the exact municipality | Context is deliberately generalised and does not supply detailed city geometry. The municipal boundary must never become a fictitious coastline. |
| Coordinates | Geographic coordinates are converted through WGS84 Earth-centred coordinates to a local frame at 51.915 N, 4.49 E; X east, Y up, Z south | This is geographic plumbing. Different renderers or asset generators must agree on the same placement, not reproduce the current shader. |
| Source reconciliation | `dist/source-fusion.js` resolves native bridge/BGT overlap before rendering | Keep original geometry and attributes. Replace the reconciliation when better sources remove the conflict; do not reproduce the current clipping as measured geography. |
| Visual interpretation | `dist/miniature-style.js` exports `featureColor` and `createCityMaterial` | Replace colours, materials, procedural illustration or generated style assets here without changing search, map navigation, source acquisition or shared links. Existing window patterns and colour assignments are illustrative choices, not measured building facts. |
| View, light and export | `dist/scene.js` provides the orthographic camera, solar lighting, tile selection and `captureCanvas`; `dist/share.js` creates the image and caption | Preserve the geographic view and source attribution while improving or replacing the renderer. |
| Live observations | `dist/weather.js`; transport feasibility is in [transport-data.md](../requirements/transport-data.md) | Keep observation time, source and measured/estimated status in the data. Animation must not erase those distinctions. |

`source-tools/aerial.js` is the retained browser-side PDOK acquisition experiment. It is not imported by the public app. Its inputs are a camera, geographic projection and target resolution; its output is a georeferenced imagery atlas. Raw aerial imagery can inform a future stylisation or reconstruction stage without being displayed directly. It contains building lean, shadows and photographed bridges: blindly projecting it onto every upward surface produces false roads and mismatched appearances.

## What a better model should be able to redo

Keep raw sources, geometry and visual interpretation independently replaceable. If adding model-generated assets, retain the source references, generation prompt, model/version, settings and resulting geographic bounds alongside the output. Those records belong with the generation stage, not inside a renderer full of landmark-specific exceptions. There is no model-training or asset-generation framework here yet.

Use `python3 -m http.server 8780 --directory dist` and inspect the actual map. Views are reproducible through `lat`, `lon`, `span`, `bearing` and `light` URL parameters. Compare the same bridge, neighbourhood, port and coast at close and wide scales, day and night. `work/visual-qa/` retains local captures; some deliberately show rejected experiments and are not visual targets. Do not infer acceptance from a screenshot filename or a passing syntax check.

The streamed 3D services are upstream snapshots that may change. This repository records observed source editions and keeps sampled raw evidence on the SSD; it does not yet archive every municipal 3D tile. A future full rebuild that requires exact source reproducibility must pin or archive those input bytes before generation.

## Current delivery tradeoffs

Detailed ground uses municipal BGT below a 1,400 m camera span. Prepared BRT road/path/rail tiles remain visible at every map scale; these are 2D survey features, not measured elevations or live vehicles. Bridges and tunnels are excluded from this flattened network. The municipality overview supplies land and water beneath these networks. These thresholds are implementation choices, not requirements; compare the actual port and neighbourhood views before changing them.

The street build preserves all selected triangle topology. Standard glTF quantisation changes positions by at most 2 cm; oversized meshes retain Float32 positions. Nearby tiles load through the existing 3D Tiles renderer. Fixed-detail layers do not preload off-screen siblings. Recently visited ground remains within the bounded cache instead of being discarded on every zoom-out.

An exact prebuilt overview mesh was tested and rejected as a delivery optimisation: its compressed payload grew enough to risk slower cold loads despite saving browser triangulation. Retained source geometry remains the starting point; do not assume that moving computation offline always improves the user experience.

Tree prototypes remain source geometry. `object-detail.js` selects vertex-clustered approximations within a one-output-pixel displacement bound and restores originals for full-resolution exports. `tree-batches.js` combines byte-equivalent geometry in shared `InstancedMesh` draw calls while retaining source-to-instance mapping and the tile lifecycle. Replace either optimisation without changing geographic sources or styling.

A measured 1440 × 900 night-view comparison on the development Mac (Apple M4 Pro, in-app browser) reduced input-to-render-submission median from 180 ms to 12 ms, p95 from 291 ms to 26 ms, across two matching drags. This measures command submission, not physical display latency, and does not establish cold-load or phone performance. Actual before/after captures and the CPU profile are retained in ignored `work/visual-qa/`. The underlying cause was repeated pole geometry and hundreds of separate tree draw calls, not lack of instancing in the source.

Wide views descend empty building tiles until the source provides actual geometry; they must not stop at an empty geographic cell and erase whole districts. Building window heights compensate for Earth curvature in the local tangent frame, so the same material works at the coast as in the centre.

Export waits for active source roots, overview, queued requests and visible detail to settle. It temporarily permits 64 MB of tree source data for a wider poster frame, then returns to the 24 MB interactive cache. Tree batching uses the loader's visible model set; cached detached models must not leak into distant views.
