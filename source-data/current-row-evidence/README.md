# Current source for the artist's Schiedamseweg row

Attribution: **Gemeente Rotterdam — 3D Rotterdam, CC BY 4.0**, https://creativecommons.org/licenses/by/4.0/. Official current resource/license evidence is included in `source-data/current-building-evidence/catalog-evidence.json`. This is source observation, not a styled or repaired facade.

The full retained `18_268620_55473.b3dm.gz` contains **all eight buildings** selected by the art worker in legacy tile17/134310/27736. Exact crosswalk:

| Legacy batch | BAG | Source address |
| --- | --- | --- |
|59|0599100000671717|Schiedamseweg34|
|27|0599100000671715|Schiedamseweg32|
|1|0599100000671712|Schiedamseweg30|
|32|0599100000671708|Schiedamseweg28|
|17|0599100000671699|Schiedamseweg26|
|15|0599100000760416|Schans3|
|43|0599100000671675|Schiedamseweg22|
|73|0599100000760417|Schans3|

The isolated `pilot-original.glb` and two CPU views are **Schiedamseweg22**, BAG0599100000671675, 78 triangles, source model creationDate2024-11-01. Actual photography date remains unknown. Source texture visibly records cream window surrounds and facade bands, arched openings, shopfront, slate roof and dormer. Rear photographic stretching and seams remain. Neighbouring architecture visible in textures is not evidence of additional geometry; do not extrude it speculatively.

Raw b3dm carries standard glTF2 PBR with `_BATCHID` and batch IDs `BAG_` plus16digits. Each building must use its own current geometry and UVs: **never apply current images to legacy UVs**. Original image bytes, positions, normals, UVs and node transforms are preserved. RTC translation remains in external feature metadata. Compose RTC × Y-up→Z-up × node world matrix for geographical placement.

Reproduce from archive root with Python3, NumPy, Pillow:

```sh
python scripts/inspect-current-row.py
```

Use `--acquire` only if the retained native raw is absent. The pinned sourceSHA256 is checked before extraction. The archive includes all helper scripts. Whole native source is included so future interpretation can be redone rather than relying on these previews.
