# Status

Written by AI on 2026-10-25 by model Claude Opus 5.5. Kept under one page. Josh's words are in [requirements/steering.md](requirements/steering.md); the plan is Claude Fable's of 25 Oct.

**Goal.** A pixel-art isometric miniature of the whole gemeente Rotterdam, at the quality of isometric.nyc and tiny.london, fast on a phone, alive with live transit, simulated traffic, weather and a lit night. Built from one reusable 3D model of the city.

**Now: M0, the comparison.** On one neighbourhood, build the city model and three ways of showing it, judge them side by side, publish the best, and ask Josh to choose.

- Neighbourhood: **Historic Delfshaven around Aelbrechtskolk** (51.9103 N, 4.4475 E). Core block 1 × 1 km first, then out to Lloydkwartier and the Euromast.
- T1: the 3D model live in the browser with a pixel-art shader. Rotates freely.
- T2: the same shader rendered offline into an image pyramid, at one bearing and at four.
- T3: T2 repainted by ChatGPT's image tool, with everything that exists as data composited back from data.

**Owners.** Claude Opus 5.5: product, renderer and shader, pages, judging, publishing, talking to Josh. GPT-6.1 Sol (medium, Codex background runs): bounded backend pieces.

| Piece | Owner | State |
|---|---|---|
| Steering file complete | Opus | done |
| Buildings, bridges, trees, lamps → scene | Sol | running |
| Ground, water, rails, markings → scene | Sol | running |
| Renderer and pixel shader (T1) | Opus | next |
| Pyramid builder (T2) | Sol, after the shader | waiting |
| Paint pass (T3) | Codex image tool | waiting |
| Speed measurement script | Sol | waiting |
| Publish at 010.jjpcodes.com | Opus via Codex Sites | waiting |

**Where the plan was changed, and why.** None yet.

**Open decisions for Josh** (sent once, after M0 has pictures): which target or hybrid; rotation; what to draw where no façade photo exists; whether a model paint pass earns its place.

**Josh should look at next:** nothing yet.
