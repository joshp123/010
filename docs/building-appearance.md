# Building appearance review candidate

This bounded candidate replaces generic coloured facades with retained municipal appearance evidence around Delfshaven and Kop van Zuid. It is **not** a claim of Tiny London quality, contemporary geometry, or whole-city appearance coverage.

The 2019 municipal textured edition contains photographic facade/roof atlases with real window rhythm, balconies, masonry and rooftop equipment. Those details are absent from the newer untextured mesh's material. The original geometry and its UVs must travel together: matching BAG identity does not make old UVs valid on newer geometry.

## Rebuild

```sh
python scripts/prepare-building-appearance.py --acquire # network acquisition, once
python scripts/prepare-building-appearance.py --style source # retained evidence, no palette filter
python scripts/prepare-building-appearance.py --style baseline # less stylised comparison
```

Python dependencies: NumPy and Pillow. The explicit review windows are at the top of the script. The transform never fetches missing sources unless `--acquire` is present. Raw `.cmpt` and JSON bytes are stored losslessly compressed under `source-data/building-appearance/raw/`; each has an acquisition date, source URL, Last-Modified value and decoded SHA-256 sidecar. The compact provenance manifest pins source hashes. A missing local raw file can be downloaded again, but changed upstream bytes fail verification rather than silently changing the edition. Files contain public municipal geographic source records, not private user data.

The output uses standard glTF2 PBR materials and a 3D Tiles index at `public/data/building-appearance/tileset.json`. Original source normals, vertex positions, UVs and node transforms are retained. The legacy `CESIUM_RTC` origin becomes an explicit ECEF translation in each tile. The Y-up convention is preserved. Misaligned legacy buffer views are repacked; batch triangles are split into individually identified BAG meshes without changing positions. Mesh and node `extras.bagId` are numeric strings. Tiles and the manifest list the same identities.

Only buildings with at least one actual textured primitive enter the candidate. Untyped or untextured-only buildings are left to the newer municipal model. The renderer must suppress matching newer geometry **only while the replacement tile is visible**, restoring it on unload; rendering both editions causes z-fighting and incorrect double buildings.

## Rejected filter experiments, retained for comparison

Source mode is the default. The manager rejected both palette presets as art direction; they remain reproducible historical comparisons, not the intended city treatment. The next art candidate is whole-building model interpretation with source checks, supplied separately.

The initial atlas transform applies a 3×3 median filter, modest saturation reduction and a 24-colour median-cut palette without dithering, followed by 3×3 mode filtering of palette indices to merge isolated noise into existing colour regions. `--style baseline` retains the first, gentler 48-colour transform without mode filtering. It does not invent windows, rooftop plant, balconies or decorative details. Source UVs preserve their placement. `facade-presets.jpg` and `roof-presets.jpg` compare the source, baseline and miniature presets at identical atlas coordinates. This is a deliberately modest, reproducible interpretation to test whether the retained detail supplies a useful basis for the miniature. It is not equivalent to the reference projects' learned redrawing, and may retain photographic shadows, occlusions and uneven source resolution. Those must be judged in actual rendered views.

The original atlases remain inside retained raw sources, so future models can replace the interpretation from first principles. `atlas-comparison-*.jpg` places the original and transformed atlas side by side for inspection; these are **not** scene screenshots. Output manifest hashes pin each prepared GLB. No image-generation service or paid resources are used.

## Known limits / acceptance gates

- Source is the older municipal edition; reported object dates are not photography capture dates. Some buildings may have changed since acquisition.
- Texture detail does not create missing silhouette geometry: flat photographed balconies remain flat, and rooftop equipment in a photograph does not become surveyed 3D machinery.
- Texture atlases contain baked daylight and shadows. Dynamic night emission must not claim observed occupancy or apply a second unrelated regular window grid.
- Coverage is intentionally limited to two review windows. Do not silently scale this source replacement across the municipality before comparing old/current shapes and appearance availability.
- Cloud QA browser cannot create WebGL. Manager must assess daytime/nighttime, source alignment, ordinary streets and colour coherence before any publication.
- Source: Gemeente Rotterdam / Rotterdam 3D, public-domain model; see `docs/data-sources.md`. Source-data terms remain separate from MIT application code.

### Per-building buffer compaction (cache correction)

The first split-BAG conversion kept each tile's complete attribute arrays on
all of its building meshes. The renderer's `Bt`/geometry estimator charges arrays
per geometry, so this inflated the shared city cache and could evict surrounding
buildings. Each primitive now stores only its referenced vertices; indices are
remapped without changing triangle order or winding, and fit in uint16 where
possible. Source positions, normals, UV values, materials, atlas bytes, node
transforms and BAG IDs remain unchanged. No cache limit increase is involved.

