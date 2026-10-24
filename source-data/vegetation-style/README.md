# Native vegetation evidence and replaceable interpretation

Source: Gemeente Rotterdam / Rotterdam 3D, public-domain model, separately attributed from MIT application code. Exact retained URLs, acquisition date and decoded hashes are in `provenance.json`. `*.gz` files losslessly retain the original source bytes; decompress them to recover the index, sample `.cmpt` and original prototype GLBs. The small `*-positions.json` extracts preserve original position accessor values for executable tests; their source hashes identify the complete corresponding GLB.

## What causes the egg/cone appearance

The actual Delfshaven source leaf `15/33577/6934.cmpt` contains separate crown and trunk instance groups. `tree_part` identifies `kruin` (crown) and `stam` (trunk). The sample has 344 trunks and 344 crowns spread over nine generic crown prototypes (plus one trunk prototype). The source crown GLB inspected here has only a solid green 64×64 texture. It does not contain leaf clusters, branching detail or a measured individual canopy surface.

The prototypes occupy unit envelopes, approximately X/Z −0.5…0.5 and Y 0…1. Original i3dm scale tuples are `[crownDiameter, crownDiameter, height − Stamlengte]`; the renderer's Y-to-Z axis adjustment applies before that scale. This preserves the intended diameter and crown height. The source's rotation vectors then place it upright on Earth. For example, the sampled `proto_6` group includes crown diameters up to 18 m and crown heights up to 20 m. Those sizes originate in the municipal data; neither tree batching nor the existing screen-space geometry clustering introduces a second scale factor.

These are inventory dimensions and generic type shapes, not surveyed leaf surfaces. In the sample, total height falls into coarse values such as 5, 8, 11 and 14 metres. `Hoogte` is ground elevation and must not be confused with `height`. A giant-looking crown is not sufficient evidence to shrink a source tree. Suspicious inventory values require a separate source-quality assessment against other observations.

The current scene replaces all source colours with one green, including trunks. `object-detail.js` approximates the original prototype within a one-pixel displacement bound; it cannot invent the canopy character absent from the prototype. `tree-batches.js` combines equivalent geometry and composes the original instance and world transforms; its source geometry comparison and transform path do not explain oversized crowns in this sample.

## Candidate interpretation

`public/vegetation-style.js` is an independently replaceable interpretation stage.
The previous solid spheres in repeated horizontal rings produced the plastic,
scaly crown visible in the actual phone review. The candidate replaces them with
thin, overlapping directional foliage sprays and open gaps. It derives a vertical
width profile from each retained municipal prototype and fits the final geometry
to the exact original bounds. It changes no instance position, diameter, height
or rotation. Trunks retain their original geometry and brown colour.

The exact representative elm is `bm_83722_K`, inventory `Ulmus minor`, planted
1975, crown diameter 15 m, height 22 m, stem length 6 m. Its source transform and
phone projection are retained in `row-tree-instance-audit.json`; the apparent
large size is not corrected by shrinking it. The 2026 8 cm aerial at
`../public-space-pilot/schiedamseweg-2026.jpg` (provenance in adjacent JSON) is
leaf-off. At RD [90283.8078,436074.1957] it shows an open branched crown at the
street edge. It does not measure summer leaf placement, colour or individual
branch depth. The leaf-on sprays are explicitly an illustration, not surveyed
botanical geometry. Shared municipal prototypes also represent multiple species;
this module does not pretend to identify every tree from its prototype. Better
leaf-on/species evidence remains needed for faithful individual canopies.

`docs/images/canopy-sprays-before-after.png` compares the actual `proto_8` geometry
before/after with identical CPU projection/light and a phone-sized inset. It is
not a live scene screenshot or acceptance. Regenerate it with:

```sh
node scripts/render-canopy-review.mjs
python scripts/render-canopy-review.py
```

The script retains the previous implementation by commit
`06279703d4e40e3b829bdc5424e8a28bb5d963a4` and reads the original compressed GLB.
Manager review must check the actual phone scene, oblique/rotated views, smaller
crowns, day/night lighting and city-scale cost. Bounds and geometry tests cannot
establish those outcomes. No photo texture, grain shader or alpha transparency
is added; the existing shared tree lighting and shadow material remains in use.

Integration order matters:

1. Existing source feature colouring.
2. `vegetationStyle.addModel(model)`.
3. `objectDetail.addModel(model)` and `treeBatches.addModel(model)`.

Remove in reverse order: tree batches, object detail, vegetation interpretation. The style restores original source geometry, disposes its derived prototypes, and never mutates retained source positions. Use the existing tree material so lighting and metro clipping remain shared. The source scene and batch tables remain intact for future reinterpretation.

Run `node tests/vegetation-style.test.mjs`. It uses native source position evidence, verifies exact envelope bounds, deterministic foliage geometry, unchanged original positions and instance matrices, trunk colour, and restoration/disposal. These tests do not prove the scene looks good. Cloud browser WebGL is unavailable; the manager must review actual neighbourhood/centre views before enabling this candidate publicly. This change does not fix missing private-garden trees, stale inventory, incorrect inventory dimensions or missing branch observations.
