# Illustrated row sampler review

This is a controlled renderer experiment, not an artwork improvement or a new default. The current materials use nearest magnification and trilinear minification. Vendored Three's `WebGLTextures` exits its anisotropy setup when magnification is `NearestFilter`; adding anisotropy alone would therefore do nothing.

`setAppearanceSampling(models, { renderer, preset })` from `public/appearance-sampling.js` accepts:

| Preset | Magnification | Minification | Anisotropy |
|---|---|---|---|
| baseline | nearest | trilinear mipmaps | 1 |
| linear | linear | trilinear mipmaps | 1 |
| anisotropic | linear | trilinear mipmaps | min(8, device capability) |

It changes existing base-color texture sampler properties only, deduplicates shared maps, preserves image/UV/material/mip generation and returns applied settings. The caller must request a render; use the same already-loaded models for each comparison. No scene integration or default changes are included.

Canonical `c48cfe7` runtime audit reports all ten 2048² maps loaded (223,696,213 decoded bytes including mipmaps). The audit does **not** include drawing-buffer dimensions or DPR. Its screenshots are 390×844 and 1280×720; those dimensions alone cannot establish backing-buffer density.

`python scripts/inspect-appearance-sampling.py` reproduces the retained [projected footprint evidence](evidence/illustrated-row-sampling.json) from the exact native geometry/UVs. At span100, bearing35 and an assumed 844-high framebuffer, projected facade triangles have area-weighted median major/minor footprints of 9.10/4.59 source texels per pixel; median anisotropy1.92. At assumed DPR2 those footprints halve. Bearing125 gives 7.86/4.51 and anisotropy1.80. This supports testing anisotropy: typical facade samples are minified and directionally unequal. These are projected triangle statistics, not visibility-buffer measurements: hidden facades and environmental occlusion are not removed. They do not prove a visible improvement.

Review lat51.90963, lon4.44711, span100, bearings35/125 at both viewport sizes. Keep camera, viewport, drawing buffer, lighting, weather and models fixed. Record CSS size, `renderer.getDrawingBufferSize(...)`, pixel ratio and returned sampler diagnostics. Capture baseline → linear control → anisotropic, then restore baseline. Compare actual frontage crops and moving-camera aliasing. Linear control isolates magnification from anisotropy; retain mipmaps for all three. Renderer sampling cannot fix photographic styling, invented architecture or rear patches.

Validation: `node tests/appearance-sampling.test.mjs` checks capability clamping, shared-map deduplication, no-op repeats, image/material/mipmap preservation and baseline restoration. GPU screenshot acceptance remains with the manager.

## Optional source emission compatibility (separate from sampling)

`prepareAppearanceModel(model, { applyLighting, applyCutaway, night })` now optionally accepts the scene's shared night uniform object. It scales existing glTF `totalEmissiveRadiance` immediately **before** `emissivemap_fragment`; fixture lighting remains appended after that fragment and is not scaled twice. Without `night`, behavior is unchanged. Source emissive colors/maps are retained; no window masks or emission are invented. Verified artwork emission remains a prerequisite to using this for lit windows. `node tests/appearance-emission.test.mjs` checks uniform identity, hook ordering, source asset preservation and absence of the gate when omitted. Scene wiring and visual acceptance are not included.

The integrated review hook is `__010.reviewAppearanceSampling("baseline")`, then `"linear"`, then `"anisotropic"`. It returns the unchanged view, actual drawing-buffer and CSS sizes with sampler settings. Use matching captures after each render; restore `"baseline"` afterward. This affects cached and subsequently loaded appearance models for the current session only; it is not a new public view preference.
