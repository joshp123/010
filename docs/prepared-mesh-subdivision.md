# Spatial subdivision without geometry loss

Written by AI, gpt-6-astra, 2026-10-24.

`scripts/subdivide-prepared-meshes.py` is a delivery stage after the green-terrain and industrial-structures builders. It partitions dense prepared GLBs into 250 m cells so a small view does not fetch an entire source square or a long coastline component. Source acquisition, reconstruction and style remain unchanged.

Only source branches containing a file larger than 1,000,000 bytes are partitioned. Every triangle is assigned once by its horizontal centroid; triangles crossing a cell boundary remain intact, and their actual vertices determine the chunk's bounds. Quantized vertex attributes, node transforms, materials, winding and semantic metadata are copied exactly. Smaller vertex sets use 16-bit indices where possible. This is not mesh simplification or another quantization pass.

Industrial coarse/fine levels use the same spatial grid, original errors and `REPLACE` refinement. A shared empty GLB represents a cell missing from one level, so subdivision does not accidentally retain coarse-only geometry when the fine level replaces it. Parent bounds enclose both levels. No simultaneous coarse/fine drawing is introduced.

The build reads the output GLB back and compares every triangle's vertex attributes with its source. It checks each original triangle is assigned exactly once, preserves the material and transform values, and verifies tileset links. An independent aggregate check found identical geometry totals: green terrain 3,469,303 triangles; industrial coarse 2,560,122 and fine 5,371,230. Unchanged assets are byte-identical. These checks support exact geometry preservation; browser QA still establishes loading and rendering behaviour.

## Rebuild

After the original source builders, run with Nix Python and NumPy into a separate staging directory:

```sh
python scripts/subdivide-prepared-meshes.py \
  --input public/data/green-terrain --output work/subdivided-green-terrain
python scripts/subdivide-prepared-meshes.py \
  --input public/data/industrial-structures --output work/subdivided-industrial-structures
```

Inspect the staged tilesets, then move the previous public layer into ignored `work/` and move the staged layer into its public location. Rebuild the site after the swap. The original prepared files from this run are retained at `work/before-subdivision-green-terrain/` and `work/before-subdivision-industrial-structures/`. Each new manifest records original file hashes, per-chunk triangle counts and validation. Original builder metrics remain under `tilesBeforeSubdivision`.

## Observed asset changes

| Layer | Total GLB bytes before → after | Largest GLB before → after |
| --- | --- | --- |
| Green terrain | 43.84 → 38.98 MB | 11.24 → 2.64 MB |
| Industrial structures | 139.52 → 115.21 MB | 9.79 → 1.20 MB |

The largest terrain source spans 2.2 × 7.1 km, rather than the implied size of its native tile name. In a 1.8 km Maasvlakte view, a bounding-box frustum estimate selects 11.30 MB of terrain before subdivision and about 60 KB after it: most of that source geometry is outside the view despite its large original bounds. Industrial selection drops from 14.50 to 9.61 MB in that view. At 550 m and 350 m port views, it drops from 5.37 to 3.34 MB and from 12.24 to 5.97 MB respectively.

These estimates use the map's orthographic camera at 1440 × 900, DPR 2 and industrial screen error 8. They are not network or browser timings. At the 2.5 km dune view, estimated terrain bytes decrease only 9.95 → 8.19 MB and visible triangle count barely changes. More small files/draws may offset some benefit there; a matched browser run must decide. Exact inputs/results are retained in `work/source-quality/height/partition-view-estimates.json` and `subdivision-validation.json`.

## Startup and deployment checks

The municipal boundary, overview and surrounding-context JSON occupy 0.184, 3.919 and 1.362 MB decoded. Their local gzip sizes are 0.074, 0.777 and 0.540 MB. Context was fetched in the same blocking group as the municipal overview; the renderer now loads it separately. Prebuilding a heavier overview mesh was previously rejected, so this change does not repeat that tradeoff.

Local gzip size is not proof of production transfer size. After deployment, inspect actual `Content-Encoding`, transferred bytes and cache headers for JSON, JS and GLBs, then compare cold and warm loads. Measure first useful map, first buildings, settled visible detail and input-to-frame response separately. The current source-stage improvements do not establish the user's roughly 100 ms ambition, especially on a cold remote connection or a phone.