Across the 15 prepared tiles, per-geometry accounted attribute/index bytes fall
from **141,160,536 to 3,564,528** (97.5% reduction). GLB download/storage grows
slightly, **28,963,788 to 29,326,696 bytes**, because small accessor/mesh records
and some vertices shared between source primitives are now separate. These are
geometry accounting numbers, not total GPU/texture memory or a browser outcome.

The download/storage sizes above record the historical compaction comparison,
not a promise that later appearance presets produce the same PNG sizes.

Run `python tests/building-appearance-compaction.py` after rebuilding. The check
uses manifest-to-source mappings and the retained municipal `.cmpt` archives;
it requires neither local git history nor network access and does not rewrite
assets. It verifies all **36,840 triangles** by expanding source BAG selections
and compact output indices, comparing every retained attribute (including
POSITION, NORMAL and UV where present), data types and normalized flags exactly.
It also checks BAG identities, source node transforms/hierarchy, explicit RTC
translation, material conversion and texture bindings, bounds, output hashes,
and referenced-vertex-only storage. Accounting the source arrays once per split
primitive independently reproduces the historical **97.5%** reduction.

Original JPEG bytes intentionally become PNGs. Exact decoded RGB pixel equality
is checked only when the prepared manifest records `--style source`; miniature
and baseline presets deliberately change pixels and skip that assertion. The
geometry and identity checks apply to every preset. The earlier 15-tile compact
candidate also passed Khronos validation with zero errors and warnings; that
historical validation is separate from this source-comparison test. The manager
still needs to verify cache behavior and neighboring buildings in the browser.

### Source-sampling texture LOD

The appearance tiles now use a `REPLACE` chain: at most 512-pixel atlases,
then at most 1024, then the original prepared atlas. Limits apply to each atlas's
largest dimension with aspect preserved; redundant levels are omitted when the
original already fits. Each lower-resolution image is a BOX area sample of the
same prepared source image. Native image bytes and all geometry/UV/accessor
values remain unchanged. This is sampling LOD, not a new artistic treatment.

The RTC transform is only on the outer tile and is inherited by descendants.
All levels retain the same world-region bounds and BAG IDs. Each coarse level's
`geometricError` is its physical sampling footprint: median non-degenerate
triangle-edge metres per atlas texel per material, taking the largest material
median in the tile. This is a sampling proxy, not geometric displacement. The
native leaf has error zero. Runtime must use a positive appearance error target
(e.g. 1 pixel); zero explicitly forces the native leaves.

`manifest.json` records level dimensions, decoded RGBA bytes including the full
mip chain, sampling footprint, hashes and stored bytes. Estimates exclude mesh,
texture-driver overhead and transient parent/child overlap during replacement.
The full source remains available at close zoom, so the complete native set can
still exceed the city cache; this change targets views where those original
texels are smaller than a screen pixel. Essential base layers should retain
loading priority, and actual browser eviction/transition behavior requires review.

Run `python tests/building-appearance-lod.py` after preparing assets to check
all levels against native accessors and verify one inherited RTC transform,
strictly decreasing errors, and a zero-error native leaf. The original
compaction test still checks native files against the earlier source candidate.

For the current 15-tile candidate, all-512 decoded RGBA+mips totals **24 MiB**,
all-1024 **96 MiB**, and native **336 MiB** (each total chooses the appropriate
available level per tile). There are 43 content levels because two native tiles
already fit 1024. Every level passes Khronos validation with zero errors and
warnings; all accessor values match native exactly.

### Native spatial residency and source-texel packing

Close views now replace the last coarse context level with separate BAG
contents, each culled by a tight **oriented** box in tile-local ECEF. The box is
computed from the actual vertices after source node matrices and glTF Y-up to
3D Tiles Z-up; its source-aligned axes avoid the excess volume of an ECEF axis
aligned box. The RTC translation still occurs only on the outer context tile.
The original full native GLB remains an offline reference, not a runtime leaf.

A single union crop per building was rejected: atlas islands are scattered and
union rectangles duplicated gigabytes of unused area. Instead, triangles are
grouped by connected UV edges. Their source image rectangles are copied without
resampling into a deterministic per-BAG atlas, with two native pixels of gutter.
No geometry positions/normals change. UV coordinates receive a reversible affine
crop/placement transform. Unreferenced images and source attributes are excluded.
Each GLB's `extras.texturePacking` retains original asset/hash, source image size,
crop rectangle, packed origin and source triangle indices for every island.
Raw municipal sources remain untouched. Coarse context still supplies distance
sampling; the packed native level is for approximately native-texel views. Deep
mip values around new packing boundaries can differ from the original atlas;
this is not a claim of identical arbitrary-mip sampling.

`python tests/building-appearance-spatial.py` verifies every packed rectangle's
pixels exactly, all expanded position/normal triangle arrays, inverse UV error
below 3e-7, tight enclosing oriented boxes, per-BAG identities and leaf culling
structure. This supplements the source-compaction and context-LOD tests.
`--reuse-native` reruns residency conversion without repeating photographic
preparation; it rejects a different `--style` from the existing native manifest.
This mode is for local iteration, while normal `--acquire` remains the complete
rerunnable pipeline. It does not lower native texture resolution or raise cache
budgets. Cache savings depend on visible buildings and must be browser-verified.

