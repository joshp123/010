# Simulated road traffic

Written by AI on 2026-10-24 by model GPT-6.

This is **decorative simulation**, separate from observed transit. Cars are not live reports. Speeds, vehicle counts, colours and choices at junctions are invented. There is no traffic prediction, signal model, collision model or claim about current legal access/closures.

## Source and rebuild

[Rijkswaterstaat's Nationaal Wegenbestand, served free by PDOK](https://api.pdok.nl/rws/nationaal-wegenbestand-wegen/ogc/v1/), supplies actual road centre lines, source junction IDs and travel directions. [PDOK states CC0, monthly updates, no cost and no authentication](https://api.pdok.nl/rws/nationaal-wegenbestand-wegen/ogc/v1?f=html). [NDW's road-class documentation](https://docs.ndw.nu/handleidingen/nwb/nwb-basisstructuur/baansubsoort/) and [direction documentation](https://docs.ndw.nu/handleidingen/nwb/nwb-basisstructuur/overige-attributen/) define the filtering and graph directions. The checked service edition was updated to 2026-10-05.

Run `python3 scripts/build-traffic.py --download` in a Python environment with Shapely and pyproj. `--download` acquires/resumes municipal pages in ignored `work/data-cache/traffic`; existing pages are reused, so archive/move that directory before deliberately refreshing the source edition. Without `--download`, rebuilding uses retained pages. All 42 raw HTTP responses remain on the SSD in that ignored directory, with exact hashes in `provenance.json`.

The `gme_naam=Rotterdam` source selection has 41,131 features. The build selects motor-road classes and known H/T/B directions, excluding footpaths, cycleways, ferries, dedicated transit lanes, parking links and emergency-only connections. It retains 28,924 selected source features in `nwb-roads.geojson.gz`, including original geometry, relevant properties and IDs. The complete original attributes remain in the ignored raw responses. It clips geometry to the retained exact municipality polygon, subtracts retained BRT road polygons explicitly tagged `in tunnel` with a 2-metre buffer, and discards resulting pieces shorter than 8 metres. Subtraction avoids graphical cars driving across water above mapped tunnels; missing BRT tunnel geometry remains a limitation. There is no line simplification or invented joining line.

`public/data/traffic/roads.pb.gz` is the replaceable runtime data contract defined by `roads.proto`: 27,218 road pieces, 192,480 vertices, 2,440 km and 1,188,274 bytes gzip. Coordinate quantisation is 1e-7 degrees. City, Hoek van Holland and the port are included. The municipal selection excludes neighbouring municipalities; crossings at the border terminate rather than continuing through omitted places. This is public named/numbered-road coverage, not every private port/service access.

Original junction IDs survive only at unchanged original endpoints. Clipping-created endpoints have no junction connection. Runtime permits a transition only through the same source junction ID with projected endpoints within 0.5 metres and allowed H/T/B travel direction. It never connects merely crossing lines, snaps disconnected roads together or cuts a curved source line with a straight shortcut. Immediate reversals, including different edges that double back at an angle greater than 120°, are excluded. Continuing ahead is weighted over turns. Cars reaching dead ends shrink out over their final 8 metres; replacements enter near the viewport edge. A view change seeds the newly visible roads. Junction turn restrictions are not modelled.

The NWB input is **CC0 1.0**. Boundary clipping and the separate BRT tunnel mask use **Kadaster / PDOK CC BY 4.0** sources, credited in the application notice. Those geometry modifications and their source hashes are recorded in `provenance.json`. Independent preparation/renderer code is MIT.

## Renderer integration

```js
const traffic = createSimulatedTraffic({ project, requestRender });
scene.add(traffic.group);
traffic.setView({ camera, span, viewportHeight });
await traffic.load();
// Parent's animation loop, seconds:
const moving = traffic.advance(performance.now() / 1000);
traffic.setPaused(true);
traffic.setEnabled(false);
```

`project(lat, lon, offsetMetres, {source:'NWB', roadId, roadClass})` supplies the intended local graphical road height, including bridges where source surface geometry is available. A `localPosition` alias is accepted. The layer does not establish measured vertical alignment from two-dimensional NWB geometry. `refreshProjection()` rebuilds source positions when the caller's surface data changes; avoid doing that every frame. The parent owns the “Simulated traffic” label, animation scheduling and page-visibility pause.

`setRoads(decodedNetwork)` replaces the data without fetching. `load(url)` explicitly fetches/decompresses/decodes and rejects actual failures. `decodeTrafficRoads(bytes)` accepts decompressed protobuf. `statistics()` reports simulation status, visible/source road counts, car count and draw calls. `dispose()` releases the geometry/materials/instance buffers and detaches the group. There are no timers or dependencies beyond the existing Three.js.

Frustum culling selects source roads on camera changes and retains currently visible cars. Only active viewport cars move each frame. Default density is six graphical cars per kilometre of selected source road, capped at 320; both are configurable. At spans above 6.5 km the layer hides and `advance()` returns false. Two instanced draws cover all cars. Original source polylines remain the route. Two-way cars use an illustrative 1.15 m right-hand offset, tapered to zero over 8 m at each surveyed junction so transitions do not jump between lanes. One-way lines stay centred. These are not surveyed lane positions or verified lane widths. Heading turns are rate-limited, turn approaches brake, and same-edge following gaps plus local junction reservations reduce overlaps. This is not a complete collision/signal model. HR means main carriageway, not motorway: without a speed-limit source all HR cars use a conservative illustrative urban cruise speed. Cars remain 4.2 m long rather than growing with zoom. Vehicle dimensions and projected height are illustrations. Pausing and visibility changes reset the time baseline, so resuming does not catch up through an unattended interval.

Actual decoded network checks exercised centre, Hoek, Maasvlakte and southern views, 20 seconds of junction-following motion, source-polyline placement, pause/resume and distant-view hiding. Node measured about 32 ms decode, 40 ms projection/setup and 0.14 ms per 320-car simulation update using a simple local projection. These are CPU adapter measurements, not browser frame-latency or visual acceptance. Parent integration still needs actual city rendering/bridge-height inspection.

## Rescue motion changes, 2026-10-24

`node tests/traffic-motion.test.mjs` checks right-hand separation, junction taper, different-edge reversal rejection, HR semantics, suspended-frame limits, pause/resume and preservation of positions through surface reprojection. It also decodes and advances the actual 27,218-road dataset for 200 updates and checks finite transforms. Reprojection now retains each vehicle's route, progress, heading and pending turn instead of recreating the whole population every time detailed ground finishes loading. Frame travel is bounded to 100 ms of simulation so stalled tabs do not catch up with long jumps.

These checks are not visual acceptance. The implementation cloud browser could not create a WebGL context, so the revised lane placement, junction animation, bridge alignment and vehicle appearance require the manager's rendered review. Dead-end shrink-out is a visual compromise, not a claimed physical exit. Cars may still overlap across unmodelled junction approaches.

## Dedicated cycling paths

Cyclists use a separate NWB FP (fietspad) network, never the motor-road graph. Run `python3 scripts/build-cycling.py --download` for initial acquisition/resume, or omit `--download` to rebuild from retained `nwb-cycleways.geojson.gz`. The download resumes the shared municipal page cache and does **not** rebuild motor-road assets. Archive/remove the cache when deliberately refreshing its edition. The retained 2026-10-24 snapshot contains 9,274 FP features; clipping/exclusions produce 8,060 runtime pieces covering 735.2 km, in a 369,013-byte gzip payload. Centre, Hoek and Maasvlakte coverage is checked. 413 selected features have unspecified directions. The selected FP source retains original geometry and all attributes; `cycling-provenance.json` records source, boundary, tunnel-mask and output hashes.

Preparation clips to the exact municipality, removes known BRT road tunnels, excludes FP records with negative `rel_hoogte`, and preserves original junction IDs only at unchanged endpoints. It uses the existing `roads.proto` contract in `public/data/traffic/cycleways.pb.gz`. H/T/B directions survive. Where the source says O/unknown, graphical riders travel both ways: that is an explicit simulation assumption, not a statement about legal cycle directions. Unmapped tunnels and missing source heights remain limitations. Shared-street cycling and links across non-FP gaps are omitted; this is not a full bicycle routing service.

Create a second layer with `createSimulatedTraffic({ project, requestRender, bicycles: true, maximumVehicles: 160, vehiclesPerKilometre: 20, maximumSpan: 2600 })`. Its default `load()` reads the cycleways file; apply the same view, pause, projection-refresh and dispose lifecycle as cars. `statistics()` exposes `cyclists` and `vehicles`; its `cars` count remains zero. Four instanced draws produce rider bodies/heads, low-poly wheels and frames/pedalling legs. Rider dimensions, clothing, cadence, a 4.2 m/s cruise speed, and about 0.4 m lateral separation are illustrative. No cyclist is a live observation. Main UI must say cars and cyclists are simulated.

The lane normal is interpolated over up to 3 m at each polyline bend (bounded to half the segment length), avoiding abrupt lateral jumps while keeping the route position on the surveyed centreline. Surface reprojection preserves all route progress and cannot reseed vehicles in the middle of the view. These are geometry/motion changes awaiting manager visual review; numerical tests are not that review.
