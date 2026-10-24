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
