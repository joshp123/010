# Measured port structures

Written by AI, gpt-6-astra, 2026-10-24.

AHN6 laser returns add measured cranes, container stacks and other non-building port forms. The browser layer uses crisp, solid occupied volumes aligned to measured crane rails, with one muted source-derived colour per connected form. Open air beneath booms remains open. This is a dated, stylised reconstruction of observations, not a claim about current container or crane positions.

## Source selection and exclusions

The [AHN dataroom](https://www.ahn.nl/dataroom) supplies classified laser returns in RD New plus NAP height (EPSG:7415). [AHN6 is CC BY 4.0](https://www.ahn.nl/eerste-deel-ahn-6-beschikbaar). Credit Actueel Hoogtebestand Nederland (AHN) / Het Waterschapshuis, identify the edition and transformations, and keep that data licence separate from the MIT code.

The [official COPC index](https://basisdata.nl/hwh-portal/20230609_tmp/links/nationaal/Nederland/AHN6_KM_PC_COPC.json) lists spatially queryable 1 km source files. Acquisition is bounded to 80 m corridors around actual BGT rail features whose `plus_functie` is `(haven)kraan`, clipped to Rotterdam's exact municipal boundary. This selects 53 connected terminal areas covering 14.464 km² and intersects 86 source files. It is explicitly partial port coverage; yards without recorded crane rails are not silently filled with invented objects.

One point-source ID and GPS day is selected for each connected terminal area, by greatest measured 10 m cell coverage. Missing parts of that flight remain missing. `source-data/industrial-structures/coverage.json` records the selected passes, observed dates and coverage; `selection.json` records exact source URLs, bounds, raw crop hashes and cache paths. Raw LAZ, DTM GeoTIFF and BGT response pages stay in ignored SSD `work/data-cache/industrial-structures/`. Region masks use RD metres, explicitly identified in their properties. The completed acquisition retained 645.53 MB of cropped LAZ. Selected passes supply 18,816,412 raw returns across 102,450 observed 10 m cells, in 52 terminal areas totalling 14.432 km²; the remaining 0.032 km² area has no observations. Cell counts measure source coverage, not the number of industrial objects. Observed dates are 13, 16 and 19 December 2025.

The geometry keeps AHN class 1 (other/unclassified), not a semantic “crane” class. It removes ground, building and water classes, plus returns within 0.8 m of the measured AHN DTM. Where the DTM is absent it requires NAP height above 2 m. Current BGT building, tank, silo, canopy, wind turbine and vegetation geometry excludes duplicate objects already covered by better sources. Polygon exclusions have a 1.5 m display margin; individual tree points use a 5 m display exclusion, not a surveyed crown. Exact BGT IDs, versions, query URLs and exclusion buffers remain in the raw cache.

## Reconstruction and runtime

`fetch-industrial-structures.py` is the source acquisition and temporal selection stage. `build-industrial-structures.py` is the replaceable reconstruction and style stage. Use a Nix Python environment containing `laspy`, `lazrs`, `requests`, `numpy`, `scipy`, `scikit-image`, `pyproj`, `shapely` and `Pillow`:

```sh
python scripts/fetch-industrial-structures.py
python scripts/build-industrial-structures.py --sample source-data/industrial-structures/selection.json
```

The builder creates 1 m occupied cells in a grid aligned to the area's measured crane rails, closes gaps with a 3 × 3 × 3 neighbourhood, fills enclosed cavities, and removes connected fragments below 6 m³. The coarser LOD uses 1.5 m cells. It only emits exposed faces, merges coplanar rectangles, and shares indexed vertices. This deliberately regularises small gaps and scan noise; it does not infer exact engineering members or turn a crane into a filled heightfield.

Each connected form receives its average source RGB, reduced saturation and lifted shadows, mapped to eleven muted colours. The source returns remain unchanged. `public/data/industrial-structures/tileset.json` is standard 3D Tiles 1.1 with a root ENU-to-ECEF transform and Y-up GLB contents. GLBs use `KHR_mesh_quantization` unsigned 16-bit positions and linear `COLOR_0`. Omitted normals allow shared vertices; GLTFLoader supplies flat shading. Runtime must preserve vertex colours and flat shading. Mesh extras identify `sourceLayer: industrial-structures` and `surfaceKind: measured-industrial`; these are not building batches and must not receive windows.

The 400 m comparison at 51.95609° N, 4.00802° E is retained in `sample.json`. Its 1 m GLB has 139,162 triangles and occupies 2.83 MB; the 1.5 m LOD has 65,144 triangles and occupies 0.94 MB. Broader source sampling uses COPC resolution 1 m, inspected against the denser 0.5 m source crop: principal silhouettes and open crane frames remain, while the smallest members are rougher. The broader build contains 118 rendered source segments and 236 GLBs: 96.22 MB / 5,371,230 triangles at 1 m, and 43.30 MB / 2,560,122 triangles at 1.5 m. Five selected segments contain no industrial returns after exclusions. The largest dense GLB is 9.79 MB. These are totals across the layer, not an initial download. Runtime assets stream spatially and by LOD; raw point clouds never ship to the browser. Further performance work should subdivide the densest source squares before reducing source fidelity.

## Height convention

AHN heights are NAP, not ellipsoidal. A verified EPSG:7415 → EPSG:4979 transform using the official PROJ `nl_nsgi_rdtrans2018.tif` and `nl_nsgi_nlgeo2018.tif` grids turns NAP 5 m at RD 60200,441750 into ellipsoidal 48.609 m. However, the existing municipal model numerically uses NAP-like heights in its ECEF placement: four coastal BGT probes read 5.292, 6.227, 5.116 and 5.373 m, against independent AHN DTM 5.330, 6.189, 5.166 and 5.417 m.

This layer follows that verified existing whole-model convention: transform RD horizontal position to WGS84, then use NAP numerically as model height. Applying the true geoid correction only here would float these structures about 43.6 m above the city. A future datum correction must transform the whole model consistently. Exact grid hashes, transform and probe evidence are retained under `work/source-quality/height/proj/` and `dunes-ground-check.json`.

## Visual evidence and known limits

At the retained 400 m fixture, catalogue edition **AHN6 2026** contains observations from **December 2025**. Source 1135 observes 16 December 18:10:55–18:11:18 UTC; 11351 is about 102 minutes later; 1134 is 19 December. Merging them visibly superimposes different crane poses. The single-flight rule addresses this before geometry styling.

Ignored `work/source-quality/height/` retains the actual comparisons:

- `port-flight-strip-comparison.png`: different measured crane poses in overlapping passes.
- `port-aligned-solid-1m.png` and `port-aligned-solid-1.5m.png`: accepted solid-form direction.
- `port-aligned-solid-source1m-1m.png`: economical source-sampling comparison.
- `port-matching-aerial-2026.jpg`: independent PDOK reference of the same crop, never a map texture. Its later date cannot validate December container positions.

Earlier all-pass voxels, Gaussian surfaces and per-face palettes are retained as rejected comparisons. Their failure was duplicate poses, fragmented or softened forms and mottled surfaces. `inspect-industrial-structures.py` reproduces the earlier single-flight local-surface comparison in `work/` only.

LiDAR sees exposed surfaces. Occluded thin members and parts outside the selected flight are missing; closing small gaps is a style/reconstruction choice. Class 1 can include other static or transient port objects, so this layer is described as measured industrial forms rather than an authoritative crane inventory. Native buildings, tank geometry and semantic ground remain separate.

## Coast finding

The municipal BGT ground already supplies dune relief and cycle paths. At 4.125° E, 51.995° N, tile `0025cb58-e0f5-4169-bb4c-5339a3bc2a7e/15/33519/6918.b3dm` has a measured dune triangle at 5.292 m and a nearby cycle path at 6.227 m. Its 5.31 MB includes 53,963 triangles. A coarser semantic mesh of those surfaces supplies relief without adding a second terrain beneath flat ground. Omit the −99.99 m missing-height sentinel.

## Delivery partitioning

The runtime assets now pass through [exact spatial subdivision](prepared-mesh-subdivision.md). Dense meshes are partitioned into 250 m cells after reconstruction; triangle/attribute values and LOD semantics are preserved. The source-builder size figures above describe the retained pre-subdivision assets, not the current delivery totals.
