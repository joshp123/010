# Prepared Rotterdam transit data

Written by AI on 2026-10-24 by model GPT-6.

This is a prepared data layer, not an integrated live service. `dist/data/transit/map.pb.gz` contains 150 routes, 793 source shapes clipped to the Kadaster GM0599 boundary, and 54,584 trip IDs linked to route and shape indices. It covers the entire municipality, including Hoek van Holland and port services. Source GTFS route types are retained: tram 0, metro 1, rail 2, bus 3 and ferry 4. Route geometry has no measured tunnel depth. The national archive contains 36,882 trips without a shape ID out of 937,368 trips; geographic selection cannot establish geometry for those trips. Unmatched real reports remain available with null route/shape metadata, so this subset is not a claim of complete operator or vehicle coverage.

`map.proto` defines the compact protobuf. Each shape line and municipal boundary ring contains packed zigzag-varint longitude/latitude deltas at 1e-7 degrees. Lines restart from zero. There is no simplification: only boundary intersections and coordinate quantisation, bounded to 7 mm displacement, are introduced. That processing bound is not source survey accuracy. Full national source bytes remain on the SSD in ignored `work/data-cache/transit/`; the public repository contains the compact derivative and provenance.

Run `python3 scripts/build-transit.py` in a Nix/devenv Python environment containing Shapely 2 to reproduce the retained input. Add `--download` to acquire the latest free OVapi archive and one timestamped live snapshot. Before refreshing a pinned archive, retain its hash-named copy if that edition is still needed. Provenance records source URLs, acquisition times, hashes, GTFS version and clipping. `municipality.geojson` retains the original Kadaster feature. `work/data-cache/transit/map.pb` is the uncompressed build output; only its deterministic gzip copy ships.

`dist/transit-feed.js` exports:

- `decodeTransitMap(decompressedBytes)` returns routes, shapes, the trip-ID map and municipality polygons.
- `decodeVehiclePositions(bytes)` decodes the GTFS-Realtime VehiclePosition subset using [official protobuf field IDs](https://github.com/google/transit/blob/master/gtfs-realtime/proto/gtfs-realtime.proto), retaining missing values, deleted entities and feed incrementality.
- `municipalVehicleReports(feed, map)` filters valid reported coordinates to GM0599 and attaches known route/shape metadata. Unknown linkage remains null. Observation time and feed time are separate; no timestamp, route position, speed or GPS provenance is invented.

Gzip must be decompressed before decoding, for example with the platform's `DecompressionStream('gzip')` or backend gzip support. The upstream vehicle feed lacks browser CORS and needs one shared backend/cache. It is a source of upstream-reported locations; metro coordinates can originate from operational stop information and are not proof of underground GPS. Freshness policy and any clearly labelled animation belong in the future integration. GTFS timetable shapes are never treated as observed vehicle positions.

The snapshot published at 2026-10-23 23:35:26 UTC contained 178 national entities. Twenty-one reports fell within GM0599 and matched retained routes: 8 RET metros and 13 RET buses. All had individual timestamps; ages were 3–57 seconds, median 9 seconds, relative to the feed timestamp. This late-night snapshot contains no municipal tram or train reports and proves no completeness guarantee. NS is absent from this particular national snapshot; the separate NDOV NS stream remains necessary to establish train observations. All five RET metro routes A–E are present in the prepared map.

## Data licences

The archive's own `licenses.txt`, preserved as `GTFS-LICENSE.txt`, is authoritative: **shapes.txt is ODbL 1.0**; other tables used here are **CC0 1.0**. Excluded ticketing tables carry different, restrictive licences and are not used. The derived shape database remains available under [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), including the public compact database and reproducible transform; retain share-alike terms when redistributing an adapted database. Attribute **OVapi / Stichting OpenGeo, GTFS NL; shape database under ODbL 1.0**, link the source and licence, and identify the municipal clipping/quantisation. This does not establish every underlying shape as a surveyed rail/road centreline.

The boundary remains **Kadaster / PDOK, Bestuurlijke Gebieden, CC BY 4.0**, with clipping/quantisation identified. Application and decoder code remain MIT. Do not imply official operator affiliation. See the [source usage policy](https://gtfs.ovapi.nl/README): identify the client in User-Agent, accept gzip and use conditional requests when polling faster than once a minute. Access is best-effort without an SLA. Use a shared collector rather than polling once per browser.
