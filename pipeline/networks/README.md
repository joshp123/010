# M1 car and cycle networks

Written by AI on 2026-10-26 by model GPT-6 Astra.

Data lives on the SSD at `/Volumes/Josh Extreme Pro USB4 4TB/010/scene/v1/networks/`. `cars.json` and `bikes.json` are directed, weakly connected graphs for RD x 89750–96500, y 434750–438000. They implement the user's follow-up decisions. They are simulated-traffic networks, not a navigation or legal-access service.

## Rebuild

Run from the repository, in order:

```sh
devenv shell -- python pipeline/networks/acquire.py
devenv shell -- python pipeline/networks/heights.py
devenv shell -- python pipeline/networks/build.py
devenv shell -- python pipeline/networks/verify_graphs.py
devenv shell -- python pipeline/networks/debug.py
```

The builder also reads existing archived BRT features under SSD `sources/overview-brt/2026-10-26/wegdeel_{vlak,lijn}/`. Exact used file hashes are in `build-report.json`; their original request URLs and licence are in that source archive's manifest. The earlier `audit.py` and `source-readiness.json` describe the initial stopped attempt, before the user authorised the assumptions; they do not describe the delivered graph.

## Browser contract

```js
const {nodes, edges, ways, edge_ways, tunnel_edges} = graph;
const [x, y, z] = nodes[nodeIndex]; // absolute RD east, RD north, NAP metres
const [from, to, speedKmh, lanes, roadClass] = edges[edgeIndex];
const source = ways[edge_ways[edgeIndex]];
// source.wvk_id, name, class, manager, manager_code, direction, oneway, tunnel
// source.tunnel === true: source height is the explicitly assumed -12 m NAP.
```

Edges are straight segments between sampled shape vertices, not straight shortcuts between junctions. Intermediate degree-two nodes preserve curves and heights. `edge_ways` shares source records so the JSON stays compact. `tunnel_edges` also lists every tunnel edge directly. The original NWB `direction` is retained; `oneway` records actual selected directions after filtering. Speeds (cars 30 km/h, national-road sections 50, woonerf/parking 15; bikes 18) and one lane per directed edge are **simulation defaults**, not measured speed limits or surveyed lane counts.

## Selection and topology

Cars exclude FP, VP, VZ, BUS/BU, OVB, tram/horse paths, ferries and emergency-only CADO connections. All other observed classes are eligible regardless of public road-manager type; original manager attributes are retained. Each build reports observed kept/dropped codes. WKD AUTO_H/T flags additionally exclude explicit car prohibitions where available. NWB H follows source begin-to-end, T reverses it, B permits both; O is omitted. Car directions intersect NWB and WKD permissions, so WKD cannot reverse a NWB one-way street.

Bikes include FP cycle paths in their NWB directions. Other eligible roads exclude BRT motorway/autoweg polygons and national-road-manager sections (a conservative surrogate where motorway designation is absent from NWB). [RVV 1990 articles 5 and 42](https://wetten.overheid.nl/BWBR0004825/2026-07-01/0) motivate carriageway use where no mandatory cycle path exists and exclusion of motorways/autowegen. The user's **12 m / parallel-path rule is a spatial approximation**, not a distance prescribed by that law: at each segment midpoint a cycle path within 12 m, aligned within 25 degrees, suppresses carriageway cycling. NWB does not distinguish mandatory from optional cycle paths. WKD FIETS_H/T supplies carriageway direction/access where available; unmatched roads conservatively inherit NWB directions, which may omit cycle contraflow exemptions. WKD is optional supplementary evidence, not the origin of the law-based selection rule.

Only matching original NWB junction IDs within 0.5 m join source ways. Crossing XY lines never create a junction. Clipped boundary endpoints stay disconnected from unrelated roads. Shapes simplify to 0.5 m before subdivision into segments no longer than 10 m before 0.1 m coordinate rounding and junction matching. Both graphs retain the largest weak component by directed edge length; `build-report.json` gives pre-pruning shares and the largest discarded components. Discarded components include meaningful coverage, not just tiny islands. Weak connectivity does not imply all-to-all directed reachability; directed component shares are also reported. Immediate U-turn avoidance, turn choice and vehicle spawning remain browser simulation responsibilities.

## Heights and tunnels

AHN DTM 0.5 m cells supply NAP heights at all shape/sample nodes; DSM fills DTM gaps. Nodes include every simplified corner and samples at ≤10 m intervals. At explicit BRT bridge polygons, DSM uses the 2nd percentile of measured cells within ±3 m to reject suspension cables: raw exact-cell DSM gives false 20–65 m spikes on the Erasmusbrug and Willemsbrug. This neighborhood estimate is recorded as `dsm_05m_bridge_p02_3m`; it is not a surveyed lane profile. Measured bridge sample profiles were smooth after this correction. If neither coverage has a valid value, the segment is omitted and counted; there is no invented surface-height fill.

BRT `in tunnel` geometry tags aligned road segments, excluding pedestrian-only tunnels and cycling-only tunnels from cars. Alignment against the tunnel polygon's long axis avoids pulling crossing surface roads into underground pedestrian passages. NWB negative-level sections named Maastunnel also tag tunnels. Tunnel nodes are set to **−12 m NAP by the user's stated assumption**. This is not a survey; fixed-depth tunnels have abrupt transitions at portals and do not reproduce approach gradients. Beneluxtunnel lies outside M1 and is not included. An underpass inferred solely from negative relative level is not automatically a tunnel. BRT vintage, polygon alignment and source relative levels can still leave omissions at complex crossings.

## Sources and gaps

- NWB: Rijkswaterstaat / PDOK, CC0, October 2026 service edition. Raw M1 pages and hashes: SSD `sources/nwb-networks/2026-10-26/manifest.json`.
- WKD Verkeerstypen: Rijkswaterstaat / NDW, CC0, October 2026 archive. Raw ZIP and official NGR licence evidence: SSD `sources/network-wkd/2026-10-26/manifest.json`. WKD has known completeness/update limitations and is not live access information.
- AHN: AHN / Rijkswaterstaat / PDOK, CC0 verified in archived capabilities. DTM/DSM source hashes: SSD `sources/network-ahn/2026-10-26/manifest.json`.
- BRT TOP10NL: Kadaster / PDOK, CC BY 4.0. Used for bridge/tunnel/motorway masks. Derived graphs carry this attribution; they are not described as exclusively CC0.
- Aerial: Beeldmateriaal.nl / PDOK 2026_orthoHR, CC BY 4.0. Exact requests and hashes: SSD `sources/network-ortho/2026-10-26/manifest.json`.

OSM turn restrictions were not integrated; no ODbL input is used in either graph. Turning restrictions, traffic signals, temporary closures, lane offsets, and cycle-path connections absent from NWB remain gaps. The Maastunnel cycle tunnel is absent from the retained connected bike graph; no invented lift/path connectors were added. Parallel-path pruning can produce disconnected fragments; no invented lateral connectors are added. Car and bike geometries can overlap on lawful shared carriageways. Source centerlines do not represent individual traffic lanes or painted cycle lanes.

Proof images are in SSD `renders/debug-networks/`: cyan cars, magenta bikes, arrows on one-way edges. The 1 m crops show raw aerial and overlay side by side. `inspection.json` checks the actual delivered graph and records named-road heights, including Lijnbaan exclusion. These source overlays establish geometry/direction alignment at the inspected places; they do not prove citywide legal completeness or browser vehicle behavior.
