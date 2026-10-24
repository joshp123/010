# Observed transit presentation

Written by AI on 2026-10-24 by model GPT-6.

`public/transit-view.js` renders the observation snapshots from `live-transit.js`, independently of city, UI and backend. It never moves a vehicle between reports. Mode colours distinguish bus, tram, metro, train and ferry; grey indicates stale, unknown-time, future-time or disconnected reports. Picking returns the full original report and presentation metadata, including the individual timestamp and freshness. The caller supplies the selected-vehicle UI.

```js
const transit = createTransitView({ project, requestRender });
scene.add(transit.group);
await transit.loadMetro(); // Explicit, replaceable BRT source subset, 8 KB gzip.
transit.update(snapshot);
transit.setView({ camera, span, viewportHeight });
const selectedReport = transit.pick(raycaster);
const corridor = transit.setCutaway({ enabled: true });
```

`project(latitude, longitude, offsetMetres)` returns a Three Vector3 at the intended local ground/rail surface plus the vertical illustration offset. `localPosition` is an alias if ground projection is unnecessary. The caller owns surface elevation and calls `update(lastSnapshot)` again when source surface availability changes. Observation latitude/longitude are never snapped to a railway. Vehicle sizes, heading and height are graphics: illustrative miniature bodies use the nearby source rail axis for metro, or use an upstream compass bearing when supplied. Missing bearings use a nearby source route axis when available, then a camera-facing symbol. The selection card distinguishes these cases; no heading is inferred from movement between reports. Bodies enlarge to remain legible when zoomed out; underground symbols retain their illustrative dimensions to fit the cutaway. No per-frame raycasts, animations or timers run here.

`setMetroData(data)` can replace the physical source without an HTTP request. `loadMetro(url)` rejects source fetch/decode failures; the caller can expose this separately from live feed health. `getCutaway()`, `statistics()` and `dispose()` provide the small integration/lifecycle boundary. Up to two instanced draw calls per populated mode and four combined cutaway meshes (floor/walls, track bed, sleepers and rails) are used. Report classification is cached across camera changes. A Node exercise of 500 reports across five modes measured about 0.21 ms per camera update; that is CPU plumbing evidence, not a browser frame-latency claim.

## Physical source and limits

