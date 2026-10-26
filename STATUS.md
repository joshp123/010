# Status

Written by AI on 2026-10-26 by model Claude Opus 5.5. One page. Josh's words: [requirements/steering.md](requirements/steering.md). Design: [requirements/RFC-001-components.md](requirements/RFC-001-components.md).

**Goal.** The whole gemeente Rotterdam as a living pixel-art miniature, true to the city in every object, better than tiny.london on truth, depth, light, craft, life and rotation, under a second on a phone.

**Where it is.** RFC step 1 (invariants, city-wide) and step 2 (look decided on one tile) run in parallel. Nothing new is published until the POC tile passes; the live site is still version 22 (Delfshaven, old look).

POC tile: **x90250_y436000, Aelbrechtskolk, Historic Delfshaven**. Candidate sheets in `renders/candidates/` (7.5 cm and 0.3 m, night, second bearing, 2026 aerial, tiny.london).

| Component | Owner | State |
|---|---|---|
| C1 sources | Sol | Delfshaven, centre, gemeente coarse done; vehicle photos and datasheets running |
| C2 scene | Sol | Delfshaven and centre (351 tiles) done; whole gemeente building; tree species and lamp types being joined |
| C3 perception, C4 buildings | Sol | first tier-1 elevation done (windows match where the photo shows them); tier-2 parts library and drop-in tile running |
| C4 vehicles | Opus | 3D models and sprite sheets; RET Citadis to be checked against 8+ current photos |
| C5 renderer | Opus | multi-scale to 7.5 cm, measured tones, view-relative sun, highlights, night from registers |
| C6 delivery | Opus | Worker with live feed and packed tiles built; not deployed |
| C7 living layers | Opus, Sol | live transit on real tracks and tunnels, OSM car and cycle graphs, weather, cutaway |
| C8 verification | Opus | candidate sheet, palette measurement, speed script; per-class checks in C3 |

**Measured compute.**
- Renderer: 75 s per km² per bearing on this MacBook for all six levels down to 7.5 cm. Built-up gemeente (about 100 km²) × 4 bearings × day and night ≈ 17 hours.
- Building assets: 30 to 55 s per image call. One call per tile-1 elevation; tier 2 batches many walls per call (being measured).
- Hosting: Sites caps a deployment at 256 MiB. Delfshaven at full depth is 243 MB. The Sites docs say nothing about price or quota for the R2 binding, so whole-city deep zoom on R2 is parked until the picture passes.

**Known problems.** Walls are 2018 photo texture until the building assets land; ground floors hidden by trees in the 2018 photos are interpreted and marked; tunnel depth is an assumed NAP −12 m; Rotterdam's marking register states no licence.

**Josh should look at next:** nothing new until the POC tile passes.
