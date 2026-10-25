# Status

Written by AI on 2026-10-25 by model Claude Opus 5.5. Kept under one page. Josh's words are in [requirements/steering.md](requirements/steering.md); the plan is Claude Fable's of 25 Oct.

**Goal.** A pixel-art isometric miniature of the whole gemeente Rotterdam, at the quality of isometric.nyc and tiny.london, fast on a phone, alive with live transit, simulated traffic, weather and a lit night. Built from one reusable 3D model of the city.

**Now: M0, the comparison.** One neighbourhood, one city model, three ways of drawing it, judged side by side.

- Neighbourhood: **Historic Delfshaven around Aelbrechtskolk**, a 1 × 1 km block (RD x 89750–90750, y 435750–436750). The scene is also built out to Lloydkwartier and the Euromast (54 tiles); the pages show the 1 km block.
- **T1, live 3D**: the scene drawn in the browser with a pixel-art shader. Rotates freely. `?style=photo` shows the same scene unpixelated at full resolution.
- **T2, pixel pyramid**: the same shader rendered offline into image tiles, four bearings (35°, 125°, 215°, 305°). About 10 s of MacBook time and 4 MB per bearing per km².
- **T3, painted pyramid**: T2 repainted square by square by ChatGPT's image tool (54 squares, median 43 s a call, three runs in parallel, no limit hit), each square aligned back onto the render, overlaps blended, rails and road markings stamped back from data. One bearing (35°).

**Published** at 010.jjpcodes.com: home page is T2; `compare.html` links all three. Measured on the phone profile against the live site: T1 4.4 s to a picture and 13 s complete (30 MB), T2 1.5 s cold and 0.7 s warm before the inlining and service worker went in.

**Owners.** Claude Opus 5.5: renderer, shader, pages, judging, publishing. GPT-6.1 Sol (Codex background runs): scene builders, web bake, speed script, paint batches.

**Where I departed from the plan, and why.**
- T2 is not a separate renderer: it is the live renderer capturing exact windows, so T1 and T2 give the same pixels at the same view and one shader decides the look.
- Roofs come from the 2026 aerial by planar projection in the shader, not baked roof textures. Simpler; tall buildings show some roof lean.
- No whole-gemeente low-resolution render yet: the scene exists only for M0. It is the first job of M1.
- The plan's per-roof structure checks are not built; tonight's judgement is by eye against the aerial.

**Known problems.**
- Façades: 87% of façade area in the block has a 2018 photo, 72% across the full area. Elsewhere walls are plain.
- The painter changes façade colours (grey plaster often becomes brick), fills empty background with invented city or water, and sometimes shifts or warps a square by up to ~40 px. The compositor masks background, re-aligns squares and drops the few it cannot align; two paints of the same place differ in palette.
- Sites serves every file with `max-age=0`; a service worker now caches tiles per deploy.
- Rotterdam's road-marking register publishes no licence. The markings are used and flagged.
- 3% of non-building ground has no valid height in the municipal model; a flat underlay at street height fills it.

**Open decisions for Josh**: sent once, with links and the comparison table.

**Josh should look at next:** the comparison page on 010.jjpcodes.com once published.
