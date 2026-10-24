# Measured port structures

Written by AI, gpt-6-astra, 2026-10-24.

AHN6 laser returns add measured cranes, roof/storage forms and other non-building port forms. Areas with repeated rectangular roof evidence use measured roof bands, inferred closed volumes and fitted straight crane members. The source does not establish every form as a container. Other industrial forms retain occupied-volume reconstruction. Muted source-derived colours and quiet illustrative tier joints make stacks legible; open air beneath measured booms remains open. This is a dated, stylised reconstruction of observations, not a claim about current container or crane positions.

## Source selection and exclusions

The [AHN dataroom](https://www.ahn.nl/dataroom) supplies classified laser returns in RD New plus NAP height (EPSG:7415). [AHN6 is CC BY 4.0](https://www.ahn.nl/eerste-deel-ahn-6-beschikbaar). Credit Actueel Hoogtebestand Nederland (AHN) / Het Waterschapshuis, identify the edition and transformations, and keep that data licence separate from the MIT code.

The [official COPC index](https://basisdata.nl/hwh-portal/20230609_tmp/links/nationaal/Nederland/AHN6_KM_PC_COPC.json) lists spatially queryable 1 km source files. Acquisition is bounded to 80 m corridors around actual BGT rail features whose `plus_functie` is `(haven)kraan`, clipped to Rotterdam's exact municipal boundary. This selects 53 connected terminal areas covering 14.464 km² and intersects 86 source files. It is explicitly partial port coverage; yards without recorded crane rails are not silently filled with invented objects.

One point-source ID and GPS day is selected for each connected terminal area, by greatest measured 10 m cell coverage. Missing parts of that flight remain missing. `source-data/industrial-structures/coverage.json` records the selected passes, observed dates and coverage; `selection.json` records exact source URLs, bounds, raw crop hashes and cache paths. Raw LAZ, DTM GeoTIFF and BGT response pages stay in ignored SSD `work/data-cache/industrial-structures/`. Region masks use RD metres, explicitly identified in their properties. The completed acquisition retained 645.53 MB of cropped LAZ. Selected passes supply 18,816,412 raw returns across 102,450 observed 10 m cells, in 52 terminal areas totalling 14.432 km²; the remaining 0.032 km² area has no observations. Cell counts measure source coverage, not the number of industrial objects. Observed dates are 13, 16 and 19 December 2025.

The geometry keeps AHN class 1 (other/unclassified), not a semantic “crane” class. It removes ground, building and water classes, plus returns within 0.8 m of the measured AHN DTM. Where the DTM is absent it requires NAP height above 2 m. Current BGT building, tank, silo, canopy, wind turbine and vegetation geometry excludes duplicate objects already covered by better sources. Polygon exclusions have a 1.5 m display margin; individual tree points use a 5 m display exclusion, not a surveyed crown. Exact BGT IDs, versions, query URLs and exclusion buffers remain in the raw cache.

## Reconstruction and runtime

The replaceable stages separate temporal/source selection, geometry interpretation, muted colours and standard delivery assets. `fetch-industrial-structures.py` and `build-industrial-structures.py` produce the original single-flight occupied volumes. `terminal-reconstruction.json` records model-reviewed regions with repeated rectangular roofs; it is replaceable source interpretation, not landmark logic in the renderer.

`fetch-industrial-terminal-sources.py` reacquires those same selected source bounds at 0.5 m COPC sampling. Its 34 unique official crops occupy 1.286 GB in ignored SSD cache and support 46 original source/region segments. Original flight/day, municipal masks and building/tree/water exclusions remain unchanged. `terminal-sources.json` records URLs, bounds, dates and hashes. No transient positions are imported from later aerial imagery.

`build-industrial-terminals.py` fits repeated roof bands close to either orthogonal local BGT crane-rail axis. Horizontal point support supplies widths, longitudinal extents and local top heights. Global roof levels locate repeated tiers but do not override supported local roof heights. Straight source-supported members form open crane frames. The shared method has no region-specific art parameters.

Hidden sides and bases are inferred. A missing DTM cell may use a robust local plane through nearby same-flight class-2 ground, within the same terminal mask and without crossing current unsimplified BGT water. Every inferred storage footprint is checked against current wet BGT water before either base path; an unsupported roof cap is omitted from the rendered derivative and retained in source evidence. Measured crane members may legitimately overhang water. Short longitudinal scan gaps may close; missing flight coverage is not filled. Repeated approximately 2.9–3 m source roof-level gaps set illustrative dark tier joints, **not surveyed individual container boundaries**. Each roof segment/member uses a robust source colour mapped to the existing muted palette.

The complete replacement converts 17 original source segments in regions 0, 1, 7, 10, 27, 32, 35, 37 and 42. The other 29 reviewed segments retain their original geometry because returns or repeated row/elevation evidence are insufficient. Reviewed regions 6, 18, 19 and 28 are entirely unchanged. All unreviewed industrial branches remain unchanged. Full source bounds are processed; local visual fixtures never replace larger source coverage.

The installed layer contains 523 GLBs, 61.37 MB raw / 36.24 MB gzip and 4,072,484 triangles across all retained LODs. Reconstructed branches contribute 1,001,204 triangles; 349 unchanged GLBs match preceding file hashes. The final rules omit 126 roofs without supported bases and 1,248 inferred storage footprints crossing current surveyed water. No unsupported caps are rendered; all 18,098 fitted measured members remain. These are whole-layer totals, not initial downloads. Standard 3D Tiles 1.1 bounds stream 250 m cells. Reconstructed branches have one detail level; retained branches keep their original coarse/fine replacement hierarchy. Exact partitioning preserves every generated triangle, attribute and transform, while avoiding large source-square downloads.

GLBs use an ENU-to-ECEF root transform, Y-up contents, `KHR_mesh_quantization` unsigned 16-bit positions and linear `COLOR_0`. Runtime uses vertex colours and flat shading. Mesh extras identify `sourceLayer: industrial-structures`, `surfaceKind: measured-industrial`, observation date and observed/inferred/illustrative distinctions. These are not building batches and must not receive windows. All 523 assets were parsed by the existing vendor GLTFLoader, with finite indexed attributes and colour data; every runtime URI exists and root bounds enclose all child boxes.

Reproduce from the project root using its existing devenv dependencies, without temporary wrappers or extra installs. The original source stage supplies the retained masks, exclusions, original crops and DTM caches. Run the terrain preparation below before the terminal build if the current BGT response cache is absent:

```sh
devenv shell -- python scripts/fetch-industrial-terminal-sources.py
OPENBLAS_NUM_THREADS=1 devenv shell -- python scripts/build-industrial-terminals.py \
  --base public/data/industrial-structures \
  --tileset public/data/industrial-structures/tileset.json \
  --output work/industrial-terminals-next
```

Use a fresh output directory and inspect it before replacing public assets. `--only` accepts original source indices for bounded reproductions. The dense acquisition took 184 seconds; the final complete two-worker reconstruction/partitioning took 362 seconds on the development machine; these are offline preparation times, not browser performance claims. Raw and detailed per-roof fit evidence remain under `work/data-cache/industrial-terminals/`.

## Reconcile dated shorelines

Some native municipal water geometry dates from 2017–19. It still covers land reclaimed by the December 2025 AHN flight and the current BGT survey; valid newer objects consequently appeared to float over water. `build-industrial-terrain.py` prepares a separate standard 3D Tiles layer for current BGT industrial land intersecting the 2019 BGT water snapshot, minus current BGT water, within the existing industrial observation masks and original source bounds. The source polygons determine the shoreline and holes; no hand-drawn repair is used. The current snapshot is 23 October 2026. Dry ditches are not classified as wet water.

The 2 m triangulation samples retained AHN6 DTM where valid. Occluded cells may use the same bounded local ground fit as the roof bases: same flight/day and terminal mask, at least eight observed ground cells within 30 m, no current-water crossing, residual90 at most 0.25 m and slope at most 0.04. Unsupported triangles remain absent. A fitted height is an inference from surveyed nearby ground, not a direct observation of that cell. Per-mesh evidence counts distinguish DTM samples from local fits; the manifest retains source hashes and detailed fit-cache hashes. The terrain supplies the surface-height query as well as visible ground.

Reproduce the complete retained-source coverage with:

```sh
OPENBLAS_NUM_THREADS=1 devenv shell -- python scripts/build-industrial-terrain.py \
  --output work/industrial-terrain-next
```

The complete scan covers all 123 retained industrial source segments. Only sources 25 and 61 meet this dated-shoreline rule: two GLBs total 13,928 bytes and 1,075 triangles. They render 1,854.17 m² of the 3,043.12 m² eligible footprint. The remaining 1,188.96 m² lacks acceptable height support and remains absent. Vertex evidence comprises 133 direct DTM samples, 523 bounded fits and 365 unsupported positions. Source 61 is entirely inferred ground; source 25 is mostly direct DTM. These are conservative source-coverage limits, not missing acquisition silently filled with a flat plane.

`source-data/industrial-terrain.json` records the exact selected source indices, source snapshots and acquisition inventory. Raw BGT pages, original terrain samples and detailed fits remain in ignored SSD cache. This reconciles supported dated industrial shoreline disagreements; it does not replace the whole city's terrain or claim current industrial objects.

## Height convention

AHN heights are NAP, not ellipsoidal. A verified EPSG:7415 → EPSG:4979 transform using the official PROJ `nl_nsgi_rdtrans2018.tif` and `nl_nsgi_nlgeo2018.tif` grids turns NAP 5 m at RD 60200,441750 into ellipsoidal 48.609 m. However, the existing municipal model numerically uses NAP-like heights in its ECEF placement: four coastal BGT probes read 5.292, 6.227, 5.116 and 5.373 m, against independent AHN DTM 5.330, 6.189, 5.166 and 5.417 m.

This layer follows that verified existing whole-model convention: transform RD horizontal position to WGS84, then use NAP numerically as model height. Applying the true geoid correction only here would float these structures about 43.6 m above the city. A future datum correction must transform the whole model consistently. Exact grid hashes, transform and probe evidence are retained under `work/source-quality/height/proj/` and `dunes-ground-check.json`.

## Visual evidence and known limits

AHN6 catalogue edition 2026 here observes **13, 16 and 19 December 2025**. The single-flight/day rule avoids visibly superimposing different crane poses. A later PDOK aerial image informed interpretation only; it cannot validate December container placements.

Actual-map inspection accepted the reconstruction direction at two separate terminals and across the complete original source-6 footprint. Retained captures include `work/visual-qa/port-reconstruction-tiered-120.jpg`, `port-full-crop6-day.jpg` and `port-second-terminal-day.jpg`. The production stage extends the same method across supported regions. Actual whole-port inspection retains a known limitation: exposed crane members and some unchanged industrial branches remain skeletal at district scale. Source-square joins and incomplete lower connections are not repaired with invented engineering. The source-date shoreline fix was checked in the actual map at the smaller terminal (`terminal-reclaimed-ground-day.jpg`); source 25 was separately checked after the full scan (`second-shore-final-day.jpg`).

LiDAR sees exposed surfaces. Roofs and fitted members are measurement-supported; hidden walls/base planes and gap closing are interpretations. Thin occluded members, source gaps and some non-container industrial forms remain incomplete. Independent fits in adjacent source squares may expose joins; exact delivery partitioning alone does not establish cross-source reconstruction continuity. This is a dated miniature interpretation, not a current crane/container inventory. Native buildings, tanks, semantic ground and lighting remain separate sources.

## Coast finding

The municipal BGT ground already supplies dune relief and cycle paths. At 4.125° E, 51.995° N, tile `0025cb58-e0f5-4169-bb4c-5339a3bc2a7e/15/33519/6918.b3dm` has a measured dune triangle at 5.292 m and a nearby cycle path at 6.227 m. Its 5.31 MB includes 53,963 triangles. A coarser semantic mesh of those surfaces supplies relief without adding a second terrain beneath flat ground. Omit the −99.99 m missing-height sentinel.

## Delivery partitioning

The runtime assets now pass through [exact spatial subdivision](prepared-mesh-subdivision.md). Dense meshes are partitioned into 250 m cells after reconstruction; triangle/attribute values and LOD semantics are preserved. Current delivery totals above include this partitioning.
