# Observed transit presentation

Written by AI on 2026-10-24. This is an unaccepted rescue candidate; manager visual review remains necessary.

`public/transit-view.js` renders snapshots from `live-transit.js`. It never moves a vehicle between reports. Grey bodies/roofs and explicit status distinguish older/disconnected reports. Picking returns the original report, timestamp, freshness and presentation metadata. Missing reports do not create simulated metros. Road traffic and cycling are separate simulations.

```js
const transit = createTransitView({ project, requestRender });
scene.add(transit.group);
await transit.loadMetro();
transit.update(snapshot);
transit.setView({ camera, span, viewportHeight });
const corridor = transit.setCutaway({ enabled: true });
```

`project(latitude, longitude, offsetMetres, context)` supplies local surface elevation. Tunnel samples use `{source: "metro-section", preferGround: true}` to exclude bridge decks. The clipped local rail geometry is sampled at intervals no longer than 8 m; distant source endpoint heights are not interpolated across the section. Reports and sections refresh when observation/surface updates arrive. `section` diagnostics expose source-tagged ground samples, surface/floor elevation ranges, geometry bounds and report-versus-section elevation differences.

Raw report coordinates remain unchanged in the snapshot and picking result. A separate `presentation.representedPosition` records the approximate displayed coordinate, method and horizontal offset when a report is aligned to a mapped track. No interpolation, extrapolation or movement between observations is implemented.

Map-matched underground symbols use the selected source track axis. Other symbols use upstream bearing when supplied, then the source rail axis, then a nearby GTFS route axis; camera-facing is the final symbol fallback. The selection metadata distinguishes these. Bodies enlarge at distant scales for other modes; underground bodies keep their illustrated dimensions. The silver/green metro is a **symbol**, with three illustrative articulated sections and windows, not a verified model of an operator's carriage count, livery, occupancy or lamp state. No underground bodies are drawn while cutaway is disabled.

## Physical source

