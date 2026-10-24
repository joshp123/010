# Building appearance review candidate

This bounded candidate replaces generic coloured facades with retained municipal appearance evidence around Delfshaven and Kop van Zuid. It is **not** a claim of Tiny London quality, contemporary geometry, or whole-city appearance coverage.

The 2019 municipal textured edition contains photographic facade/roof atlases with real window rhythm, balconies, masonry and rooftop equipment. Those details are absent from the newer untextured mesh's material. The original geometry and its UVs must travel together: matching BAG identity does not make old UVs valid on newer geometry.

## Rebuild

```sh
python scripts/prepare-building-appearance.py --acquire # network acquisition, once
python scripts/prepare-building-appearance.py           # retained bytes only, miniature preset
python scripts/prepare-building-appearance.py --style baseline # less stylised comparison
```

Python dependencies: NumPy and Pillow. The explicit review windows are at the top of the script. The transform never fetches missing sources unless `--acquire` is present. Raw `.cmpt` and JSON bytes are stored losslessly compressed under `source-data/building-appearance/raw/`; each has an acquisition date, source URL, Last-Modified value and decoded SHA-256 sidecar. The compact provenance manifest pins source hashes. A missing local raw file can be downloaded again, but changed upstream bytes fail verification rather than silently changing the edition. Files contain public municipal geographic source records, not private user data.

The output uses standard glTF2 PBR materials and a 3D Tiles index at `public/data/building-appearance/tileset.json`. Original source normals, vertex positions, UVs and node transforms are retained. The legacy `CESIUM_RTC` origin becomes an explicit ECEF translation in each tile. The Y-up convention is preserved. Misaligned legacy buffer views are repacked; batch triangles are split into individually identified BAG meshes without changing positions. Mesh and node `extras.bagId` are numeric strings. Tiles and the manifest list the same identities.

Only buildings with at least one actual textured primitive enter the candidate. Untyped or untextured-only buildings are left to the newer municipal model. The renderer must suppress matching newer geometry **only while the replacement tile is visible**, restoring it on unload; rendering both editions causes z-fighting and incorrect double buildings.

## Interpretation, separately replaceable

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
