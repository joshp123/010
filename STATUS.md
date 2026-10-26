# Status

Written by AI on 2026-10-26 by model Claude Opus 5.5. Kept under one page. Josh's words are in [requirements/steering.md](requirements/steering.md).

**Goal.** The whole gemeente Rotterdam as a pixel-art miniature at tiny.london quality or better, fast on a phone, alive: live transit, simulated cars and cyclists, weather, a lit night. Built from one reusable 3D model of the city.

**Direction (decided 26 Oct).** The 3D scene is the master asset. The shipped map is the procedural pixel pyramid at four angles, rendered from the scene. An image-model paint pass ships nothing unless a square passes per-building colour and material checks; it is off the site. Walls with no photo get a façade from facts only (height, BAG year and use). Nothing that exists as data is drawn by a model.

**Live at 010.jjpcodes.com.** Delfshaven to the Euromast, four angles, day and night. **Next deploy: the centre and Kop van Zuid** (Delfshaven to Kralingen, Centraal to the Wilhelminapier, 22 km²) with real trams, metros, buses, trains and ferries on their tracks, simulated cars and cyclists, weather, a metro cutaway and a share button.

| Piece | Owner | State |
|---|---|---|
| Scene, centre and Kop van Zuid: buildings with BAG facts, ground, rails | Sol | done |
| Coarse model of the whole gemeente (1 km tiles) | Sol | done, not yet rendered |
| Live transit feed (Worker, `/api/live`) and route geometry with tunnel depths | Sol | done |
| Car and cycle networks from OpenStreetMap, one connected graph each | Sol | done |
| Look, night, facts-only façades, living layer, share, cutaway | Opus | done |
| Pyramids for the centre: four angles, day with depth, night | Opus | rendering |

**Where I departed from the plan.** T2 uses the live renderer to capture exact windows, so one shader decides the look. Roofs take the 2026 aerial by planar projection. Vehicles are boxes placed in RD/NAP and hidden by depth tiles from the same render.

**Known problems.**
- Sites serves everything with `max-age=0`; the service worker caches per deploy. Uploads take minutes per 100 MB; the whole gemeente will need packed tiles.
- Rotterdam's road-marking register has no stated licence: kept, flagged.
- Façade imagery: Mapillary covers the centre well but its API needs a token (an account); not used. Commons photos are selective. No open source covers façades fully.
- Tunnel depths are a stated NAP −12 m, not surveyed. Ferries at NAP 0 without tide.
- Cloudflare allows 20,000 files per deployment; depth tiles are packed four to a file. The whole gemeente will need packed tiles.
- The networks came from NWB at first and missed a quarter of the streets; rebuilt from OpenStreetMap.

**Josh should look at next:** https://010.jjpcodes.com on his phone, day and night (☀/☾).
