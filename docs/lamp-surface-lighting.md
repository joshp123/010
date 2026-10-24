# Fixture surface lighting

Written by AI on 2026-10-24 by model GPT-6.1 Sol.

Published and checked on 010.jjpcodes.com on 2026-10-24. Existing ground-pool sprites do not illuminate nearby walls or container surfaces. The renderer adds warm surface illumination from the same retained fixture anchors, without runtime light objects or source geometry changes. It is enabled by the shared scene renderer. Current intensity gain is 0.55; the initial 1.4 gain was rejected after actual neighbourhood views showed excessively bright continuous lower façades.

The preparation reads all 104,728 native and 21,904 supplementary head anchors from their existing standard GLBs. Native anchors are the highest transformed source prototype vertex, not measured optical centres. Supplementary anchors retain AHN-supported upper hardware at 69 registered fixtures and illustrative 10 m heads elsewhere. Original source, licence and height evidence remain in the corresponding lamp manifests and [supplementary source documentation](supplementary-lamps.md). Each input GLB hash is recorded in the field manifest. Nothing is acquired or hand-placed.

Ordinary light reach is an illustrative 18 m. The 69 supported tall heads use 1.4 times supported head height above terrain, bounded to 24–70 m. Every 8 m lookup cell retains two candidate heads, ranked by horizontal distance divided by reach. The query considers nearest ordinary heads and tall heads separately so a nearby ordinary fixture cannot conceal a farther high mast. Source positions remain unchanged; Float16 lookup offsets are an approximation, with a maximum observed component error of 0.0313 m in the complete build.

The surface shader evaluates continuous three-dimensional falloff, upward direction toward the head, and surface-facing response at each fragment. It adds warm diffuse-colour-scaled radiance only at night. Colour, intensity, range, falloff and operation remain illustrative. There is no surveyed beam direction, shadow/occlusion solution or operational status. Intervening structures can therefore receive light through another object. Two retained heads per 8 m cell can also change at cell boundaries; the visual comparison must assess this approximation rather than assuming it is invisible.

The module applies only to buildings, industrial structures, bridges and tanks in the current renderer. Existing ground pools, windows and daytime appearance stay on their current paths. No source vertex, index, material classification or metadata is modified.

## Reproduction and integration

From the project root, reproduce the complete source-derived fields:

```sh
.devenv/profile/bin/python3 scripts/build-lamp-surface-field.py \
  --output public/data/lamp-surface-lighting
```

The default visits every tile touched by a source head’s influence plus the lookup-cell half diagonal, including influence across tile boundaries. The manifest identifies complete source-influence coverage and lists all prepared tiles. It distinguishes two prepared but truly empty tiles from nonempty field files. A runtime atlas tile outside complete source-influence coverage is empty, not unprepared.

For a bounded QA reproduction, use a separate output:

```sh
.devenv/profile/bin/python3 scripts/build-lamp-surface-field.py \
  --output work/lamp-surface-local-qa \
  --bounds -35000 -7000 -30000 -2000 \
  --bounds -5000 -2000 0 3000
```

Bounds use the existing local east/up/south frame; each group is minimum X, minimum Z, maximum X, maximum Z. These rectangles select QA coverage only. They are not an acceptable municipality-wide shipping selection. Preparation uses fixture heads from the entire source, including heads outside each selected tile.

`createFixtureSurfaceLighting({ enabled, night, requestRender })` in `public/fixture-surface-lighting.js` returns `apply(material)`, `setView(camera)`, `prepareView(camera)`, `diagnostics()` and `dispose()`. Apply it to the four shared city materials after their creation; call `setView` after camera matrices or night lighting update. Export calls `await prepareView(captureCamera)` for its final aspect ratio before rendering, then restores the live camera with `setView`. Preparation catches request errors and returns; it does not loop waiting for success. The module wraps the existing shader hook. The disabled path allocates no textures, fetches no fields and changes no shaders. With lighting enabled, daytime still fetches neither manifest nor fields; an actual Hoek day load confirmed zero such requests. Switching to night starts preparation.

A fixed 4×4 atlas covers 4,096 m per side. Camera corner rays intersect the ground plane to measure the actual ground footprint; screen span alone does not establish coverage. Illumination fades globally as the largest footprint extent increases from 2,800 to 3,500 m, before the atlas can miss visible ground because of tile alignment. A 64 m border fade avoids a hard atlas edge. This keeps detailed surface lighting bounded at close views; the existing overview lighting remains at wider scales. Bounded QA manifests report unprepared atlas tiles separately from true empty tiles. The complete field has no arbitrary partial rectangles, but fixture registry gaps still remain dark.

