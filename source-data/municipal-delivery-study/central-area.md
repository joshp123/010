# Local central-area delivery candidate

Written by AI on 2026-10-25 by model GPT-6 Astra.

Assets live outside Git at `/Users/josh/code/010-municipal-delivery/central-256`. The immutable pack filenames, tile offsets/lengths, source/derived/gzip hashes and CC BY4.0 edition attribution are in `manifest.json`. No release upload occurred.

The complete rectangle [west4.474,south51.914,east4.491,north51.922] covers230 source leaves around Beurs/Blaak and ordinary central streets. Stations at Eendrachtsplein/Leuvehaven fall outside this rectangle and retain the original source path. The compiler selected all finest tiles whose official bounding regions intersect the rectangle; it did not select attractive individual buildings.

Actual source wire1,622,314,665bytes; derived independently gzipped256 textures173,808,756bytes in3 bounded packs. This central photography is heavier than the full-city sample mean. These byte reductions do not establish arrival speed or image-quality acceptance.

All230 actual output tiles were checked against retained originals: non-image buffer bytes, accessors, mesh/node/scene structure, UVs and the complete feature/batch tables (including RTC/BAG) are unchanged. All51 images in the first/middle/last output tiles were decoded and matched exact BOX256 source pixels. The local shared range handler returns200+Content-Encoding:gzip, with bytes matching the recorded derivedB3DM hash. Actual browser/zoom/native refinement remains the acceptance path.

## Reproduce

Use the existing project Python/Pillow environment:

```
python scripts/compile-municipal-delivery.py --output /durable/path/central-256 --bbox 4.474 51.914 4.491 51.922 --acquire --workers 2
python scripts/verify-municipal-delivery.py /durable/path/central-256
```

The first command retains original source responses under `raw/`, resumable per-tile compilation under `compiled-tiles.json`, independent gzip tiles under `tiles/`, then assembles content-hash-named packs and a stable manifest. Re-running without `--acquire` uses retained source bytes. A different output limit invalidates the previous level's compile records while retaining its raw sources.

The original source's occasional tiny-UV triangles make a global worst-world-texel error unusable. The opt-in municipal helper therefore loads genuine256 geometry/materials as an intermediate source representation, then measures the actual visible triangles against the registered camera's physical pixel resolution. This uses the existing two-texel-per-physical-pixel convention, preserves the unmodified official tile as its REPLACE close child, and keeps the source ancestor while that child loads. Material metadata retains the original256 dimensions even if GPU residency subsequently uploads a smaller image. No median threshold, new cache allowance, final native simplification or source identity remapping is introduced.

`?sourceMips=256` enables the local candidate. Outside the exact manifest coverage, the source hierarchy is untouched. A missing derived response falls back to the original source URL. The main default remains unchanged.

The shared Worker handler requires a reviewed release tag before public use. The local adapter supplies the same Range contract from the durable pack directory. A public Worker streams the exact independently gzipped member range as200gzip and may cache it by immutable gzip hash; it never fetches/decompresses the whole pack. GitHub distribution/cold latency has not yet been proved for these new assets.
