# Building conversion coordinates

Written by AI on 2026-10-26 by model GPT-6.1 Sol.

`transform.ecef_to_rdnap()` returns the municipal-source transformer. It decodes
Earth-centred coordinates with GRS80, transforms longitude and latitude using the
real NSGI RDNAPTRANS2018 horizontal correction grid, and retains the decoded
source height as NAP.

This explicit height convention matters: Rotterdam's exporter has already put
NAP into the geodetic-height field before constructing Earth-centred coordinates.
Applying another geoid correction lowers buildings and objects by approximately
43.61 m in Delfshaven. Evidence:

- The objects extractor compared 2,640 source tree-trunk heights with their
  explicit municipal `Hoogte`: median absolute difference 0.000032 m, maximum
  0.00907 m (including source position quantisation).
- In source tile `16/67155/13867`, 204 textured buildings have median base height
  -0.38748 m and median roof height 11.43164 m using the municipal convention.
  Full geoid correction gives -43.99420 m and -32.17447 m respectively.
- The newer LOD2 tile's 202 buildings have the same median base -0.38748 m.
  Detailed distributions are in `transform-check-building-heights.json`.

The source datum is treated as ETRS89 for horizontal conversion. Aerial alignment
must independently verify this assumption; the source epoch has not been proved.

`transform.ecef_to_rdnap(False)` provides standard ETRS89 Earth-centred to RD/NAP
conversion, including the real geoid grid, for actual ellipsoidal-height inputs.
`get_transformer` is an alias of `ecef_to_rdnap`.

Both grids and published reference coordinates are archived with hashes under
`sources/coordinate-grids/2026-10-25` beside the repository. They are local files;
conversion requires no network access and never falls back to a gridless method.
The reference check converts 3,208 published NSGI geographic reference points to
Earth-centred coordinates and then through the standard transformer. Maximum
horizontal residual is 0.00014144 m and maximum vertical residual 0.00004998 m.
These are numerical transformation checks, not a measurement of source accuracy.

Run the reference check inside this repository:

```sh
devenv shell -- python pipeline/buildings/transform-check.py
```

