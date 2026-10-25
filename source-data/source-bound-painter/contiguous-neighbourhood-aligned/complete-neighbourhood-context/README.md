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
