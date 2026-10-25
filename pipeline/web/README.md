# Phone scene bake

Written by AI on 2026-10-25 by model GPT-6.

From the repository root:

```sh
devenv shell -- python3 pipeline/web/bake.py
```

Reads `scene/v1` and writes `scene/web-v1` beside it. Only the 16 core tiles
(RD x 89750–90750, y 435750–436750) are baked. The source is never written.
The output manifest keeps the source structure and metadata, limits the tile
list to those 16 tiles, and adds per-file and per-tile before/after bytes and
SHA-256 hashes under `web_bake`. Its original raster/count statistics describe
the source; the `web_bake` record describes the output encoding.

`--source`, `--output`, `--metres-per-texel` (default 0.15), and
`--texture-quality` (default 80) can override the defaults.

## Encoding

- meshoptimizer's gltfpack 1.2, added as `pkgs.meshoptimizer` in `devenv.nix`.
- `EXT_meshopt_compression` (explicit EXT, rather than the newer KHR variant),
  `KHR_mesh_quantization`: 16-bit positions, 10-bit normals, float UVs. No mesh
  simplification. Source materials receive unique names to prevent merging.
- Embedded WebP building textures, quality 80, using `EXT_texture_webp`.
  Each atlas scales to its area-weighted world/UV density at 0.15 m per texel,
  never above its source dimensions. Degenerate UV triangles do not determine
  the density. This is an atlas average, not a bound on every projected triangle.
  Unused atlas texels become a solid average colour, retaining a 16-texel margin
  around all sampled triangles for texture filtering.
- gltfpack drops custom attributes and root extras. The bake carries IDs/classes
  through floating `TEXCOORD_1`, restores their original semantic names as scalar
  float attributes with the original integer values, and restores root extras.
  `verify.mjs` decodes the resulting buffers with the browser's MeshoptDecoder
  and checks that the integer value sets survive. It does not change the renderer.
- `classes.png`: 1250 × 1250 RGBA, majority class in R, bitwise OR in G;
  ties choose the first source pixel in NW, NE, SW, SE order. B=0, A=255.
  Lossless Pillow PNG encoding without source metadata or colour profiles.
- `ortho.jpg`: 1000 × 1000, JPEG quality 80. Objects are minified JSON.

three.js needs MeshoptDecoder for these GLBs; WebP is browser-native.
No KTX2/Basis, Draco, extra texture loader, or paid service is used.

## Visual check

With the authorised `builds/dev/scene-web` symlink pointing to `scene/web-v1`:

```sh
devenv shell -- python3 tools/shot.py 'http://127.0.0.1:8790/t1.html?scene=./scene&x=90341&y=436174&z=3' '../scene/web-v1/source-phone.png'
devenv shell -- python3 tools/shot.py 'http://127.0.0.1:8790/t1.html?scene=./scene-web&x=90341&y=436174&z=3' '../scene/web-v1/baked-phone.png'
```

These use the existing screenshot tool's default 390 × 844 phone viewport at
DPR 3. Browser rendering on this Mac is not a measured physical-phone load time.

## Result on 2026-10-25

All 16 tiles: 146,772,472 → 30,075,576 bytes (79.5% reduction).
Per-tile range: 882,154–2,459,102 bytes. Three tiles meet the 1,500,000-byte
budget; thirteen exceed it. The average is 1,879,724 bytes. The largest remaining
cost is building imagery. Quality remains 80; this bake does not meet the size
target and does not establish a 100 ms physical-phone load time.

Inspected `source-phone.png` and `baked-phone.png` side by side in
`scene/web-v1/comparison.png`, at the requested position and z=3. Buildings,
shadows, trees and roads stay aligned. Small changes to texture grain and
surface edges are visible; no missing geometry or features were apparent.
Both pages loaded with the existing renderer and MeshoptDecoder, without loader
errors. The final bake's metadata, material counts, custom-attribute value sets,
source file hashes, raster dimensions, exact majority/OR channels and output
byte totals were checked.