The archived grids originate from NSGI, converted to GeoTIFF by OSGeo PROJ-data,
under CC BY 4.0. Reference coordinates come from NSGI's
[`GeodetischeInfrastructuur/transformations` repository](https://github.com/GeodetischeInfrastructuur/transformations/blob/main/validate/data/Z001_ETRS89andRDNAP.txt).

## Inspect the built tile

```sh
devenv shell -- python pipeline/buildings/debug_render.py --tile x90250_y436000
```

This starts a temporary local HTTP server and headless Chromium, waits for the
renderer to finish through CDP, writes 2500 × 2500 PNGs, then stops both. Files
are under `renders/debug-buildings`: `overlay-<tile>.png` (translucent source
roofs and cyan edges over 2026 imagery), `oblique-<tile>.png` (source materials),
`edges-<tile>.png`, and `aerial-<tile>.png`. A roof-boundary GeoJSON sidecar uses
absolute RD coordinates and supplies the exact RD-to-image-pixel mapping.
The image-only reference is also retained as `aerial-<tile>.jpg`.

If the ground producer has not yet written `ortho.jpg`, this fetches and archives
the exact 2026 PDOK WMS response with request, hash and attribution. No product
renderer, styling or scene files are written by this debug command.

## Rebuild this scene

From the repository, with the archived grids in place:

```sh
devenv shell -- python pipeline/buildings/rebuild.py --area m1 --workers 8
```

This downloads missing municipal source files, retains raw archives, builds the selected area (M1 by default) with parallel source and tile workers,
renders inspection images and merges
only building/object metadata into the shared scene manifest under its lock.
It never writes ground.glb, ortho.jpg or classes.png. No packages were added for
this pipeline. Run a stage directly when only that stage needs replacing:

```sh
devenv shell -- python pipeline/buildings/build.py --area core
devenv shell -- python pipeline/buildings/objects.py --area m0
devenv shell -- python pipeline/buildings/debug_render.py --tile x90250_y436000
devenv shell -- python pipeline/buildings/alignment.py
devenv shell -- python pipeline/buildings/finalize.py
```

`build.py` follows only intersecting deepest tiles, reads composite b3dm content,
retains original source material groups and UVs, and transforms full triangle
positions into tile-local glTF axes. Vector footprint duplicates and outline
primitives are excluded. Geometry-only duplicate triangles are removed at source
boundaries. Images are JPEG quality 90, maximum 2048 pixels on either dimension.
No atlasing, mesh compression or additional LOD is performed.

The newer LOD2 inventory is authoritative. Match normalized 16-digit BAG numbers,
compare both horizontal bounding-box corners within 1 metre, then select the old
mesh only if it contributes source images. Otherwise keep LOD2. Old objects with
no newer counterpart are counted in the report but omitted; do not silently
restore possibly removed structures. Tile ownership uses the current geometry's
projected footprint centroid, computed from the union of projected triangles.
The footprint union uses a 0.1 mm precision grid to avoid GEOS numerical topology
failures at shared triangle edges; mesh coordinates remain unchanged.
Whole selected buildings stay together. Bridges are selected independently from
the textured bridge source. Their source IDs remain in the feature table.
BAG facts come from archived PDOK pand records and every explicitly linked VBO.
Year is oorspronkelijk bouwjaar; use is the sorted union of VBO gebruiksdoelen,
with an empty list for a proven zero-VBO building. Status is the stated pand
status. Unavailable facts use null, with an explicit BAG coverage flag; zero VBOs use [].
Coverage distinguishes unavailable current BAG records from zero VBOs.
BAG does not state storeys, so no storey count is inferred or emitted. Per-feature
provenance identifies archived response hashes and source fields.

PDOK migrated the old /lv/bag/ogc/v1 endpoint to
https://api.pdok.nl/kadaster/bag/ogc/v2. The BAG stage follows explicit VBO links
outside the spatial query too; boundary clipping cannot silently lose a use.

Reports in scene/v1/buildings-{core,m0,m1}-report.json record the actual chosen
source counts and the source manifest snapshots, not padded download counts.
Each tile's glTF root extras.features identifies its objects; _FEATURE_ID_0
indexes this table for every vertex. Immutable source manifest snapshots preserve
provenance when the archive expands from core to M0. Source downloads retain
original compressed transfer bytes where applicable; the initial format-probe
responses were stored as decoded HTTP entities and are identified in manifests.

## Photo coverage and known limits

Façade coverage is 3D triangle-area weighted over building walls with
abs(unit normal dot vertical) < 0.2. Bridges are excluded. A triangle qualifies as
photo-covered if it has a source image and non-degenerate original UV triangle
area greater than 1e-10. Image-bound area and excluded degenerate-UV area are also
reported. This measures available mapping, not photograph freshness or the
semantic content of every image pixel. Some old photographs contain vegetation
baked into walls; missing photographs remain untextured.

The core result is 86.7428068% photo-covered wall area; M0 is 72.1275698%.
Source capture dates vary and newer LOD2 is not a complete statement of 2026
construction. Zero source dimensions remain zero and are counted in the objects report.
Lamp height means mounting height, not a measured highest point of the fixture.

The alignment check compares original roof outlines with the explicit PDOK 2026
orthophoto at 0.1m per output pixel. In Aelbrechtskolk, two low courtyard sheds
fit at 0.135m; the tall northern tower fits at 1.082m. The saved crops show source
edges in cyan and fitted photo edges in magenta. The low-roof search was limited
to the visually identified roof boundary: the unrestricted strongest gradient
matched nearby paving and was rejected. Search step is 0.025m; this is not survey
accuracy. Tall-roof lean in orthophotos and source age may explain disagreement,
but this has not been proved. Uniform 0.3m alignment is not established. No
arbitrary offset or geometry changes were made to force agreement.

The two primary debug images are overlay-x90250_y436000.png and
oblique-x90250_y436000.png under renders/debug-buildings beside the repo.
Euromast uses tile x91500_y435500. Debug HTML and its temporary localhost server
are inspection tools only; they are not part of the product renderer.

## M1 result (2026-10-26)

M1 has 351 building/object tile pairs: 21,611 textured2018 buildings, 1,478 LOD2
buildings, 11 bridges, 33,150 trees and 17,697 lamps. All 23,089 buildings have
resolved BAG year/status/use; 5,253 explicitly have zero VBOs. Storeys are absent.
Photo-covered wall area is 12,675,987.2803 / 17,672,615.8907 m² (71.7267175%).
The M1 report lists the 20 largest buildings with zero photo-covered wall area,
with their BAG facts, tile ownership and measured wall area.

All 351 actual GLBs were checked for valid feature indices, finite positions,
JPEG dimensions and unique BAG IDs. A separate audit joins every feature back
to its archived pand record and every linked VBO, including response hashes.
Both audits found no issues. The BAG audit can be repeated with:

```sh
devenv shell -- python pipeline/buildings/bag.py --audit-scene
```

Current BAG marks 493 retained meshes demolished, 20 incorrectly registered,
17 with demolition permission, four out of use and 76 under renovation. These
are municipal-model/current-register conflicts, not missing BAG lookups. The
conversion preserves the specified municipal geometry inventory and exposes
the status instead of inventing a replacement or silently deleting geometry.
BAG use is a building-level union; it does not locate uses on floors or walls.

Landmark proof images cover Erasmusbrug (x93000_y436000) and Centraal
(x91750_y437500), with neighbouring owner tiles loaded. The bridge itself is
br05A040 in x92750_y436000; the station roof is BAG 0599100100007430 in
x91750_y437750. The Centraal overlay has an apparent roof-tip discrepancy of
2.96 m against the 2026 photo; Erasmusbrug deck-edge samples have a median
perpendicular discrepancy of 0.43 m (range 0.39–0.77 m). These are image-edge
measurements, not surveyed transformation residuals. These images do not
establish uniform 0.3 m roof agreement; no offset was applied to conceal the discrepancy.
