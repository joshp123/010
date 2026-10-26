# Municipality overview

Written by AI on 2026-10-26 by model GPT-6 Astra.

From the repository root:

```sh
devenv shell -- python pipeline/overview/rebuild.py
```

Add `--reextract` after `rebuild.py` to recompute building geometry from raw
archived payloads instead of reusing derived footprint caches.

The output is `/Volumes/Josh Extreme Pro USB4 4TB/010/scene/overview-v1/`.
The grid contains every 1000 m RD tile intersecting the exact PDOK GM0599
polygon. Building ownership follows the detailed contract: a whole feature belongs
to the tile containing its footprint centroid. All local meshes use east, NAP up,
and negative north from the tile's south-west corner. Detailed pipeline files and
`scene/v1` are not written by this code.

Each stage can be replaced independently:

- `index.py`: exact boundary response and intersecting tile index.
- `buildings.py`: deepest municipal LOD2 buildings, storage tanks and bridges;
  projected triangle unions become simplified footprints extruded between measured
  source minimum and maximum elevations. No facade texture. Feature identities,
  source URLs and height are retained. BAG IDs remain null on non-BAG structures.
- `imagery.py`: exact PDOK `2026_orthoHR` WMS JPEG responses at 1 m per pixel;
  municipal tree trunk instances become points with source dimensions.
- `surfaces.py`: full-resolution TOP10NL polygons and rail centrelines rasterised
  at 1 m. Generic terrain is unknown rather than assumed paving. Delivered building,
  tank and bridge footprints override the base classes. AHN DTM samples on a shared
  25 m grid provide coarse terrain; triangles touching nodata are omitted.
- `imagery_coverage.py`: measure large white source-image gaps within GM0599.
- `finalize.py`: read every delivered tile, record byte counts and hashes, pin
  source manifests, and assemble the scene manifest.
- `mosaic.py`: class rasters with delivered building footprints overlaid at 8 m
  per pixel, plus aerial reference and regional comparisons at 4 m per pixel.

Raw responses, URLs, acquisition times, hashes and credits live under dated
`sources/overview-*` archives on the SSD. Rebuilds reuse those bytes. Extracted
building caches are derived inputs, not replacements for archived source bytes.
Source interpretation is explicit in each layer's report; a later model can
change a classification or simplification without regenerating the raw evidence.

TOP10NL is an overview compromise: it does not distinguish every detailed BGT
surface class, and generic industrial/urban terrain stays unknown. Rails use
G-channel bits 1 (tram) and 2 (train/metro), with source centrelines visible at
1 m rather than invented track gauges. Markings and lamps are omitted.

AHN supplies terrain, not bathymetry. Offshore and basin nodata remain holes in
`ground.glb`; `classes.png` still records the source water polygons. Aerial white
gaps remain exact source pixels. Municipal buildings and managed trees have
different survey dates and do not establish all 2026 construction or private trees.

Inspect `renders/overview/gemeente-8m.png` against
`renders/overview/gemeente-8m-aerial.jpg`, then the regional pairs. Counts, measured
coverage limitations and bytes per tile are in the scene reports and manifest.
