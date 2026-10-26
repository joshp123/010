# Building assets

Written by AI on 2026-10-26 by GPT-6 Astra.

For the 16-tile Delfshaven block, run from the repository root:

```sh
.devenv/profile/bin/python pipeline/assets/block.py --block delfshaven --render --preserve-existing x90250_y436000
.devenv/profile/bin/python pipeline/assets/block.py --block delfshaven --render --preserve-existing x90250_y436000 --watch
.devenv/profile/bin/python pipeline/assets/report_block.py
```

The first command builds every ready tile. The watch command repeats as Claude's
wall generation and source facts arrive. `--preserve-existing` reads and renders
the accepted test tile without replacing its three delivery files. Omit it only
when intentionally rerunning that tile. A single tile uses `--tile <tile>`.
Each tile records pending elevations, roof inputs, errors and render hashes.
Missing or incomplete generation uses interpreted composition. Every material is
an asset material; no original photograph texture is retained.

Roof preparation is `.devenv/profile/bin/python pipeline/assets/roofs.py prepare
--tile <tile>`. Make four native image-tool calls using each quadrant reference
and the read-only `prompts/roofs.md`, then persist the outputs with
`record_call.py`. `roofs.py assemble --tile <tile>` and `verify_roofs.py --tile
<tile>` use that tile's aerial and source-only occlusions. Semantic review flags
remain separate from colour scores. The accepted test roof is preserved.

`wall_facts.py --tile <tile>` prepares honest merged planes, BGT-facing
classification and rectified references. `perceive_walls.py --tile <tile>` uses
native ChatGPT contact sheets, measured photo colours and source-edge checks;
it requires existing ChatGPT authentication and makes no paid API calls.
Tile-local facts avoid overwriting a shared BAG record when a building spans a
tile boundary. Unmeasured or occluded openings are not extrapolated into grids.
Composition can use an explicitly interpreted adjacent-tile measured palette
when a tile has no usable material photo; the source measurement is retained.

Roof and wall numeric verified fractions do not certify every architectural
component. Provisional composition remains interpreted, even where its layout
uses photo measurements. Pending tier-1 work and perception coverage are quality
limits, not a publication acceptance claim. The 25 MB normal delivery target is
reported; larger tiles retain detail. Generated assets stay on the SSD, outside
code commits.

Individual accepted-test commands:


```sh
pipeline/assets/verify.py --tile x90250_y436000
pipeline/assets/compose.py --tile x90250_y436000
pipeline/assets/assemble.py --tile x90250_y436000 --provenance-tint
pipeline/assets/compare_composition.py
```

Verification aligns generated elevations and checks visible source edges,
measured window boundaries and CIEDE2000. Missing source assessment stays
interpreted. Numerical checks do not certify every architectural component.
Unchanged inputs reuse derived outputs. A colour-adjusted elevation whose
model output hash remains in generator metadata is accepted only when the saved
pre-colour image matches that hash and the documented colour pass reproduces
every delivered RGB pixel. Derived provenance records both image hashes and the
read-only postprocessor hash; generator metadata is never rewritten. Elevation-generator-owned `generated-raw.png`,
`generation.json` and `prompts/` are read-only to these commands.

Composition uses model-made parts under `assets/v1/parts/`, scalar measured
material colours and the wall's observed opening rectangles. It copies no photo
texels. Unknown material inherits a same-building measurement, then a tile
measurement, with interpretation recorded. Source-reviewed corrections for the
ten comparison walls are hash-bound to their original photos. No uniform window
grid is inferred. New source assessments can record internal window divisions;
only photo-edge-supported divisions are drawn. Unresolved panes use plain
frames instead of an invented pane pattern. Unmeasured architectural details remain interpreted.

The parts library is extracted from the ten independently generated comparison
facades. `derive_parts.py` rebuilds it from those saved outputs; reruns do not
make image calls. `compare_composition.py` shows the photo, actual composition
atlas crop, and independent tier-1 redraw at a common 5 cm pixel grid. Generated
comparisons are style references, not ground truth for counts or geometry.

Assembly replaces every source material, including rejected generation,
low-evidence walls and triangles outside the facade inventory. Roofs use the
roof asset; areas beyond aerial coverage are interpreted. Every asset material
has `extras.asset: true`. Positions, normals, feature IDs and feature metadata
are preserved. The normal GLB reports whether it meets the 25 MB target.

`--provenance-tint` also writes `buildings-provenance.glb`. It retains geometry
and materials, blending interpreted texels 45% towards #ff00ff. Those images use
lossless PNG to preserve unchanged delivery texels and the exact blend. The tint
GLB is a diagnostic artifact and can exceed the normal delivery size budget.
`buildings.assembly.json` records routes and wall/roof area-weighted numerical
verified and interpreted fractions. Synthetic tier-2 styling is interpreted.
