# Local central-area delivery candidate

Written by AI on 2026-10-25 by model GPT-6 Astra.

Assets live outside Git at `/Users/josh/code/010-municipal-delivery/central-256`. The immutable pack filenames, tile offsets/lengths, source/derived/gzip hashes and CC BY4.0 edition attribution are in `manifest.json`. The reviewed three packs are published in the fixed release recorded below.

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

The shared Worker handler requires a reviewed release tag before public use. The local adapter supplies the same Range contract from the durable pack directory. A public Worker streams the exact independently gzipped member range as200gzip and may cache it by immutable gzip hash; it never fetches/decompresses the whole pack. Genuine GitHub distribution was exercised through this handler in the remote preview; deployed Worker edge-cache behaviour remains unverified.

## Actual integrated review

The MAIN8785 opt-in path was looked at in a dedicated390×844 phone tab:450m central entry, five normal ZoomIn taps, rotation to239°, close84–95m roofs/façades, normal Find reported metro, and a subsequent genuine report west of the compiled coverage. The close view requests original level18 source and returns its sharp machinery/window detail; city geometry remains present during refinement. Runtime independently repeated the explicit opt-in central broad-to-close path and confirmed derived plus native requests. The normal source outside coverage remains in use. Local disk and warm source caches mean this is operating-path/quality evidence, not public distribution speed acceptance. Architecture/style remains outside this delivery change's acceptance.

The first real review caught and corrected two integration defects before release: vendor-relative URLs had sent derived requests to the municipal origin, and equal zero parent/child geometric errors caused the vendor to skip the native leaf as unconditionally refining. The derived parent now has positive structural error while the actual error remains the physical-texture demand. Detached models are evaluated in the municipal group frame; attaching/presenting invalidates the cached demand. Scanning stops immediately once a triangle requires native detail; remaining triangles cannot change that decision. Temporary diagnostics were removed.

The operational pilot release is `municipal-central-256-20261025-a290827d998f` in the existing public repository. The released manifest adds only this fixed releaseTag to the reviewed content metadata. The three pack filenames/bytes remain unchanged. `public/data/municipal-delivery/manifest.json` and `ATTRIBUTION.md` are small deployment metadata; packs and originals remain outside Git. Hash-named assets and this tag must never be overwritten; changed content gets a new release. Repository-wide release immutability is disabled, matching its original policy.

For the genuine GitHub local preview, use `createLocalMunicipalDelivery('/Users/josh/code/010-municipal-delivery/central-256/release', { remote: true })`. This bypasses local pack reads and exercises the same fixed-origin Range handler as the Worker. The default adapter remains local for reproducible offline inspection.

## Actual GitHub delivery review

The release upload digests match all three reviewed local pack SHA256 values. Independently requested members from each pack returned exact206 ranges and decoded to the recorded tile hashes. MAIN8785 then ran the same handler with `remote:true`, without local pack reads or an injected edge cache.

A dedicated390×844 phone tab with browser HTTP cache disabled entered the central450m view. At the first actual screenshot around8seconds, real source buildings were visible while the remainder refined. Five ordinary ZoomIn taps followed by45degree rotation retained city geometry and responsive controls. The close84m view initially showed the coarse photography while original18 arrived, then settled with sharp original fans/pipes/window divisions, zero pending/refused/errors. This establishes a bounded remote transition, not blazing arrival or instantaneous native detail.

Normal Find selected a genuine C report outside pilot coverage first, correctly using original delivery. Next selected a central C report: full train/rails and city context remained visible while detail refined, then the surrounding native city settled. Subsequent genuine C reports moved the followed camera from Beurs51.91788/4.48119 to51.92024/4.48946, then51.92287/4.49680 outside the pilot. Full train/rails and real city context remained visible in both actual phone frames as detail refined; outside coverage used the original source route. There was no invented movement or freshness. The existing photo/CAD appearance remains outside the art brief; this delivery work does not accept it.

The public Site has not been changed for this pilot. The source candidate now includes the narrow Worker route using its existing Cache API and execution context; this passes the actual project Worker typecheck, but has not been deployed or edge-tested. Coverage outside this bounded central rectangle remains the unchanged original path.
