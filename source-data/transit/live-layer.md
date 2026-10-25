# Live observation adapter

Written by AI on 2026-10-24 by model GPT-6.

`public/live-transit.js` is independent of the renderer and UI. It loads the compact municipal map once and joins actual upstream reports. It does not create positions from a timetable, interpolate between reports, assume speed units or supply missing observation times.

```js
import { createLiveTransit } from './live-transit.js';
const live = createLiveTransit({ onUpdate: snapshot => receiveObservations(snapshot) });
await live.start();
// live.stop() stops automatic polling; live.refresh() fetches once.
// live.dispose() also aborts in-flight requests and ends callbacks.
```

The default same-origin endpoints are `/api/transit/vehicles` (GTFS-Realtime protobuf) and `/api/transit/ns` (NS bridge JSON). `mapUrl`, `vehicleUrl`, `trainUrl`, polling intervals and the callback are configurable. `snapshot()` returns the current ages without a request. `start()` and `refresh()` resolve to a snapshot; network/decode failures appear in source health rather than rejecting the normal update flow. Callbacks occur after source responses and every five seconds while polling so old reports become visibly stale.

Each vehicle has a stable source-prefixed ID, unchanged WGS84 `latitude`/`longitude`, Unix-seconds `observedAt`, `ageSeconds`, `freshness`, `mode`, `routeType`, route `label`, `operator`, optional upstream compass `bearing` in degrees clockwise from north, `tripId`/`routeId` when known and `sourceConnected`. NS labels are reported train numbers, not inferred line names. Freshness is `fresh` for an individually timestamped report aged 0–90 seconds by default; otherwise `stale`, `unknown` or `future`. The threshold is configurable. Source publication and reception times remain separate in `snapshot.sources`; a current response envelope does not refresh an old GPS fix. Render fresh observations as current vehicles; any stale/unknown/future markers need an explicit presentation distinct from fresh data.

A failed fetch marks that source `error`/disconnected, retains its previous coordinates and timestamps, and lets their age continue increasing. A successful full snapshot replaces the source's prior reports. Empty successful snapshots mean no supplied municipal reports; they are distinct from a connection failure. Unknown route linkage remains unknown. Incremental GTFS feeds are explicitly unsupported rather than incorrectly replacing a complete snapshot. NDOV metro coordinates are upstream operational reports, not an independent underground GPS claim.

## Sources and proxy boundary

[OVapi vehiclePositions.pb](https://gtfs.ovapi.nl/nl/vehiclePositions.pb) supplies urban/regional vehicles through the NDOV conversion. With `Origin: https://010.jjpcodes.com` and ordinary CORS fetch headers, both GET 200 and OPTIONS 200 omitted `Access-Control-Allow-Origin` on 2026-10-24. Browsers therefore need the same-origin proxy. This is a response-header probe; end-to-end browser verification belongs to the eventual app integration. The feed normally refreshes once a minute. The client and proxy check every 15 seconds to notice new publications without stacking minute-long caches; the proxy identifies itself, accepts gzip and retains conditional-request validators.

[NL Trains Live](https://treinen.ai-tigers.com/) documents a public no-key HTTP bridge for NS GPS sourced from NDOV. Its [attribution](https://treinen.ai-tigers.com/attribution) identifies NS-Treinposities and CC0. The adapter requests `/v1/trains?bbox=51.84,3.94,52.01,4.61`, which covers the complete municipal bounds, then applies the actual municipality polygon. Both CORS GET 200 and preflight 204 allowed `*` in the probe. Individual `observed_at` and fix-source labels remain intact. The bridge's `speed_mps` field is deliberately ignored: observed values appear to retain NS's km/h units despite that field name. No published service SLA or rate limit was found; this third-party bridge has no completeness guarantee. Client/proxy requests are spaced 15 seconds apart.

The optional `source-tools/transit-worker.js` exports `createTransitProxy()`. Create one handler at backend module scope, call it with the incoming Request and delegate unmatched paths (null) to the normal backend. It owns only the two exact paths above. It caches response bytes for 15 seconds per warm handler for both feeds, coalesces concurrent requests and returns 502 on upstream errors. It does not turn a stale cached response into a successful live request. This in-memory cache is **not** a globally shared cross-region cache; hosting integration must decide whether additional edge caching is needed. It requires no key, account or persistent TCP connection. The application Worker delegates these routes to this handler. Publication status is recorded separately from adapter evidence.

NS `trainUpdates.pb` was inspected separately: its 2,129 entities were all TripUpdate messages, with 38,773 stop-time updates and no VehiclePosition messages. Timings/platform updates are not GPS. The official NDOV NS GPS feed remains ZeroMQ; the third-party HTTP bridge is a replaceable acquisition adapter.

## Verified path and limits

The actual optional proxy, gzip municipal map and live adapter were exercised together through native HTTP fetch. A checked update contained 17 fresh municipal NDOV reports and four municipal NS reports, three fresh and one over 160 seconds old. The old NS fix was correctly stale despite a current response. Bus/metro labels and source coordinates/times were preserved. This late-night sample had no municipal tram report and is not proof of complete daytime coverage.

Forced source failures retained the last observations unchanged, marked both sources disconnected and aged all reports to stale. Truncated/malformed feeds produced explicit source errors. Proxy cache/coalescing and upstream 502 behavior were exercised. Disposal prevented further callbacks. The integrated local Worker was exercised in the in-app browser: actual NDOV and NS reports appeared in the city with source health and a working metro cutaway. Public deployment and device performance remain separate checks.

The source/licence boundaries in [README.md](README.md), [GTFS-LICENSE.txt](GTFS-LICENSE.txt) and [provenance.json](provenance.json) still apply: timetable shape databases are ODbL, other used timetable tables CC0, boundary CC BY, independent code MIT.

Public-source follow-up at 2026-10-24 04:12 UTC (AI, GPT-6 Astra): the same adapter fetched the deployed `010.jjpcodes.com` endpoints and municipal map. Both providers were ready; it returned four fresh metro, three fresh bus, three fresh tram and two fresh train reports, plus one correctly stale train. This verifies observed reports for all four requested modes in one live sample, not continuous or complete service coverage. The compact source-health/count record is retained in `work/visual-qa/public-transit-morning.json`.


Public early-Sunday diagnosis (written by AI, GPT-6 Astra, 2026-10-25): at 06:04:54 UTC / 07:04:54 Rotterdam, the deployed `/api/transit/vehicles` response and direct OVapi `vehiclePositions.pb` had identical SHA-256 `ac14905c1733c9b8f9d890d9aa09b87d2942b3d2359bac2529b95e1e34a26fd5`, 171 entities and source publication 06:04:26 UTC. Neither supplied a position inside the retained Rotterdam municipality. The one nearby fresh RET B report was at Schiedam Centrum (51.9215965, 4.4094238), outside the boundary; its trip393431577/start07:14:45 mapped correctly to B. Native RET Sunday25October timetable inspection confirmed B first departs Schiedam Centrum07:14, E first departs Slinge07:21 and Den Haag07:56 ([B](https://www.ret.nl/home/reizen/dienstregeling/metro-b.html), [E reverse](https://www.ret.nl/home/reizen/dienstregeling/metro-e/2026-10-25/terug.html)). The current empty municipal metro result is therefore consistent with early Sunday service, with no observed proxy, freshness or classification defect. This bounded sample does not establish complete later RET reporting; repeat actual Find once genuine in-boundary reports arrive. No simulated train or code change was introduced.
