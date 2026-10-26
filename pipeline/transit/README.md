# Transit geometry

Written by AI on 2026-10-26 by model GPT-6.

Produces `/Volumes/Josh Extreme Pro USB4 4TB/010/scene/v1/networks/transit.json`.
The output uses passenger line names from the retained national GTFS, matching
the live Worker's `(mode, line)` keys. Buses are omitted.

Run from the repository, using its existing devenv:

```sh
devenv shell -- python3 -m pipeline.transit.build
devenv shell -- python3 -m pipeline.transit.match
devenv shell -- python3 -m pipeline.transit.finish
devenv shell -- python3 -m pipeline.transit.debug
devenv shell -- python3 -m pipeline.transit.verify
```

## Sources and geometry

- GTFS: retained `Projects/010/work/data-cache/transit/gtfs-nl.zip` on the
  same SSD, feed version 9644 (2026-10-23). Its own `licenses.txt` identifies
  shapes as ODbL-1.0; routes/trips are CC0. Preserve the shape attribution and
  ODbL terms when redistributing the derived database.
- Track geometry and tunnel/bridge classification: Kadaster/PDOK BRT TOP10NL,
  CC BY 4.0, retained under `010/sources/overview-brt/2026-10-26/`.
- Four GTFS legs at Woudestein cross a BRT gap. Actual BGT `spoor` geometry,
  Kadaster/PDOK CC0, from `010/sources/bgt/2026-10-25/` supplies that gap.
- AHN DTM/DSM: Rijkswaterstaat/PDOK, CC0, NAP metres. Reuses the network run's
  native 0.5 m tiles under `sources/network-ahn/2026-10-26/`, supplemented
  through the same free WCS under `sources/transit/2026-10-26/ahn/`.
- Debug aerial: Beeldmateriaal.nl/PDOK `2026_orthoHR`, CC BY 4.0.

GTFS supplies routes and directions; its coarse chords are not used as rail
positions. The matcher selects connected paths on the same-mode BRT graph.
Only source endpoints connect: geometric crossings do not invent switches.
Intervals are unioned per physical feature, line and traversal direction,
then simplified to 0.5 m and clipped to RD bounds
`87750,432750,98500,440000`. Ferries retain GTFS water routes.

The requested JSON has no direction field. Coordinate order carries traversal
direction; `height-report.json` records direction and source feature per path.
Paths split at source feature boundaries. A consumer must choose the matching
mode/line and nearest appropriate path rather than concatenate all paths.

## Heights and limits

Surface vertices use native AHN DTM. Missing DTM uses the nearest valid DTM
cell within 2 m, then DSM if necessary. Bridges/viaducts use DSM's second
percentile within 3 m, following the networks pipeline's deck sampling method
to reject overhead wires and pylons. This is an estimate of deck elevation,
not a surveyed railhead measurement. Height sampling adds vertices at most
5 m apart on bridges, 20 m on surface tracks, and 40 m in tunnels/on water.
XY and Z are rounded to 0.01 m; that precision does not imply centimetre accuracy.

BRT `in tunnel` sections have `t=1`. No measured tunnel depth was found in
the retained sources: **all tunnel vertices assume NAP -12 m**. BRT's relative
height level is not a measured depth. No portal ramp profile is invented;
separate tunnel/surface paths can have abrupt height changes at portals.
Ferries assume **NAP 0 m water elevation**, without tide correction.

BRT is generalized mapping, not a survey of every individual rail. Matching
removes GTFS street/block shortcuts but cannot promise sub-metre track centre
accuracy everywhere. The 0.5 m simplification tolerance does not improve source
accuracy. The retained GTFS snapshot determines which passenger lines appear;
this pipeline does not rename current lines to historic numbers.

## Evidence and provenance

`010/sources/transit/2026-10-26/` retains GTFS shape links, planar source
paths, matched feature paths, matching and height reports. Source downloads
have URL, licence and SHA-256 sidecars; reused inputs retain their parent
manifests. `height-report.json` maps every exported path to its BRT/BGT source.

`010/renders/debug-transit/` contains the full-bounds 2 m/pixel overlay and
the Delfshaven 0.5 m/pixel aerial/overlay pair, plus `verification.json`.
The latter checks the actual exported file, line coverage, bounds, heights,
tunnel flags, source matching gaps and image dimensions/hashes.
