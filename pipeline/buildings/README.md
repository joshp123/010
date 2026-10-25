# Building conversion coordinates

Written by AI on 2026-10-25 by model GPT-6.1 Sol.

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
devenv shell -- python pipeline/buildings/rebuild.py
```

This downloads missing municipal source files, retains raw archives, builds core
then M0, renders inspection images, measures two roof/photo samples and merges
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
Whole selected buildings stay together. Bridges are selected independently from
the textured bridge source. Their source IDs remain in the feature table.
Source construction year and use are retained where supplied. No separate PDOK
BAG enrichment was needed or requested for completion.

Reports in scene/v1/buildings-{core,m0}-report.json record the actual chosen
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
construction. Two source trees have zero crown diameter and retain that value.
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