At a changed atlas origin, the module fetches at most 16 compressed tiles after 150 ms without another camera update, decompresses once and copies their half floats into the fixed textures. An obsolete request is aborted. There is no per-frame fixture search, geometry traversal or cache framework. Normal HTTP caching remains available. CPU arrays and GPU textures are separate allocations; pending decoded tiles temporarily add memory.

## Measurements and acceptance

The complete source-derived build produced 317 nonempty files totalling 9,134,458 gzip bytes, plus a 144,285-byte manifest (35,073 bytes gzip locally), in 7.79 seconds. Its source-influence selection covers 319 tiles; two have no relevant lookup cells. The preceding two-area QA build produced 57 files, 1,765,072 gzip bytes, in 1.53 seconds; those outputs are retained under ignored `work/lamp-surface-bounded-first-candidate/`. Every decoded tile is 262,144 bytes; all hashes, finite half floats and lengths were checked. Fixed GPU texture storage is 4,194,304 bytes; matching CPU backing arrays occupy another 4,194,304 bytes. Up to 4,194,304 decoded tile bytes can be pending during an atlas update. Two texture reads and two bounded light evaluations are added per eligible night surface fragment. No draw calls or Three.js lights are added. These counts do not establish actual GPU frame cost.

`diagnostics()` records requested ground footprint, view strength, atlas origin, available/missing tiles, pending state, errors, cumulative compressed bytes, current decoded bytes and atlas copy CPU time. Parent integration must compare actual map day/night, supported tall masts and ordinary neighbourhoods, with matching rendered geometry and device/view/cache conditions. Actual local IAB checks: the port view loaded 15 fields, 129,147 compressed bytes, with a 1.3 ms atlas copy; Hoek night loaded 13 fields, 297,775 compressed bytes, with no missing prepared coverage or errors. These are single-view transfer/preparation measurements, not end-to-end speedups or physical GPU timing. The 0.55 close neighbourhood and port views show restrained surface response without an obvious 8 m lookup pattern in those stills. Public verification is recorded below.

### Browser comparison, 2026-10-24

Parent inspected actual in-app-browser captures at 1440×900 (2880×1800 drawing buffer). The initial gain of 1.4 produced excessive continuous bright lower façades in Delfshaven, despite useful local highlights at port masts. Shared gain was reduced to 0.55; no location-specific tuning. The close neighbourhood comparison preserves a clearer distinction between illuminated windows and nearby walls. This shared setting was accepted after the broader checks below.

Evidence under ignored `work/visual-qa/`: `surface-lighting-baseline-port.jpg`, `surface-lighting-candidate-port.jpg`, `surface-lighting-baseline-neighbourhood.jpg`, `surface-lighting-candidate-neighbourhood.jpg`, `surface-lighting-candidate-neighbourhood-close.jpg`, `surface-lighting-restrained-neighbourhood-close.jpg`. Port location: 51.955,4.010,span550,bearing35; neighbourhood:51.9072,4.449,span700 and200,bearing35. All comparisons use manual night. Geometry readiness was complete with zero failures. Port field transfer129,147bytes/15tiles; neighbourhood862,467bytes/16tiles. Atlas copying took1.3ms and1ms respectively; these are CPU copy measurements, not GPU frame or physical-device performance.

Full source-relevant coverage has now been generated. Restrained port close-ups, a pan and rotation, Hoek day/night, and landscape/story exports were inspected in the in-app browser. Daytime requested no lighting assets; night loaded 13 Hoek tiles (297,775 bytes) with no missing prepared coverage or errors. Landscape export was copied and the actual 3840×2016 PNG opened; its caption contained the current Hoek view and @jjpcodes. The browser connection restarted during the first clipboard check, yielding stale clipboard evidence; after reconnecting and refreshing, the copy matched the current view. The stale image is not acceptance evidence. A separate images-only review found no concrete visual regression in the inspected scenes. These checks do not establish all-device performance or physical photometric accuracy. Public verification passed on 010.jjpcodes.com: 13 Hoek fields loaded (297,775 bytes), zero missing fields or lighting errors, and complete geometry readiness with zero refusals. First buildings appeared in 4.68 seconds and detail settled in 9.33 seconds in this ordinary-cache navigation; this is not a controlled cold-cache comparison. Public screenshot and diagnostics: `work/visual-qa/published-v8-hoek-night.jpg` and `published-v8-lighting.json`.

Release: Sites version 8, source `63b502e55d4c1273d04c4b775d9c0df38c23670e`, deployed 2026-10-24 05:25:21 UTC. Deployment `appgdep_6adc41258d988191b422609bfaf464ac`. Archive contains 4,020 files, 218,306,560 expanded tar bytes; no obsolete bounded candidate assets.
