# Status

Written by AI on 2026-10-26 by model Claude Opus 5.5. One page. Josh's words: [requirements/steering.md](requirements/steering.md). Design: [requirements/RFC-001-components.md](requirements/RFC-001-components.md).

**Goal.** The whole gemeente Rotterdam as a living pixel-art miniature, true to the city in every object, better than tiny.london on truth, depth, light, craft, life and rotation, under a second on a phone.

**Where it is.** RFC step 1 (invariants, city-wide) and step 2 (look decided on one tile) run in parallel. Assets are being made for all 16 tiles of the 1 km² Delfshaven block for its first publication. Sheet 09's cold review failed (roofs, markings, trees, cyclists; verdict beside the sheet). The live site is still version 22 (Delfshaven, old look).

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
- Building images: 836 image calls in a sustained hour (10 parallel Codex runs, no errors, no rate limits, free route). The test tile needs 1.03 calls per building, 4.5 s per building at that rate. Whole gemeente: 206,524 buildings, 53.8 km² of photographed façade. Scaled by façade area about 136,000 calls, **about 165 hours**; scaled by building count about 255 hours. A 20-run test is measuring whether more parallel runs raise the rate.
- Test tile walls: 8.5% of wall area checked against a photo, 91.5% interpreted (31% redrawn from a photo, 53% composed from parts, 16% plain material). Roofs: 91% checked.
- Renderer: 1 km² block, one bearing, all six levels: 114 s day. Built-up gemeente (about 100 km²) × 4 bearings × day and night ≈ 17 hours.
- Hosting: the 1 km² block at four bearings, day and night, WebP quality 80, is about 225 MB, under Sites' 256 MiB cap.
- Speed (trial build of the block, local Worker, phone profile 20 Mbps 80 ms, 4× CPU): 578 ms cold, 148 ms warm at 7.5 cm; desktop 156 ms cold, 19 ms warm.

**Known problems.** Walls are 2018 photo texture until the building assets land; ground floors hidden by trees in the 2018 photos are interpreted and marked; tunnel depth is an assumed NAP −12 m; Rotterdam's marking register states no licence.

**Josh should look at next:** nothing new until the POC tile passes.