Rebuild with `python3 scripts/build-metro-physical.py`. Input is the retained `source-data/transport-network.geojson.gz`, itself acquired from [Kadaster / PDOK BRT TOP10NL spoorbaandeel_lijn](https://api.pdok.nl/kadaster/brt-top10nl/ogc/v1/collections/spoorbaandeel_lijn). Output is `public/data/transit/metro-physical.json.gz`: standard geometry coordinates plus exact source IDs, physical-form categories and relative levels. Its embedded source SHA-256 is `2ffa63fe01878f4c05732c295a6587027ddbeceb927fdf38f68a8d399ab9b37d`. The retained network was municipality clipped and simplified by 1 metre. No extra simplification is applied by this extraction.

The subset contains 215 in-use metro/sneltram source features: 12 explicitly **in tunnel**, 39 bridge, four bridge-and-covered, six covered and 154 with no explicit physical form. Only the 12 explicit tunnel features create the underground display and clipping mask. Unclassified features and covered platforms are not assumed underground. This includes a short real tunnel near Hoek van Holland without putting its whole surface route underground. BRT's `hoogteniveau` is relative ordering, never metres; it is retained as metadata and does not set tunnel depth. BRT/municipality coverage and missing physical tags limit classification completeness.

A metro report is associated with the nearest retained source rail segment only if within 18 metres. Its plan coordinate remains unchanged. Only a nearest segment explicitly tagged tunnel puts its graphical body 12 metres below the supplied surface. This tolerance is a display association, not evidence of physical location accuracy. Operational metro positions are upstream reports, not independent underground GPS measurements. Missing/incorrect source classification can leave a report unclassified. The cutaway's constant 12-metre depth, 14-metre chamber width, 4.2-metre lower side walls and viewpoint-projected 16-metre opening are **illustrative**, not a surveyed profile. Surface and bridge report height also depend on the caller's graphical surface projection. Use the UI label “Metro cutaway · depth illustrated”.

## Clipping contract

`getCutaway()` returns `{texture, bounds, illustrativeDepthMetres, source, classification, sourceSegmentCount}` after source loading. The single-channel unsigned-byte DataTexture is bounded to the padded current viewport, at most 2048 × 2048 (4 MB). Its dimensions follow output pixel scale; it rebuilds when the viewport leaves its cached margin or scale changes by roughly 25%. The same texture and bounds objects are retained so material uniforms stay current. A fractional distance edge and linear sampling remove the former whole-city raster's coarse sawteeth. No extra global high-resolution texture is allocated. Exact export resolution updates the viewport mask through the same camera boundary.

In city surface materials, compute `uv = (worldPosition.xz - bounds.xy) / bounds.zw`. When enabled, discard only when uv is inside [0,1] and `texture(corridorTexture, uv).r > 0.5`. Do not sample outside bounds: clamped edge texels are not a world mask. The integrated materials cover sea, city surfaces, trees and prepared lamp graphics. The mask follows only explicit tunnel plan lines. A ray from the illustrated 12 m-deep tunnel floor toward the camera intersects the ground; that intersection defines the opening axis, with an 8 m half-width. This is an oblique sectional illustration, not a surveyed excavation. Camera rotation invalidates the cached mask as well as pan and zoom. The actual chamber floor stays on the source plan at 12 m depth, with 14 m display width and 4.2 m lower side walls. The upper earth is left open in the cut; it is not represented as solid vertical walls that obscure the train. These widths and heights are graphic dimensions, not measured tunnel engineering. Tunnel profile is not surveyed. No array of WebGL clip planes or stencil buffer is needed.

This BRT-derived physical subset is **CC BY 4.0**, credited to Kadaster / PDOK, BRT TOP10NL, with extraction/classification changes described here. It is separate from the ODbL GTFS shapes database. Independent presentation code is MIT. Existing source attribution and boundary licence notices remain applicable.

The cutaway includes fixed rails and sleepers following only those explicit source tunnel axes, at the same illustrated 12 m depth. Track gauge (1.5 m), rail width (0.22 m), bed width (3.6 m) and sleeper spacing (1.2 m) are graphic dimensions, not surveyed track or tunnel engineering. Each source axis gets one illustrated rail pair; this does not establish actual track count or station layout. The cutaway uses four draws, with no per-frame track construction. Vehicles retain their original reported plan coordinates.


## Rescue candidate and honest empty states

The earlier 40 m mask and 42 m flat floor erased an unnecessarily broad city stripe. The candidate uses the view-projected opening above and retains the original observed plan coordinates. The metro body now has three illustrated articulated sections, a silver/green palette, a window band and roof gaps. These are a legible metro symbol, **not** a verified model of the observed vehicle's rolling stock, carriage count, occupancy or lamp state. Neither a stale report nor missing observations produce a newly simulated metro. Underground bodies are omitted entirely while cutaway is disabled; ground holes cannot accidentally expose them.

Only one rail pair per retained source axis is drawn. The available BRT axis does not establish actual track count; adding twin tracks would invent geometry and place exact-coordinate reports between them. A future source interpretation can add individual track geometry explicitly. The candidate does not solve missing or imprecise underground reporting, source classification gaps, or full station architecture.

`statistics()` supplies `metroObservations`, `visibleMetroObservations`, `visibleUndergroundObservations`, `visibleFreshMetroObservations`, `visibleFreshUndergroundObservations`, and `cutawayMessage`. “Visible” here means the report's body centre is inside the camera frustum; it does not claim pixel-level visibility through every building or bridge. Use `cutawayMessage` in the transport panel while cutaway is enabled. A busy citywide feed of buses/trams must not imply there is a metro report in the current cutaway. Zero is explicitly reported as “No metro report in this cutaway view”.

The scene integrator should preserve overground bridge geometry/deck surfaces when applying the tunnel clipping mask. A tunnel below a bridge is not a reason to erase the bridge. This renderer does not own the city's materials.

`node tests/transit-view.test.mjs` checks classification, viewport counts, report-coordinate integrity, inactive-cutaway hiding, oblique aperture projection and rotation invalidation. Cloud WebGL is unavailable for this implementation run. Those tests do not establish visual quality; the manager must inspect the actual candidate locally, including a fresh report known to be within the viewport and a deliberately empty viewport. Do not infer success from a populated global feed badge.
