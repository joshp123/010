# Rotterdam ground scene

Written by AI on 2026-10-25; updated 2026-10-26 by model GPT-6.1 Sol.

From the repository root:

```sh
devenv shell -- python pipeline/ground/build.py --area core
devenv shell -- python pipeline/ground/build.py --area m0
devenv shell -- python pipeline/ground/build.py --area m1 --workers 6
devenv shell -- python pipeline/ground/check_alignment.py
```

M0 includes all 16 core tiles. Raw responses are pinned in dated source archives on the SSD; a rebuild reuses those bytes. No package changes are needed by this stage. Outputs are `scene/v1/tiles/<tile>/{ground.glb,ortho.jpg,classes.png}`, merged ground fields in `scene/v1/manifest.json`, and `ground-{core,m0,m1}-report.json`. A file lock protects manifest merges with the building stage.

- `archive.py`: exact response bytes, URLs, timestamps, SHA-256 and attribution.
- `surfaces.py`: current BGT polygons in RD, explicit class mapping, holes, level ordering, 10 cm rasterisation. Detailed vegetation attributes distinguish shrubs from grass. BGT historical/retired, planned and underground features are excluded. `spoor` is the centre of each individual track, per [BGT catalog 10.3.1](https://docs.geostandaarden.nl/imgeo/catalogus/bgt/). Rails are offsets of ±0.7175 m; train/sneltram uses bit 2, tram bit 1. Kerbs are shared road/cycleway–pavement raster boundaries.
- `markings.py`: archives Rotterdam's official marking records for comparison. Final M1 extraction uses thin, bright, neutral aerial components with vehicle rejection; municipal support overlap is recorded but does not gate extraction. Short dashes, broad symbols, shadows, canopy and parking paint can be missed. The municipal register has no stated licence found in source metadata or official catalogues: **the manifest records it as unlicensed**. The mask is retained for Claude's decision. No publication permission is asserted.
- `geometry.py`: municipal b3dm triangles, complete node hierarchy and RTC transform, actual RDTRANS2018 grid, exact tile clipping, local glTF axes, `_CLASS`, preserved real vertical faces. Source local Y already encodes apparent NAP height while the RTC origin is at ellipsoid height zero; blindly applying GEO2018 would lower everything about 44 m. Source height values are retained, and this inference is recorded in the report. It is not an independent vertical survey. Defective features contain nodata-interpolated 50–100 m pits. Features with a vertex below −10 m in this bounded ground area are omitted in full and individually reported; their holes are not filled. This policy must be reconsidered for another area or source edition.
- `build.py`: exact RD WMS requests, orchestration, source and output hashes, class shares, ground coverage and full-resolution debug comparisons. Actual masks use class IDs, never the debug colours. Photographs are reference inputs, not the intended rendered road appearance.

New full-resolution comparisons are under `scene/v1/debug-ground/` (prior M0 evidence remains under `renders/debug-ground/`): `x90250_y436000-comparison.png` (Aelbrechtskolk) and `x90000_y436000-comparison.png` (Schiedamseweg). Each has the unmodified aerial, flat class map with line bits, and an aerial alignment overlay. Yellow rails, cyan train/metro rails, white markings and dark kerbs on classes; magenta paint on the aerial. Source-ground water-boundary alignment evidence is also retained there. After a core build, `check_alignment.py` regenerates `ground-water-boundary-probe.png` (native municipal water blue, current BGT boundary red) and `ground-water-alignment.json`. The report compares native water vertices with the current vector boundary and the built class raster, and records the mesh survey dates and height-datum inference. It also reads each delivered debug tile’s `ground.glb` and writes `*-delivered-ground-coverage.png`: red marks nonbuilding pixels with no delivered height mesh, over the aerial photo. Missing area by surface class is included in the JSON report. It reads production outputs and writes only debug evidence.

Class coverage and height-mesh coverage are different: BGT can classify a courtyard whose municipal 3D source has no valid height. The reports retain both measures. Dates differ among the municipal mesh, current BGT, marking register and spring 2026 photo; changes and occlusion are not repaired by guessing.

Observed limitations in this snapshot:

- M0 has 78,087.24 m² of uncovered nonbuilding ground (3.098% of the BGT nonbuilding area). Core has 20,737.85 m². These are geometry omissions, not unknown class pixels.
- Aelbrechtskolk's missing pavement includes a waterfront strip near the bridge: 425.25 m² of pavement in that tile. Both inspected core tiles have complete carriageway and tram-bed geometry.
- The largest apparent M0 gap is `x91750_y436000` at Erasmus MC. At RD 91850,436150, the archived current BGT contains road feature `G0599.04482078ced14f6989f9a2374d32f409` (`rijbaan lokale weg`, 2026 publication) and no current pand footprint, while the 2026 photo visibly contains hospital roofs. The class mask preserves the recorded class; it does not interpret the roof photo as a road. The missing-ground percentage here therefore includes surfaces beneath buildings. Inspect `x91750_y436000-delivered-ground-coverage.png`; do not interpret the entire red hospital area as a missing public road.
- Three `spoor` features are explicitly `(haven)kraan`, not tram/train/metro. They are retained in raw BGT, counted as omitted in tile rail statistics, and are not drawn as fictitious standard-gauge tracks. The current line-bit contract has no crane-rail type.

Read the actual delivered files against the contract:

```sh
devenv shell -- python pipeline/ground/check_outputs.py m0
```

M1 covers RD [89750,434750,96500,438000], 351 tiles. Six fork workers share immutable ground arrays and a precomputed triangle index. Each worker holds one decoded aerial tile. Source archive manifest locks work across processes. BGT archive filenames include request bounds so an M0 cache cannot answer an M1 request. Municipal markings select feature IDs by extent then fetch exact batches of 500 IDs, avoiding the service’s failed deep-offset query; raw failed responses remain archived.

Train and metro beds use class 14 (`spoorbaan`); class 16 is reserved for explicit ballast. Surface/elevated `trein` and `sneltram` BGT centre lines draw bit 2 at standard gauge. Negative relative-height features are excluded. Crane rails remain explicitly omitted. No ballast or hidden railway detail is inferred from photographs.

M1 comparison files are `scene/v1/debug-ground/x93000_y436000-comparison.png` (Erasmusbrug) and `scene/v1/debug-ground/x91750_y437500-comparison.png` (Centraal). Each panel preserves the native 2500 × 2500 resolution. Licence evidence, catalogue queries and limitations are in `markings_licence.json`, mirrored into the scene manifest. Raw evidence is under `sources/markings-licence-evidence/2026-10-26/`.

```sh
devenv shell -- python pipeline/ground/check_outputs.py m1
```

M1 marking correction after visual inspection: the municipal register support missed photographed road dashes and accepted vehicle highlights. Final extraction uses aerial white top-hat, brightness >165, channel range <40, narrow elongated components (principal variance ratio >=8), with lower-threshold neutral vehicle-roof rejection and 50 cm dilation. Parking pixels are omitted conservatively. Short/fat markings and shadowed paint are missed. Municipal vectors remain archived and their overlap is measured in per-tile statistics; they no longer gate paint extraction. The manifest retains the requested unlicensed status for the marking register and retained mask. This deterministic mask is an approximation, not complete vector truth.

Final M1: all 351 tiles passed delivered-file checks (3,398,005 ground triangles). Unknown class: 32 pixels, 0.32 m². Missing height: 641,776.66 m², 3.573035% of nonbuilding class pixels. Near Erasmusbrug, native water is −0.076..+0.038 m NAP; actual quay faces reach +3.129 m north and +6.110 m south. See `scene/v1/ground-m1-maas-source-check.json`. Current BGT still maps part of the visibly filled Rijnhaven construction area (`x93500_y435250`) as water. Geometry surveys date from 2008–2019; class/height/photo disagreement is retained rather than guessed away. Centraal's roof hides train rails in the required comparison; the additional `x91500_y437750` comparison shows the exposed approaches. The `x93500_y435250` comparison shows elevated metro rails. BGT ground classes beneath/around roofs can also admit roof highlights into the heuristic marking mask.
