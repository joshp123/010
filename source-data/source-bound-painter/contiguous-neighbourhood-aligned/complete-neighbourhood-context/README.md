Written by AI on 2026-10-25 by model GPT-6.

Complete evidenced neighbourhood, first authored camera

This candidate joins the retained 208 municipal buildings, original BGT ground/base/court triangles and original inventory tree instances. It introduces no court infill or new tree locations. The orthophoto is the retained official PDOK image. Raw sources remain separate and replaceable.

`scene-120-clean.png` is the first drawing. `scene-120-bound-view-120.png` is its actual original-geometry bake. `scene-120-bound-view-300.png` is its reverse reprojection: newly exposed surfaces honestly retain source appearance. Neither is final art acceptance. Fine bright frames, imperfect source-to-drawing feature correspondence and some projection fragments remain visible.

`scene-300-continuation.png` is REJECTED: wrong camera. `scene-300-correct-camera.png` is REJECTED: photographic hierarchy and invented background beyond the original model. Neither has been bound. Complete prompts are retained beside each image. The first cleanup request timed out without an image; the second returned `scene-120-clean.png`.

The model drawing is sampled at 6 drawing pixels/metre. Native source photos are not pixel-filtered. The binder preserves already authored UV texels when continuing from a previous state. Exact retained road markings are restored from the reviewed source mask; generated road paint is excluded from the drawing.

Rebuild from the art repository with its existing devenv:

```sh
devenv shell -- python scripts/bind-neighbourhood-sequence.py source-data/source-bound-painter/contiguous-neighbourhood-aligned /Users/josh/code/010-rescue-local source-data/source-bound-painter/contiguous-neighbourhood-aligned/complete-neighbourhood-context 120 source-data/source-bound-painter/contiguous-neighbourhood-aligned/complete-neighbourhood-context/scene-120-clean.png --export
```

The stable first runtime export is `bound-scene120-buildings/` and `bound-scene120-context/`. The standard rebuild writes equivalent first-view assets to `bound-complete-scene-buildings/` and `bound-complete-scene-context/`. Building assets preserve original GLB geometry and UVs. Context assets preserve original feature/prototype triangles and original instance transforms; only the tree UV charts are new. Primitive extras retain original feature/instance IDs. Context identity metadata declares anchor root matrix, RTC, original instance transforms, original feature/triangle ownership and pinned source hashes.

The exported 120 view is a local candidate for actual desktop/phone/rotation review, with native appearance on unseen surfaces. The existing twelve explicit source-opening observations do not certify the other buildings' generated openings.

Sequential reverse continuation

`scene-300-drawn.png` and its source-support cleanup `scene-300-clean.png` returned the correct reverse drawing. The binder applied it ONLY to previously unauthored UV texels; comparison with the saved first state confirmed zero previously authored texels changed. Actual joined renders are `scene-300-bound-view-120.png` and `scene-300-bound-view-300.png`. Stable reverse exports are `bound-complete-scene-buildings/` and `bound-complete-scene-context/`. This is a candidate, not acceptance of all openings or whole-city production.

After rebuilding the first state, continue with:

```sh
devenv shell -- python scripts/bind-neighbourhood-sequence.py source-data/source-bound-painter/contiguous-neighbourhood-aligned /Users/josh/code/010-rescue-local source-data/source-bound-painter/contiguous-neighbourhood-aligned/complete-neighbourhood-context 300 source-data/source-bound-painter/contiguous-neighbourhood-aligned/complete-neighbourhood-context/scene-300-clean.png --previous-state source-data/source-bound-painter/contiguous-neighbourhood-aligned/complete-neighbourhood-context/scene-120-bound-state.npz --export
```

Actual app review found two separate limitations: directional PBR relit an already shaded drawing, and the app's native 35.26438968 degree camera exposes surfaces hidden from these 28 degree authoring cameras. Exported atlases equal the saved bound state; sampled runtime geometry/UV colours did not establish a broad export loss. `scene-120-runtime-elevation.png` shows the first-state newly exposed roof/tree strips at the real elevation. Future observations must use `runtime_camera()` in the source composer: actual geographic focus at height zero, the app's east/up/south origin and camera direction, vertical span, and viewport aspect. Its square context contains the declared runtime crop without silently changing pixels per metre. Do not change the map camera to conceal untreated surfaces.

This local sequence needed six returned model images and one timed-out request, including the two rejected reverse images. It does not demonstrate free municipality-scale throughput or a reliable trained production model.
