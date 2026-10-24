# Simulated road traffic

Written by AI on 2026-10-24 by model GPT-6.

This is **decorative simulation**, separate from observed transit. Cars are not live reports. Speeds, vehicle counts, colours and choices at junctions are invented. There is no traffic prediction, signal model, collision model or claim about current legal access/closures.

## Source and rebuild

[Rijkswaterstaat's Nationaal Wegenbestand, served free by PDOK](https://api.pdok.nl/rws/nationaal-wegenbestand-wegen/ogc/v1/), supplies actual road centre lines, source junction IDs and travel directions. [PDOK states CC0, monthly updates, no cost and no authentication](https://api.pdok.nl/rws/nationaal-wegenbestand-wegen/ogc/v1?f=html). [NDW's road-class documentation](https://docs.ndw.nu/handleidingen/nwb/nwb-basisstructuur/baansubsoort/) and [direction documentation](https://docs.ndw.nu/handleidingen/nwb/nwb-basisstructuur/overige-attributen/) define the filtering and graph directions. The checked service edition was updated to 2026-10-05.

Run `python3 scripts/build-traffic.py --download` in a Python environment with Shapely and pyproj. `--download` acquires/resumes municipal pages in ignored `work/data-cache/traffic`; existing pages are reused, so archive/move that directory before deliberately refreshing the source edition. Without `--download`, rebuilding uses the committed selected source, requiring no network or ignored page cache. All 42 raw HTTP responses remain on the SSD in that ignored directory, with exact hashes in `provenance.json`.

The `gme_naam=Rotterdam` source selection has 41,131 features. The build selects motor-road classes and known H/T/B directions, excluding footpaths, cycleways, ferries, dedicated transit lanes, parking links and emergency-only connections. It retains 28,924 selected source features in `nwb-roads.geojson.gz`, including original geometry, relevant properties and IDs. The complete original attributes remain in the ignored raw responses. It clips geometry to the retained exact municipality polygon, subtracts retained BRT road polygons explicitly tagged `in tunnel` with a 2-metre buffer, and discards only degenerate pieces shorter than 0.1 metres; short surveyed junction connectors must survive. Subtraction avoids graphical cars driving across water above mapped tunnels; missing BRT tunnel geometry remains a limitation. There is no line simplification or invented joining line.

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

Cyclists use a separate NWB FP (fietspad) network, never the motor-road graph. Run `python3 scripts/build-cycling.py --download` for initial acquisition/resume, or omit `--download` to rebuild from retained `nwb-cycleways.geojson.gz`. The download resumes the shared municipal page cache and does **not** rebuild motor-road assets. Archive/remove the cache when deliberately refreshing its edition. The retained 2026-10-24 snapshot contains 9,274 FP features; clipping/exclusions produce 8,746 runtime pieces covering 713.4 km, in a 381,461-byte gzip payload. Centre, Hoek and Maasvlakte coverage is checked. 413 selected features have unspecified directions. The selected FP source retains original geometry and all attributes; `cycling-provenance.json` records source, boundary, tunnel-mask and output hashes.

Preparation clips to the exact municipality, removes known BRT road tunnels, excludes FP records with negative `rel_hoogte`, and preserves original junction IDs only at unchanged endpoints. It uses the existing `roads.proto` contract in `public/data/traffic/cycleways.pb.gz`. H/T/B directions survive. Records with O/unknown directions are excluded from runtime and preserved in the selected source; no direction is guessed. Unmapped tunnels and missing source heights remain limitations. Shared-street cycling and links across non-FP gaps are omitted; this is not a full bicycle routing service.

Create a second layer with `createSimulatedTraffic({ project, requestRender, bicycles: true, maximumVehicles: 160, vehiclesPerKilometre: 20, maximumSpan: 2600 })`. Its default `load()` reads the cycleways file; apply the same view, pause, projection-refresh and dispose lifecycle as cars. `statistics()` exposes `cyclists` and `vehicles`; its `cars` count remains zero. Four instanced draws produce rider bodies/heads, low-poly wheels and frames/pedalling legs. Rider dimensions, clothing, cadence, a 4.2 m/s cruise speed, and about 0.4 m lateral separation are illustrative. No cyclist is a live observation. Main UI must say cars and cyclists are simulated.

The lane normal is interpolated over up to 3 m at each polyline bend (bounded to half the segment length), avoiding abrupt lateral jumps while keeping the route position on the surveyed centreline. Surface reprojection preserves all route progress and cannot reseed vehicles in the middle of the view. These are geometry/motion changes awaiting manager visual review; numerical tests are not that review.

## Source-connected journeys (rescue)

`public/traffic-journeys.js` plans an origin-to-destination path before a vehicle moves. Bounded Dijkstra searches source-directed edges with a modest turn cost, selects a reachable source junction as its destination, and keeps that complete path throughout the journey. The demand, chosen destinations and departure times remain illustrative. There is no random next-edge choice at junctions. Initial viewport vehicles represent trips already underway; replacements enter at the viewport edge. Arrivals leave the simulation rather than respawning at a visible dead end. Viewport culling still removes offscreen vehicles; this is not a persistent citywide traffic model.

Connections require identical nonzero NWB junction IDs, endpoint separation at most 0.5 m, and projected height separation at most 3 m. Geometric crossings alone never create a connection. Source H/T/B direction is respected. Immediate same-source-road reversals and turns sharper than 120 degrees are rejected; source-directed circulation loops remain possible. These are conservative graphical routing rules, **not verified legal turn restrictions**: this retained dataset has no turn restrictions, signal phases, lane widths, traffic demand or surveyed continuous elevation. Motorways and urban HR carriageways cannot be distinguished from HR alone. The scene's projected surface heights remain a separate limitation. The height-gap guard prevents discontinuities but does not establish bridge clearance or underpass correctness.

The old eight-metre preparation cutoff deleted genuine junction links, including the four-metre onward connection from an Erasmusbrug motor carriageway. Both compilers now retain nondegenerate connectors. Bicycle routing stays exclusively on FP, so disconnected FP components and shared-street gaps are intentionally not stitched to the car network. Unknown bicycle directions are excluded. Negative FP relative levels and known BRT tunnels are excluded conservatively, which also removes some legitimate underpasses.

Run `node tests/traffic-journeys.test.mjs` and `node tests/traffic-motion.test.mjs`. The first checks synthetic crossings, one-way travel, disconnected endpoints, vertical discontinuities and reversals; then checks actual centre and Hoek multi-edge journeys and both directions on the separate motor/cycle Erasmusbrug paths. `journey-audit.json` retains the deterministic report. Its coordinates use planar projection, so zero height-gap counts are **not an elevation validation**. Network component counts are weak connectivity, not guarantees of bidirectional reachability. Runtime statistics expose projected-network counts and planned/completed journey counts for browser review. CPU tests cannot validate visual steering, layer alignment or motion quality.

## WKD bicycle-access review candidate

The FP-only network above is a preserved baseline, not complete bicycle access. Primary NDW documentation clarifies that NWB `rijrichtng` describes motorized travel: it is insufficient evidence of bicycle direction. The new candidate uses Rijkswaterstaat **WKD Verkeerstypen** `FIETS_H` and `FIETS_T` explicitly (`J` permitted, `N` not permitted), keyed exactly by `WVK_ID`. Motor direction is never inherited. See the [NDW schema](https://docs.ndw.nu/handleidingen/wkd/wkd_verkeerstypen/) and [CC0 dataset record](https://data.overheid.nl/dataset/73747-wegkenmerkendatabase-voor-verkeerstypen). The complete retrieved schema HTML is retained as `wkd-schema.html.gz`.

Acquisition: `python scripts/prepare-cycling-access.py --download` (or `--archive /path/01-10-2026.zip`). Initial regional extraction needs the complete municipal NWB cache; it retains exact original regional CSV values for 39,123 matching IDs and only the additional NWB features absent from the existing road/cycle archives. No street-name or nearest-line conflation is used. `cycling-access-provenance.json` preserves archive/CSV/selected-source hashes, URL, raw-page hashes and the archive definition's actual snapshot date, **2026-10-07**. Compilation subsequently needs only committed sources: `python scripts/build-cycling.py --wkd`.

This produces **a separate** `public/data/traffic/cycleways-wkd.pb.gz`, leaving the reviewed baseline filename unchanged. It contains 27,701 pieces / 2,168.7 km / 1,176,760 compressed bytes. It connects dedicated FP paths to permitted shared streets using the same original junction IDs; notably 17,605 selected RB source features and 496 ERF features contribute. It adds no interpolated connector. Unknown permissions, newer NWB feature dates, ferries, special-access/emergency/bus-only classes, negative levels and known tunnels are excluded. A permitted shared street does not become a physically separated cycle lane: geometry stays on its source road, and any visual offset is still illustrative.

The review branch now loads `cycleways-wkd.pb.gz` by default. Rebuild it from retained sources with the command above before starting the browser candidate. The original FP-only filename remains available for comparison. `node tests/cycling-access-network.test.mjs` validates every runtime direction against its retained WKD row, checks that bikes are excluded from Erasmusbrug motor carriageways, and finds mixed FP/shared-street journeys around centre and Hoek. The retained report `cycling-access-journey-audit.json` shows 62 mixed journeys among 100 tested central origins. `python tests/cycling-access.test.py` covers directional permissions, newer-source exclusions and turn-match ambiguity.

Limitations are source-specific: WKD's documentation reports known bicycle-direction and parallel-path errors and incomplete source refreshes. The October WKD archive and live-acquired NWB snapshot are not proven identical monthly editions; newer NWB features are rejected, but the exact ID join does not eliminate all edition mismatch. One bridge FP's WKD direction reverses the old motor-direction assumption. This deserves visual/source review, not an unsupported legal-correctness claim. WKD does not supply turn restrictions or signal states. No evidence here validates continuous elevation.

## OSM motor-turn restriction acquisition and matching pilot

`python scripts/audit-turn-restrictions.py --download` requests only restriction relations in the bounded centre/Erasmusbrug rectangle (51.900,4.465–51.930,4.505), plus member ways/nodes. `--input response.json` accepts a locally acquired Overpass response; subsequent runs use the retained gzip. `--endpoint URL` selects another public Overpass server. The response uses `out body` rather than contributor metadata. The script rejects partial responses, retains raw response and exact query/hashes, and outputs `osm-turn-restriction-audit.json` for **review**, not automatic activation.

The conservative matcher requires an unambiguous NWB junction within 8 m, compatible source motor direction and a unique named/local-tangent match for both ways. Unnamed matches require tighter distance/angle agreement. Multiple nearby junctions or edge matches are rejected. Conditional restrictions, via-way/multiple-member relations and motorcar exemptions remain explicitly unsupported. The runtime now applies the reviewed strict subset below. `only_*` blocks every other exit from its incoming directed edge, while `no_*` blocks only the named outgoing directed edge. Bikes do not inherit these motor restrictions.

Cloud acquisition attempts on 2026-10-24: `overpass-api.de` returned HTTP 406; independent `overpass.kumi.systems` timed out after 30 seconds. No restriction data was fabricated or marked as acquired. The script is ready for the manager's local network. A successful geometric match is still only a review candidate and cannot establish exhaustive legal-turn coverage.

### Actual-source correction and reviewed runtime pilot

The manager acquired 63 OSM restriction relations (113 ways / 574 nodes) and retained `osm-centre-turn-restrictions.json.gz`. The first audit falsely yielded zero candidates because it skipped all 28,924 actual NWB `MultiLineString` features. This was an implementation bug, **not absence of restrictions**. The corrected matcher uses only original overall first/last endpoints, never invents multipart joins, retains short endpoint tangents, and reports a 57,848-endpoint / 22,544-junction inventory. Empty supported inventories now fail explicitly. Regression tests load both the actual retained NWB and actual downloaded OSM.

The corrected audit finds 17 candidate relations. Ten satisfy the stricter reviewed gate: <=2m junction separation, exact nonempty street-name agreement or the proven short continuations described below, local-tangent cosine >=0.985, and compatible source directions. Source overlays are in [traffic-restriction-matches.png](../../docs/images/traffic-restriction-matches.png). `scripts/compile-turn-restrictions.py` uses an explicit ten-relation allow-list, so newly matched refresh results cannot silently enter runtime. It emits `public/data/traffic/turn-restrictions.json` with source/audit hashes, ODbL license and attribution. This is a small conflated OSM/NWB pilot, not a complete legal routing database. The other 53 relations are not activated (46 unmatched/unsupported, seven looser candidates).

Motor `load()` fetches the rule asset and exposes `restrictionStatus`; missing/invalid assets report unavailable rather than implying restrictions loaded. Planner diagnostics report applied/unresolved rules and excluded transitions. Each rule is specific to from-road, incoming direction, source junction, to-road and outgoing direction. Runtime-target checks resolve all ten and remove ten directed graph transitions; `node tests/traffic-restrictions.test.mjs` checks both `no_*` and `only_*` behavior against actual prepared roads. `python tests/cycling-access.test.py` checks the corrected source matcher. Reprojection retains rules as part of the source network.

Source data and derived restriction database: © OpenStreetMap contributors, [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/); the surrounding application code remains MIT. The UI must display the OpenStreetMap attribution link when publishing this candidate. No source turn signals, time windows, or via-way state machine are inferred. Source-edition differences and ambiguous geometry continue to limit coverage.

### Exact instance samples and further turn coverage

`sampleVehicles({limit:8, roadId:null, near:null, radius:Infinity})` is an on-demand API on each traffic layer. It returns up to 64 visible instances with stable vehicle ID, source road ID/class/direction, source-coordinate position, centreline and exact last-rendered instance-base coordinates, world-base coordinates, lane offset, screen NDC, scale, speed and journey progress. The base coordinates come from the actual instance matrix, not a reconstructed screenshot path. This supports scene raycasting of the surface below a suspect car or cyclist. It does not add per-frame diagnostics work.

Source review recovered three more central restrictions: OSM 1312594 (Nassaukade→Stieltjesstraat), 14966194 and 14966196 (Coolsingel/Aert van Nesstraat). NWB names the corresponding short junction links Nassaukade (5.007m) and Meent (19.119m), respectively. Each has a **unique directly connected, direction-compatible, aligned continuation** with OSM's street name. The matcher accepts this evidence only for single-part links <=25m, a <=2m via match, tangent cosine >=0.985 and continuation cosine >=0.94. It records the continuation's actual road ID/junction/name; no free-form name alias or invented connector is introduced. Removing the actual continuation makes the regression test reject the match again. OSM/NWB direction conflicts such as Coolsestraat 21622541 remain rejected.

The current explicit reviewed allow-list contains **ten** rules, tested against the actual prepared motor graph (ten excluded transitions). The corrected audit now has 17 candidates out of 63 relations: ten strict/evidenced matches, seven looser candidates, and 46 unmatched/unsupported. Updated source overlays are in the linked image above. The initial pilot had seven rules; this source review adds three without relaxing the geometry or direction checks.

For broader acquisition, run `python scripts/acquire-municipality-turns.py --download --max-tiles 17` on a network that reaches Overpass. Default is at most four new requests per invocation; reruns reuse completed responses. The retained exact municipality footprint needs 17 bounded queries, including Hoek and the port. `osm-municipality-turn-plan.json` records them. Each tile retains raw gzip plus exact query, endpoint, retrieval time and hash. Requests stop after the first error; cached tiles remain usable. Merging requires every tile, rejects conflicting source snapshots, and keeps only restriction relations whose via geometry intersects the municipality, together with complete members. No broader source is claimed acquired by the plan alone.

After acquisition, run `python scripts/audit-turn-restrictions.py --source source-data/traffic/osm-municipality-turn-restrictions.json.gz --acquisition source-data/traffic/osm-municipality-turn-acquisition.json --output source-data/traffic/osm-municipality-turn-audit.json`. This does not overwrite the reviewed central audit or activate new runtime rules. Review source alignments before extending the explicit compiler list. `python tests/municipality-turn-acquisition.test.py` tests exact retained footprint coverage, source conflicts and member/boundary filtering.

Source-coordinate overlays can be regenerated with `python scripts/render-turn-source-review.py` from the retained audit and raw source geometry.

### Following across source junction links

A follower now checks queued same-direction vehicles along its already planned next edges, not just its current NWB edge. Otherwise a lead car on the far side of a short connector disappears from following logic until the follower enters that road. A bounded lookahead (following distance, at most 16 edges) includes real short links without changing route geometry. Occupancy positions are snapshotted once per frame so vehicle update order cannot move a leader into the wrong indexed road. Opposite directions and other branches do not trigger following brakes. This improves queue spacing; it is still not a signal-aware collision model. `node tests/traffic-following.test.mjs` checks short connectors, reverse source direction, other branches and snapshot identity.

### Resuming independent tiles after Overpass failures

A failing tile need not block the remaining request budget:

```sh
python scripts/acquire-municipality-turns.py --download --continue-on-error --max-tiles 9
```

Every failed HTTP request consumes one budget slot. `--continue-on-error` makes one attempt per selected missing tile and moves on; there is no retry loop. Without it, the original stop-after-first-failure behavior remains. Failed-attempt metadata (tile, endpoint, query hash, time and error) is retained beside the successful raw responses.

Select a single tile with repeatable `--tile`, or split a failed exact bbox into four children:

```sh
python scripts/acquire-municipality-turns.py --download --tile 36-865 --max-tiles 1
python scripts/acquire-municipality-turns.py --subdivide 36-865 --tile 36-865 --download --continue-on-error --max-tiles 4
```

The second command persists the split in `osm-municipality-subdivisions.json`, so subsequent resumes keep the same child queries. Children are `36-865.0` through `.3`; a parent selector includes its active descendants. A child can be subdivided once more if explicitly requested; depth is bounded to two levels. The four child bboxes exactly cover their parent, including boundary edges. Parent raw responses are preserved but are not counted as completed children. Completion is calculated over **all active leaf tiles**, regardless of the download selector, so acquiring one selected tile cannot falsely mark the whole municipality complete. The global original count remains 17; splitting one tile changes the active required count to 20.

`python tests/municipality-turn-acquisition.test.py` uses temporary files and mocked HTTP responses to verify 502 continuation, request budgets, selected resumption, persisted subdivisions, exact bbox coverage, source preservation and incomplete-state reporting. It makes no network requests.
