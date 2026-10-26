# Building assets: test tile

Written by AI on 2026-10-26 by GPT-6 Astra.

Run from the repository root in order:

```sh
pipeline/assets/verify.py --tile x90250_y436000
pipeline/assets/compose.py --tile x90250_y436000
pipeline/assets/assemble.py --tile x90250_y436000 --provenance-tint
pipeline/assets/compare_composition.py
```

Verification aligns generated elevations and checks visible source edges,
measured window boundaries and CIEDE2000. Missing source assessment stays
interpreted. Numerical checks do not certify every architectural component.
Unchanged inputs reuse derived outputs. Generator-owned `generated-raw.png`,
`generation.json` and `prompts/` are read-only to these commands.

Composition uses model-made parts under `assets/v1/parts/`, scalar measured
material colours and the wall's observed opening rectangles. It copies no photo
texels. Unknown material inherits a same-building measurement, then a tile
measurement, with interpretation recorded. Source-reviewed corrections for the
ten comparison walls are hash-bound to their original photos. No uniform window
grid is inferred. Unmeasured architectural details remain interpreted.

The parts library is extracted from the ten independently generated comparison
facades. `derive_parts.py` rebuilds it from those saved outputs; reruns do not
make image calls. `compare_composition.py` shows the photo, actual composition
atlas crop, and independent tier-1 redraw at a common 5 cm pixel grid. Generated
comparisons are style references, not ground truth for counts or geometry.

Assembly replaces every source material, including rejected generation,
low-evidence walls and triangles outside the facade inventory. Roofs use the
roof asset; areas beyond aerial coverage are interpreted. Every asset material
has `extras.asset: true`. Positions, normals, feature IDs and feature metadata
are preserved. The normal GLB is checked against the 25 MB budget.

`--provenance-tint` also writes `buildings-provenance.glb`. It retains geometry
and materials, blending interpreted texels 45% towards #ff00ff. Those images use
lossless PNG to preserve unchanged delivery texels and the exact blend. The tint
GLB is a diagnostic artifact and can exceed the normal delivery size budget.
`buildings.assembly.json` records routes and wall/roof area-weighted numerical
verified and interpreted fractions. Synthetic tier-2 styling is interpreted.