Rebuild with `python3 scripts/build-metro-physical.py`. Input is retained `source-data/transport-network.geojson.gz`, acquired from [Kadaster / PDOK BRT TOP10NL spoorbaandeel_lijn](https://api.pdok.nl/kadaster/brt-top10nl/ogc/v1/collections/spoorbaandeel_lijn). Output is `public/data/transit/metro-physical.json.gz`, with exact source IDs, physical categories and relative levels. Embedded source SHA-256: `2ffa63fe01878f4c05732c295a6587027ddbeceb927fdf38f68a8d399ab9b37d`. The earlier network transform clipped to the municipality and simplified by 1 m; this extraction adds no simplification.

The subset contains 215 in-use metro/sneltram features: 12 explicit tunnel features, 39 bridges, four bridge-and-covered, six covered, and 154 without an explicit physical form. Only explicit tunnels create underground sections. A short real tunnel near Hoek is included without treating its entire surface route as underground. Relative `hoogteniveau` ordering is not metres and does not set the graphical depth.

A report associates with a retained rail segment within 18 m. When a nearby GTFS route-shape axis is available (within 40 m of the raw fix), candidate physical axes must agree within about 20 degrees, ignoring travel direction (`abs(cos(angle)) > 0.94`). The nearest compatible candidate is selected. Only an explicit tunnel classification creates an underground symbol.

The approximate represented position projects onto that physical axis when route-axis agreement is available, or when the raw fix is within 5.5 m of the nearest axis. Otherwise the report remains an amber position marker at its raw surface coordinate, with an explicit track-offset status. This is **local route-axis approximation, not trip-aware map matching**: it does not identify a particular service path through branches, infer stop-event progress, establish travel direction or resolve parallel tracks. Underground operator reports are not automatically independent GPS fixes. Missing classification, route-shape ambiguity and imprecise observations remain gaps; no track-level accuracy is claimed.

## Bounded local section

Manager review rejected both the initial 42 m pale trench and the later narrow, displaced rail strips. They lacked depth hierarchy, cut through long stretches of the city and did not guarantee a legible reported train. The rejected narrow version also sampled city clipping by world XZ at every height, so an opening in the ground could leave tall building faces blocking the same view ray.

The current candidate opens a **single selected source feature within a 38 m radius**, giving a maximum 76 m straight section. It chooses an in-viewport tunnel-classified metro report, prioritising fresh connected reports, then proximity to viewport centre. Without one, it uses the nearest visible source tunnel. It never adds a train to fill an empty section. Only segments belonging to the selected BRT source feature are clipped to this circle; nearby crossing features are excluded. Only the selected report is rendered underground in the section. This prevents the earlier union of nearby tunnels from making large T-shaped excavations. Source feature endpoints or bends can make the section shorter or curved.

The dark floor stays 12 m below the source surface. The far side has a full-depth warm earth face, with a cooler 4.2 m concrete lower chamber, 2 m horizontal ground shelves and lower maintenance ledges. These distinguish surface, soil and chamber without inventing geological strata. The near face is intentionally removed to reveal the interior. Both section ends have soil/concrete faces. Connected internal source points create no caps; open source-feature endpoints and clipped section endpoints do. The far side and both ends have 2 m wide horizontal ground shelves and exterior earth faces, giving the cut a finite thickness rather than a vertical fin. The camera-near long face remains open so the train can be seen. The chamber remains at most 76 m long; its end shelves extend another 2 m at each end. Chamber width is fixed at 6 m; an offset report never widens the excavation. These widths, strata/materials, depth and wall construction are **illustrative, not surveyed engineering**.

One rail pair is drawn per source axis: illustrated gauge 1.5 m, bed width 3.6 m, rail width 0.15 m, sleeper spacing 1.2 m. BRT does not establish individual track count. Inventing a second track would not fix the source limitation and could place a report between invented rails. Full station architecture is not implemented.

## Clipping integration

`getCutaway()` returns stable `texture`, `bounds` and `projection` objects plus source metadata. `projection` is `(viewDirection.x/viewDirection.y, viewDirection.z/viewDirection.y)`. Project every city fragment's view ray to the local y=0 plane before sampling:

```glsl
vec2 rayPlane = worldPosition.xz - worldPosition.y * metroCutawayProjection;
vec2 uv = (rayPlane - metroCutawayBounds.xy) / metroCutawayBounds.zw;
if (insideBounds(uv) && texture(metroCutawayMask, uv).r > 0.5) discard;
```

The CPU mask rasterises the projected triangles of the actual floor, earth, concrete and ground-shelf faces. It no longer dilates a swept centreline into a capsule: that earlier aperture removed city pixels beyond the rectangular section, exposing the scene background as pale rounded end fins. Every aperture pixel now has a section face behind it, with a conservative one-texel boundary inset to avoid unsupported edge pixels at finite raster resolution. The ground and ordinary city fragments in those view rays are clipped together. For buildings, `metro-city-cut.js` adds bounded whole-feature excision: source `_batchid` groups (or appearance BAG groups across material primitives) whose world bounds intersect the physical footprint or projected reveal are removed as whole features, leaving only faint original foundation edges within 0.6 m of each feature base, at 12% opacity. This avoids isolated roof/facade fragments abutting the chamber. Selection uses conservative feature bounds, so it can include a building whose bounds cross the section without a triangle crossing it. The earlier full roof/facade ghost cages were rejected as clutter and removed. The remaining foundation lines write no depth. Ground and the surrounding unselected city remain opaque. This is an illustrative sectional view; no missing building architecture is generated. The mask is at most 1024×1024; its extent is the small section, not the viewport or municipality. Camera rotation, substantial anchor movement, zoom and feed/surface refresh invalidate it. The seven section meshes are rebuilt only at those boundaries, with no per-frame construction.

The city integration must preserve overground bridge geometry/deck surfaces. A tunnel under a bridge is not a reason to erase the bridge. The scene passes visible building models to `metroCityCut.update(models, transit.getSectionGeometry())` after source reconciliation and projection refresh, then marks shadows dirty when selection changes. Feature bounds are cached until geometry/world transforms change; unchanged frames do not scan vertices. Turning the section off restores all feature attributes. The shared cutaway shader reads `_metroExcised` (default zero) and the same rule applies to city shadow-depth materials. This renderer does not own city model loading. The section uses depth-tested geometry; no train is painted above an occluding bridge or fabricated to satisfy the count.

## Empty states and finding an actual report

`statistics()` returns citywide `metroObservations`, viewport `visibleMetroObservations` / `visibleFreshMetroObservations`, and active-section `visibleUndergroundObservations` / `visibleFreshUndergroundObservations` while cutaway is enabled. These are geometric counts, **not proof of pixel-level visibility**. Do not derive cutaway population from the overall bus/tram/rail feed badge.

`cutawayMessage` and `cutawayShortMessage` distinguish a fresh report at an approximate track position, an unsupported off-track report, an older/unverified report that is not live, and no report in the section. The application should show it persistently but compactly while cutaway is enabled, including when View is closed.

`metroFocus` is null or an original tunnel-classified report's `{id, latitude, longitude, label, observedAt, freshness, sourceConnected}`. It prefers fresh connected reports; an older report is an explicit fallback. “Find reported metro” may navigate to those coordinates at a close span (220 m), but must say “older” when the target is stale. Navigation changes the camera, never the observation. `metroFocusCandidates` supplies the ordered candidates with the same raw coordinates plus `inSection` and `presentationState` (`train` or `marker`). The UI can cycle through reports even when the current section already contains a report; report counts must not suppress this action.

## Verification and attribution

`node tests/transit-view.test.mjs` checks classification, busy-feed/empty-section distinction, stale-only status, report integrity, bounded section geometry, actual full-depth earth faces, disabled-cutaway hiding, ray-plane aperture projection and rotation invalidation. `node tests/metro-occlusion-render.mjs` also produces a CPU ray-rendered PPM using the actual section meshes, vehicle instances and projected clipping mask. A synthetic fixture puts tall buildings at both section ends and a crossing tunnel directly under an offset report; the test checks route-axis selection, raw-coordinate retention, exclusion of the crossing excavation, visible train pixels through the masked buildings, and zero cleared pixels without a section surface behind them. In the retained synthetic comparison the former capsule had 2,072 unsupported pixels; the exact triangle aperture has zero, with the same 1,444 train pixels. It does not execute production lighting/window shaders or validate the actual city scene. Cloud WebGL is unavailable in this implementation environment. Tests are supporting evidence only: manager must inspect a known fresh in-section report, an older-only report and an empty section in actual day/night views before acceptance.

The BRT-derived subset is **CC BY 4.0**, credited to Kadaster / PDOK, BRT TOP10NL, with changes described here. It is separate from the ODbL GTFS shapes database. Presentation code remains MIT. Preserve source and municipal-boundary attribution.

`node tests/metro-city-cut.test.mjs` verifies feature grouping, unchanged source positions, unrelated features retained within a combined mesh, BAG primitives treated together, cache/lifecycle behavior and ghost depth writes disabled. `python scripts/build-metro-source-fixture.py` reconstructs exact retained native building triangles around the rejected B view in a rigid local frame for the CPU renderer. `METRO_SOURCE_FIXTURE=/tmp/metro-source-buildings.json METRO_GHOST=1 node tests/metro-occlusion-render.mjs` exercises that geometry. The source fixture now includes retained native BGT terrain and uses vertical intersections with those triangles for the section ground. Native ground triangles containing values below −30 m are excluded as invalid-height evidence, while source building triangles are unchanged. It still uses a test report and simplified constant materials; it is not a live feed capture or production lighting acceptance. Actual browser day/night review is still required.
