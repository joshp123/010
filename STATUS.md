# Status

Written by AI on 2026-10-26 by model Claude Opus 5.5. Kept under one page. Josh's words are in [requirements/steering.md](requirements/steering.md).

**Goal.** The whole gemeente Rotterdam as a pixel-art miniature at tiny.london quality or better, fast on a phone, alive: live transit, simulated cars and cyclists, weather, a lit night. Built from one reusable 3D model of the city.

**Direction (decided 26 Oct).** The 3D scene is the master asset. The shipped map is the procedural pixel pyramid at four angles, rendered from the scene. An image-model paint pass ships nothing unless a square passes per-building colour and material checks; it is off the site. Walls with no photo get a façade from facts only (height, BAG year and use). Nothing that exists as data is drawn by a model.

**Live at 010.jjpcodes.com.** Delfshaven to the Euromast (3.4 km²), four angles, day and night following Rotterdam's real sunset. Neighbourhood under work next: **the centre and Kop van Zuid** (RD x 89750–96500, y 434750–438000).

| Piece | Owner | State |
|---|---|---|
| Scene: buildings with BAG facts, M1 area | Sol | building |
| Scene: ground, rails, metro and train beds, M1 | Sol | building |
| Coarse model of the whole gemeente (1 km tiles) | Sol | building |
| Live transit feed (Worker, `/api/live`) | Sol | building |
| Car and cycle networks with heights | Sol | building |
| Look: photo flattening, palette, gardens, facts-only façades | Opus | done |
| Night: lamp register pools, real-window rooms by BAG use | Opus | done |
| Live layer: vehicles with depth occlusion, weather | Opus | built, waiting on feed and networks |
| First-view speed: inlined preview, preloads, service worker | Opus | done |

**Where I departed from the plan.** T2 uses the live renderer to capture exact windows, so one shader decides the look. Roofs take the 2026 aerial by planar projection. Vehicles are boxes placed in RD/NAP and hidden by depth tiles from the same render.

**Known problems.**
- Sites serves everything with `max-age=0`; the service worker caches per deploy. Uploads take minutes per 100 MB; the whole gemeente will need packed tiles.
- Rotterdam's road-marking register has no stated licence: kept, flagged.
- Façade imagery: Mapillary covers the centre well but its API needs a token (an account); not used. Commons photos are selective. No open source covers façades fully.
- Metro positions are drawn at street level until the cutaway uses tunnel depths.

**Josh should look at next:** https://010.jjpcodes.com on his phone, day and night (☀/☾).
