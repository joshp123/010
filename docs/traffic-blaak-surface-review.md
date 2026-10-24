# Blaak source alignment

The stopped queue and the road-surface mismatch were separate defects. The
reservation fix remains unchanged. The original audit left runtime unchanged; the current-vector correction below now provides a motor-only review candidate. Bridge geometry remains unchanged.

NWB road 185274103 is Keizerstraat, direction B, with source junctions 185274093
and 185274094. Its retained WKD row explicitly permits cars and bicycles in both
directions (AUTO_H/T and FIETS_H/T are J; access date 2024-09-15). It is therefore
not defensible to exclude this road as cycle-only from the available evidence.

Decoded exact native municipal BGT triangles reproduce the manager's capture:

| Vehicle | Captured offset point | Original NWB centreline |
|---|---|---|
| 2, distance 18.154m | 0.327m inside traffic island 16524553 | 0.114m inside carriageway 14702898 |
| 17, distance 23.654m | 0.422m inside carriageway 14702898 | 0.625m inside same carriageway |
| 19 | 0.288m inside cyclepath 14198208 | 0.680m inside same cyclepath |
| 23 | 0.654m inside cyclepath 14198208 | 0.362m inside island 16524553 |

![Exact native source overlay](images/traffic-blaak-surface.png)

The generic right-hand lane offset worsens car 2's position, but simply removing
it leaves other cars on the old cyclepath/island. This is a source alignment
problem, not just height or material classification. Native road/island surfaces
are around 3.3m; the synthetic street ribbon at about -0.58m is below them and
cannot resolve the mismatch by changing its colour. No surface is reclassified.

The retained PDOK 2025 OrthoHR image independently shows the broader carriageway
to the east and construction on the western side. Old BGT capture dates are
2014 (cyclepath), 2015 (carriageway) and 2019 (island); their complete present-day
accuracy is not established. Retained municipal OSM Keizerstraat ways do not
span this 25m section, so their cycleway/residential tags cannot safely replace
this segment's access interpretation.

![2025 independent imagery, source centreline and captured vehicle positions](images/traffic-blaak-ortho2025.png)

A bounded **review-only corridor candidate** is generated from the actual BGT
carriageway polygon: sample the NWB line at <=0.5m intervals, project to the
polygon eroded by 2.35m, and require the complete resulting line to stay inside
its 2.2m erosion. The clearance accommodates a 1.15m lane offset and 0.95m car
half-width. These are explicit rendering dimensions, not invented street data.

![Derived corridor candidate](images/traffic-blaak-corridor-candidate.png)

This leaves the north source junction unchanged but shifts the southern shared
junction about 1.6m. Activation therefore requires reconciling the same endpoint
on NWB 600909887 and 185274085, checking turns/full footprints and current surface
boundaries, and keeping bicycle paths independent. Moving only this road would
break source graph joins. The candidate is deliberately not loaded by runtime;
it is a derived geometric interpretation, not a newly surveyed centreline.

Reproduce with `python scripts/audit-blaak-surface.py`. Source tile, dated aerial,
metadata, manager capture, machine-readable comparisons and candidate are retained
in `source-data/traffic/blaak-surface/`. The test checks exact captured polygon
membership, source access evidence and candidate clearance. Visual route
acceptance still requires the manager's native browser.

## Current-vector correction candidate

The same crop is now retained from explicit PDOK `2026_orthoHR`. It shows a
completed building replacing the 2025 construction but the roadway is deeply
shadowed. Gamma 0.45 is used only in the labelled comparison; both original
JPEGs remain unchanged. The shadow cannot establish surveyed lane boundaries.

![Identical dated crops and derived route](images/traffic-blaak-dated-corridor.png)

Current BGT supplies the missing independent vector evidence. Carriageway
`G0599.170ade244cdb72d73e050210a7e24429` was registered 2026-07-09T05:07:24Z
and published 2026-07-09T06:19:33Z. Its boundary differs from the native road by
0.272m Hausdorff distance within the review box. The nearby cyclepath was also
updated July 2026; the west island remains registered. These current road
polygons, not the aerial shadow, support the correction.

![Current vector reconciliation](images/traffic-blaak-current-corridor.png)

`python scripts/prepare-blaak-corridor.py` rebuilds
`public/data/traffic/road-geometry.json` from retained sources. It intersects
current and rendered-native carriageways, samples the original NWB line every
<=0.5m, and moves samples into a 2.6m-eroded corridor. The original source
geometry and J/J access record remain retained. All three incident motor edges
share the same corrected junction 185274094. The two neighbouring edges blend
back to original geometry between 10m and 14m from that junction; their far
endpoints remain unchanged. Bicycle paths receive no motor correction.

The builder verifies 340 full 4.3m × 1.885m car footprints in both directions,
including the actual lane offset/taper, plus all six admissible source turn
movements with 2.8rad/s yaw limits at 7m/s. Every checked footprint has zero area
outside the intersection of current/native carriageways. The initial 2.35m
margin left a 0.017m² turning sliver and was rejected; the 2.6m corridor passes.
This is a bounded sampled-clearance check, not a continuous collision proof.

The runtime validates the original road IDs, endpoints and coordinates (within
one 1e-7-degree protobuf rounding unit), then applies the whole group atomically.
Missing/changed/partial evidence keeps original geometry and reports the reason.
`geometryStatus=reviewed:3` and per-sample `geometryEvidence` expose use of the
current BGT interpretation. Original coordinates remain on each corrected road;
all other roads are unchanged. Shared source-junction graph identity, access,
restriction rules and the reservation fix remain intact.

Checks: `node tests/traffic-geometry.test.mjs`, existing motion, restriction and
Blaak queue regressions, and production build pass. The geometry test checks
loader/reprojection, stale/partial rejection, exact unchanged other roads,
shared-node journey continuity, all 60 restrictions and bicycle isolation.
The manager must still inspect native moving cars at the same Blaak view before
accepting this candidate. This local correction is not municipality-wide lane
accuracy or a guarantee of current traffic regulation.
