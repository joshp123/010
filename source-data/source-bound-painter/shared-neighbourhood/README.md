Written by AI on 2026-10-25 by model GPT-6.

Shared municipal-neighbourhood drawing candidate

Raw inputs: ../raw/*.b3dm with exact public URL and decoded/compressed SHA sidecars. Original source bytes, architecture, UVs, BAG identities and georeferences remain authoritative. Fields are model interpretation, not new city evidence.

Recreate source observations:
    devenv shell -- python scripts/source-view-painter.py prepare source-data/source-bound-painter/raw source-data/source-bound-painter/shared-neighbourhood/model-fields
Recreate original-geometry artwork handoffs:
    devenv shell -- python scripts/source-view-painter.py bake source-data/source-bound-painter/raw source-data/source-bound-painter/shared-neighbourhood/model-fields

Five built-in imagegen fields were generated from exact shared source views, the common north18 pixel painting and the retained Tiny London ordinary-neighbourhood reference. Prompts are retained alongside each field. Drawing density is6pixels/metre; model proposals are nearest-sampled into original UV atlases. Original depth excludes occluded projections. Hidden surfaces retain source material; there is no invented-window completion.

The six child directories in model-fields/bound-shared-neighbourhood are original per-source handoffs. collection.json identifies each source/BAG set. Runtime must replace matching older artwork entries, retain unmatched buildings and keep existing source-supported night masks separately. Road-like source mesh strips do not create public-space evidence.

Actual bake review: broad material/roof drawing reaches the adjoining collection, but fine scalloped aperture/edge fragments remain. Candidate requires normal/opposing/near/phone city review;117BAG count does not establish style/fidelity acceptance. No municipality throughput or trained-student claim.
