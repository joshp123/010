Written by AI on 2026-10-24 by model GPT-6.

Complete north18 building drawing candidate, not art/fidelity acceptance. Current replacement: bound-model-drawn-block-pixel. Earlier rejected architectural drawing remains in views-v3.json and its original paint fields; its handoff is preserved separately.

The common-scale replacement uses five newly model-composed pixel fields: two steep opposing views, two court/end-wall views and the top roof. The model was explicitly asked to draw at320px whole-block scale, with broad wall/roof masses and selective dark/recess/highlight clusters. The court edits use the earlier interpreted court field plus exact source evidence, chosen new whole-block drawing and Tiny London ordinary Brixton style reference. Full prompts are common-pixel-{drawing,roof,court}-prompt.txt. Five successful built-in generations produced this replacement. Remaining earlier cardinal fields are low-confidence fallbacks for surfaces not observed by those five views; they are not proof of newly painted unobserved sides.

Internal source recovery lives at source-data/source-bound-painter/raw/18_268620_55472.b3dm. The adjacent README pins its public URL and compressed/decoded hashes. Use this path for the commands below on the internal clone. Code and fields are committed in this durable internal repository; generated depth/atlas/GLB outputs can be rebuilt.

The source is the retained municipal leaf18_268620_55472.b3dm.gz in the adjoining rescue-review checkout. DecodedSHA256: d898d44dc9d6440779d5c5b9784da9e9361a771b344e630ca523749c6c6ad596. No source bytes or geometry were edited.

Each source view is an exact orthographic projection of that geometry. Its corresponding paint image was produced by the built-in image generation tool using the retained prompt and Tiny London visual reference. The model supplies whole architectural drawing composition, rather than material exemplars. Nine views cover outer streets, roofs and inner courts. views.json retains camera registration, source fingerprint, selection confidence and drawing scale. Candidatev3 samples only these model drawings at384pixels across the54m block, approximately7pixels/metre. This is not a source-photo pixel filter.

From the worktree root, regenerate derived depth and bake with existing devenv dependencies:

```sh
devenv shell -- python scripts/source-view-painter.py prepare ../010-rescue-review/source-data/current-building-appearance/raw/18_268620_55472.b3dm.gz source-data/source-bound-painter/north-complete-block/model-fields
devenv shell -- python scripts/source-view-painter.py bake ../010-rescue-review/source-data/current-building-appearance/raw/18_268620_55472.b3dm.gz source-data/source-bound-painter/north-complete-block/model-fields
devenv shell -- python scripts/source-bound-painter.py render ../010-rescue-review/source-data/current-building-appearance/raw/18_268620_55472.b3dm.gz source-data/source-bound-painter/north-complete-block/model-fields --mode painted
```

Latest handoff: bound-model-drawn-block-v3. Earlier full-resolution handoffs remain separately retained. Runtime imports original BAG identities, UVs, transforms and triangle geometry using its existing bound-artwork compiler.

Actual baked opposing views exposed the need for elevated court observations; those were added to the generic preparation operation. Side elevations have lower drawing confidence because their municipal textures include aerial roof projections on vertical party walls. The model was instructed to draw those as plain walls and retain uncertain occlusions without invented openings.

Remaining limits: model canvas/internal feature movement is not mathematically prevented by this compiler; original geometry does not establish aperture fidelity. Thin source/registration seams remain in actual baked views. The first integrated city view remained too photographic/architectural. Candidatev3 still needs normal and close opposing city judgement against the original miniature brief. This block is a production mechanism trial, not whole-neighbourhood or municipality completion. Ten successful image generations plus one failed attempt were required for these views and roof correction; this is teacher artwork, not a scalable municipality operating cost demonstrated by a trained student.
