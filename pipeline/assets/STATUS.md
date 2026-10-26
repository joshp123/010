# Building assets: test tile

Written by AI on 2026-10-26 by GPT-6 Astra.

Current outputs use no source photo texels. The normal GLB is 24,736,324 bytes;
all 13,641 source triangles, normals, feature IDs and 231 feature records survive.
`retained_original` is 0 m² and all materials have `extras.asset: true`.
The 39 failed generated wall comparisons use tier 2. No pending elevations.

Routes by area: tier 1 46165.94 m²; tier 2 composed/fallback
97019.59 m²; roof asset 27592.65 m². Roof-asset
coverage includes 762.83 m² of bridge horizontal surfaces, all interpreted.
Building roof area alone is 26829.82 m².

Numerical source-visible verification: walls 8.2742% verified /
91.7258% interpreted; building roofs 91.4089% /
8.5911%. Including bridge horizontal surfaces, roof-asset
fractions are 88.8818% / 11.1182%. These screens do not certify all components.
All synthetic tier-2 detail remains interpreted.

Verification rerun: 157 elevations cached, 120/159 checkable walls pass,
433 walls have no checkable visible evidence, zero pending.
Composition: 1,864 walls; 1,119 observed opening placements; 33 source-reviewed
components; 18 model-made parts. Last full run 40.52 seconds.
Own measured material 97 walls; same-building inheritance 670; tile measurement
inheritance 1,097. No photo crops or uniform inferred window grid.

Ten independent image-tool redraws and the actual composed atlas crops are at
`tier2-comparison/tier2-vs-tier1.png`. Comparison-driven fixes include masonry
courses, cream frames/sills, pane-versus-aperture correction, clipped openings,
lintels, balcony fronts, actual ribbon panes and canopy ornament. Style parity
on observed parts is separate from unresolved source detail and semantic truth;
tier-1 redraws sometimes alter counts, so they never override source facts.

`assemble.py --tile x90250_y436000 --provenance-tint` also writes
`buildings-provenance.glb` (94,350,772 bytes). Every
interpreted texel is blended 45% towards magenta, using lossless diagnostic
textures. Full decoded-pixel and geometry checks are recorded in
`independent-output-review.json`.

Commands are in README.md. Claude generation inputs/prompts remain unchanged.
No web/tools edits by this run, paid API calls or commits.
The final shipping GLB was rendered offline and visually inspected:
`check-oblique-final.png` and its source-hash sidecar.
