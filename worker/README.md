Written by AI on 2026-10-26 by model GPT-6.

# Rotterdam live transport Worker

Local preparation only. No deployment, commit, account or paid service is needed.

`index.js` owns `/api/live`; other requests use the Cloudflare `ASSETS` binding.
The Sites Worker artifact is `dist/server/index.js`, `dist/client/` (static
assets), and `dist/.openai/hosting.json` with the existing project ID and no
`static` field. The generated Wrangler configuration binds `../client` as
`ASSETS`; extensionless HTML handling preserves `/t2`. The source Sites manifest
already uses the Worker form. `tools/build-site.sh` now creates this layout and
keeps its existing page assembly steps.

## Build and run

From the repository, inside the existing Nix environment:

```sh
devenv shell -- npm ci --ignore-scripts
devenv shell -- bash tools/build-site.sh '/Volumes/Josh Extreme Pro USB4 4TB/010/builds/site-worker'
devenv shell -- node node_modules/wrangler/bin/wrangler.js dev \
  --config '/Volumes/Josh Extreme Pro USB4 4TB/010/builds/site-worker/dist/server/wrangler.json' \
  --local --ip 127.0.0.1 --port 8788 --inspector-port 0
curl --compressed http://127.0.0.1:8788/api/live
```

To wrap an already-built static site without rebuilding any page, copy its
files into a new output's `dist/client/`, then run
`devenv shell -- node worker/build.mjs /absolute/output`.
The exact existing-site verification artifact is at
`/Volumes/Josh Extreme Pro USB4 4TB/010/builds/site-worker-exact`.

## API contract

`GET /api/live` returns compact JSON. `fields` describes each vehicle row:

```js
const { lines, headsigns, vehicles, feedTimestamp, nsFeedTimestamp } = snapshot;
const expanded = vehicles.map(([id, lineIndex, headsignIndex, x, y, bearing, observedAt]) => ({
  id, mode: lines[lineIndex][0], line: lines[lineIndex][1],
  headsign: headsigns[headsignIndex], x, y, bearing, observedAt,
  feedTimestamp: id.startsWith('NS:') ? nsFeedTimestamp : feedTimestamp,
}));
```

Coordinates are RD New metres rounded to 0.1 m, calculated with the published
polynomial in `web/miniature/rd.js`. This rounding is not a claim of positional
accuracy. The rectangle is the municipality's RD envelope enlarged by 2 km:
`[53500.0, 426647.4, 103032.6, 449000.0]`. It includes neighbouring towns and
the space between the city and Hoek van Holland.

Times are Unix seconds. `feedTimestamp` is OVapi's publication time;
`nsFeedTimestamp` is the NS bridge's `served_at` (reception/publication, not a
GPS fix). `observedAt` is always the original source observation time; missing
times, bearings and headsigns are `null`. No timetable animation or fabricated
positions are supplied. Old observations are retained with their original times;
the renderer must use `observedAt` to decide freshness. Metro locations can be
operational stop reports rather than underground GPS.

`lines` contains `[mode, passengerLineName]` pairs. Modes are `tram`, `metro`,
`bus`, `train`, `ferry`, or `null` for unknown metadata. Train line names are
GTFS names such as `Intercity`, `Intercity direct` and `Sprinter`. The NS ID
contains the passenger's train number. A destination is omitted if the retained
GTFS has conflicting destinations for that train number.

Every coordinate-bearing, non-deleted report inside the rectangle is retained,
with duplicate physical vehicle IDs collapsed. The lookup is restricted to
routes with a stop inside gemeente Rotterdam, as requested. Reports on other
routes remain present with null metadata and are counted in `unmatched`.
`unmatched.ns` counts trains without a GTFS line match; their mode is still
known from the train-only source. This limitation needs a scope decision before
all vehicles in the larger rectangle can have known modes and line names.

Responses send `Cache-Control: public, max-age=5`. Wrangler/Cloudflare compress
JSON for gzip-capable clients: use `curl --compressed` to test phone-sized
transfers. The raw JSON is around 26 KB at the sampled daytime load; compressed
transfer is around 8 KB. Neither size is a fixed bound when vehicle counts grow.

## Upstream and caching

OVapi: <https://gtfs.ovapi.nl/nl/vehiclePositions.pb>, CC0; usage policy:
<https://gtfs.ovapi.nl/README>. Uses the requested identifying User-Agent,
`Accept-Encoding: gzip`, and retained ETag/Last-Modified conditional headers.
Concurrent requests share one promise and refresh no sooner than 10 seconds,
including on upstream failure. A 304 keeps the source's original timestamps.

NS: <https://treinen.ai-tigers.com/v1/trains>, a no-account HTTP bridge for NDOV
NS positions, with CC0 data attribution at
<https://treinen.ai-tigers.com/attribution>. It has no guaranteed availability or
completeness. It is filtered by the same RD rectangle and cached with the same
10-second policy. Speed is unused. If NS fails, the OVapi snapshot still returns
with `sources.ns = "unavailable"`; an OVapi failure returns 502 without presenting
a previously cached snapshot as current success.

The Cloudflare Cache API shares compact snapshots within a Cloudflare location;
in-memory state also coalesces requests in each warm isolate. Neither provides
a global cross-region lock, and simultaneous cold isolates can each fetch.
A strict worldwide maximum of one upstream request every 10 seconds is **not
guaranteed** by these mechanisms. No extra coordinating service was introduced.
`transit-upstream` log entries identify actual outbound fetch attempts.

Ferries are included when OVapi reports them; missing operator coverage cannot
be synthesized. The local sample included Waterbus line 20. The sampled current
GTFS/feed supplied tram lines 4 and 8 and metro A–E. Tram numbers 21/23/24/25
were not in that snapshot; labels are never remapped to expected example numbers.

## Reproduce the lookup

The compact retained table is `source-data/transit/worker-lookup.json`.
The Worker build embeds it into its single server bundle; phones never download
it. `worker-provenance.json` records the archive hash, version, selection and
counts. Refresh it using any retained OVapi archive:

```sh
devenv shell -- python3 worker/build-lookup.py \
  '/Volumes/Josh Extreme Pro USB4 4TB/Projects/010/work/data-cache/transit/gtfs-nl.zip'
```

The builder selects routes using stops covered by the exact municipality polygon
and stop-times, then retains all trips on those routes, including real-time ID
aliases. Unlike shape-based selection it includes trips without shapes. Used
GTFS tables are CC0 and licences are checked before generation. No shapes or
ODbL shape derivatives are embedded. Boundary attribution: Kadaster / PDOK,
Bestuurlijke Gebieden GM0599, CC BY 4.0. Existing licence records are preserved.
