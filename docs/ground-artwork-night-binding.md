# Bounded ground artwork and fixture-light review binding

Written by AI, GPT-6, 2026-10-24. Work in progress; no visual acceptance claim.

The Schiedamseweg artwork path is a model-painted **albedo** texture on verified BGT features. It must receive the same sunlight, object shadows and fixture illumination as the corrected row. It must not contain photographed cars, tree/building shadows or lit-night windows baked into the texture. Unknown surface detail under occlusion stays plain. The source fixture field and the building's future source-supported emission masks remain separate stages.

## Existing night evidence

`public/data/lamp-surface-lighting/manifest.json` records source-head inputs and hashes. Native positions come from source fixture geometry; supplementary head-height evidence is separate. The field stores two candidate heads per 8 m cell. Actual emission colour, reach, output and operational status remain illustrated, and the field has no occlusion solver. It is not an inventory of lit windows.

`prepareAppearanceModel` already applies `fixtureSurfaceLighting` to corrected building materials, so the painted row receives local outside light. The delivered `work/illustrated-row-review/row-review.glb` does not yet contain a verified emission/glazing inventory. Do not create emissions by thresholding every dark texel: that would illuminate roofs, door shadows, signs and occluded areas. A source-supported glazing mask may specify *where* a window is; its night operation remains explicitly illustrative.

The existing scene applies the fixture field only to buildings, industrialStructures, bridges and tanks. Ground receives screen-aligned pool sprites instead. That disconnect is especially apparent after reducing the previous blue night blanket.

## Integrated review candidate

The bounded review now applies `fixtureSurfaceLighting.apply` also to `materials.ground`, `materials.streets`, `materials.bridgeSurfaces`, `materials.industrialTerrain`, and `materials.yards` immediately after their creation. Use the same existing uniforms/field. Do not add lights or replace source lamp geometry. The existing gain 0.55 was already reduced after earlier full-façade overbrightness; keep it initially. Actual ground texture values multiply this light, preserving material identity.

The pool sprites now share the loaded surface-field strength uniform: their alpha is multiplied by one minus that strength. This preserves the existing pools until source data loads and restores them as the field fades at 2.8–3.5 km; close-view surface illumination does not double-add a screen-space pool. Lamp heads remain visible. The review needs matching day/night captures with and without the field on the same painted row, plus an ordinary adjacent street: light should follow real heads, illuminate source ground, retain façade material differences and avoid sheet-like orange bands. Surface-field selection seams and light shining through walls remain known limits.

This is a grounded illumination trial, not a proposal to add arbitrary night window grids. Actual source geometry, source dates, supported masks, material interpretation and operational illumination remain independently replaceable.