The retained candidate packs 550 BAG contents with 11,734 exact source-pixel
rectangles. Across the entire prepared area, native decoded RGBA+mips now totals
**325.25 MiB**, versus 336 MiB for shared full-tile atlases. Packing is rectangular
NPOT, selecting the lower-area result of shelf and MaxRects arrangements; the
largest current atlas dimension is 3455 pixels. The primary gain is visibility
residency, not this modest whole-area total reduction.

A conservative source-box projection at Delfshaven (51.9098, 4.448), span 200,
bearing 35 estimates **131 visible BAGs / 67.59 MiB** at 390×844 versus 168 MiB
for intersecting old native tiles. At 1440×900 it estimates **357 / 170.69 MiB**
versus 240 MiB. Run `python tests/building-appearance-residency-estimate.py` to
repeat. These are projected-box texture estimates, not measured browser usage;
they exclude geometry, base layers, cached offscreen items and transition overlap.
In particular, adding the manager's measured 78 MiB base to the desktop estimate
can still exceed the 224 MiB shared cap. Actual close-view acceptance remains a
manager browser check, and this implementation does not claim universal fit.

All 550 content GLBs validate with zero errors/warnings. Exact source-compaction,
LOD and spatial tests pass: 36,840 triangle attribute matches, every crop pixel
matches the native reference, and inverse UV maximum error is below 1.5e-7.
Leaf centers also independently fall within their original geographic source-tile
envelopes after one RTC translation and correct source/up-axis rotation.

## Explicit current-edition source candidate

The current official textured UUID `3adbe5af-d05c-475a-b34c-59e69ba8dadc`
uses native glTF2 PBR and substantially clearer photographic observations in the
reviewed Schans and Schiedamseweg pilots. The resource-specific catalog now
states **CC BY 4.0**, attribution **Gemeente Rotterdam — 3D Rotterdam**;
see `source-data/current-building-evidence/catalog-evidence.json`. Model
creationDate2024-11-01 is not a verified photographic capture date.

This path is deliberately explicit and writes separate source and output
folders. Legacy archives and their geometry/UV relationships remain unchanged.
Native current PBR values survive conversion; only the legacy material extension
is translated. Current geometry always carries its own current UVs and images.
Source-style RGB pixels remain exact. Finest spatial leaves retain native pixels;
coarser texture levels are temporary view-dependent sampling levels.

```sh
python scripts/prepare-building-appearance.py --edition current --acquire \
  --tile 18/268620/55473.b3dm --tile 18/268621/55475.b3dm \
  --tile 18/268679/55479.b3dm
python tests/building-appearance-compaction.py --current
python tests/building-appearance-spatial.py --current
python tests/building-appearance-lod.py --current
```

The first leaf contains all eight BAGs in the artist's Schiedamseweg row, the
second contains the modern Schans66–80 pilot, and the third contains the centre
tower pilot. Explicit leaf selection verifies those leaves exist in the native
hierarchy and retains their bounds. No guessed replacement bounds or mixed-edition
UVs are used. Without `--tile`, current edition uses the existing bounded two-area
selection; it is not a whole-city acquisition command.

Select this candidate in the app with `?appearance=current` (append the usual location, span, bearing and lighting parameters). The separate source index is `/data/current-building-appearance/tileset.json`; the default remains the previously reviewed legacy evidence until visual review.
Generated GLBs and duplicate acquisition gzip archives are ignored in this path;
pinned hashes, URLs, manifests and code are committed. Original complete evidence
archives remain retained under the evidence folders. Reacquisition fails if the
upstream bytes no longer match committed provenance, requiring explicit review.
This is stronger photographic source evidence, **not** a claim of finished pixel
art or resolved night appearance.

Verified three-leaf candidate:49BAGs,4,324 unchanged source triangles,42 exact
source RGB atlases,1,698 exact native pixel rectangles. Packed UV inverse error
is at most0.000162 source pixels (float32 rounding), with all current atlas edges
≤8192 pixels and no native resampling. All55 GLBs pass Khronos validation with
zero errors/warnings. A separate network reacquisition of the9,644,080-byte row
source matches the pinned SHA256. All49 finest contents together decode to
187.41MiB including mips; that is an all-content total, not a measured view's
residency. Browser scene completeness and rendering remain manager review.

`python scripts/compare-building-editions.py` independently transforms the two
residential observations to RD xy plus ellipsoidal height. Their native triangle
counts and envelopes agree within3micrometres: improved photographic observation
must not be misrepresented as increased geometry detail. The tower independently
changes from1,226 to1,394 triangles. Photography date is still unestablished.
