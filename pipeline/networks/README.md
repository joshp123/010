# M1 traffic networks

Written by AI on 2026-10-26 by model GPT-6 Astra.

Current deliverables: SSD `scene/v1/networks/cars.json` and `bikes.json`. These use the Geofabrik Zuid-Holland OpenStreetMap extract. Each retains its largest weakly connected component, as requested in the latest steering. No further per-tile audits are part of this workflow; existing audit files describe previous graph versions and are historical.

```sh
devenv shell -- python pipeline/networks/osm_source.py
devenv shell -- python pipeline/networks/heights.py
devenv shell -- python pipeline/networks/build_osm.py
```

To render just the requested whole-area aerial overlay:

```sh
devenv shell -- python - <<'PY'
import json, sys
sys.path.insert(0, 'pipeline/networks')
from debug import ROOT, M1, render
folder = ROOT / 'scene/v1/networks'
graphs = [json.loads((folder / f'{mode}.json').read_text()) for mode in ['cars', 'bikes']]
render('m1', M1, 2, graphs)
PY
```

The image is SSD `renders/debug-networks/m1-2m.png`: cyan cars, magenta bikes, arrows on one-way routes. Inspect the complete image against its aerial underlay before handing off.

## Contract

Absolute RD/NAP coordinates rounded to 0.1 m. Shapes preserve OSM junction nodes, simplify intervening geometry to 0.5 m, and sample heights at intervals up to 10 m.

```js
const [x, y, z] = graph.nodes[nodeIndex];
const [from, to, speedKmh, lanes, roadClass, maxspeed] = graph.edges[edgeIndex];
const source = graph.ways[graph.edge_ways[edgeIndex]];
// source.osm_id, source.tags, source.oneway, source.tunnel, source.bridge
```

`roadClass` is the OSM highway value. `maxspeed` is the tagged limit or Dutch built-up-area/class default; it is null on cycleways/paths without a tagged general limit. `speedKmh` is the simulation speed. Missing lane counts use one lane. `tunnel_edges` directly indexes tunnel edges, and the shared source records have `tunnel: true`. Original source tags remain available for access qualifiers and conditional rules. Turn-restriction relations are retained with mode-specific directed edge references; via-way constraints require tracking the traversed source-way sequence.

Cars respect the most specific motorcar/motor_vehicle/vehicle/access tag, one-way streets and roundabouts. Private/forbidden access and non-motor roads are excluded unless explicitly permitted for motor traffic. Bikes respect bicycle access, use_sidepath, motorway/motorroad exclusions, one-way bicycle exceptions and contraflow tags. Separately mapped cycleways keep their original geometry and topology. Shared carriageways remain shared. Barrier nodes explicitly impassable to the mode become route terminals rather than connecting through the barrier.

AHN DTM supplies surface heights; DSM fills gaps. Explicit bridge DSM sampling uses measured nearby lower returns to reject suspension cables. Short missing height runs interpolate along the same source arc/way; all-nodata ways remain omitted. Tunnels use the user's stated assumption of −12 m NAP, not surveyed depth; portals can have abrupt height transitions.

`osm-build-report.json` records current sizes and connectivity before/after component selection. Component shares use both node and directed-edge counts; connectivity is weak connectivity, not a claim that every ordered node pair is reachable. Disconnected peripheral source components are intentionally omitted.

## Provenance

Raw Geofabrik PBF and bounded extract are archived in SSD `sources/network-osm/2026-10-26/`, with exact URLs, hashes and timestamps in its manifest. Source: © OpenStreetMap contributors, via Geofabrik; ODbL 1.0. Derived graph database: ODbL 1.0. Code remains separate from that data licence.

AHN / Rijkswaterstaat / PDOK: CC0, archived in `sources/network-ahn/2026-10-26/`. Aerial: Beeldmateriaal.nl / PDOK `2026_orthoHR`, CC BY 4.0, archived in `sources/network-ortho/2026-10-26/`. No OSM contributor personal metadata was fetched.

The NWB builder, comparisons and earlier coverage reports are retained for history. They are not current acceptance results. Browser simulation and drawing are outside this task; `web/` is untouched.
