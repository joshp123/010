Written by AI on 2026-10-25 by model GPT-6.

This candidate replaces the rejected previous shared drawing fields. The architectural evidence is the retained municipal source collection; the only style authority is the actual Tiny London Brixton close reference. Previous generated artwork was excluded from model inputs.

Twelve overlapping source-camera fields retain the common geographic anchor and approximately six native drawing pixels/metre. Each building belongs to one field per camera orientation, with neighbouring context still present around it. This avoids cutting a facade between independently generated fields. Source images and exact camera/depth records are retained. Ten fields also use an exact same-camera, geometry-only render of the original triangles; the first two oblique fields predate that guide. Full prompts are retained beside each native generated image. All twelve outputs are 1254 square pixels.

Prepare and bake through the existing project environment:

    devenv shell -- python scripts/source-view-painter.py prepare-overlaps source-data/source-bound-painter/contiguous-neighbourhood source-data/source-bound-painter/contiguous-neighbourhood/native-context-fields
    devenv shell -- python scripts/source-view-painter.py bake source-data/source-bound-painter/contiguous-neighbourhood source-data/source-bound-painter/contiguous-neighbourhood/native-context-fields

Preparation regenerates observations, not illustrations. The retained paint files and their full prompts are the replaceable model interpretation. Baking preserves original source identities, geometry and UVs. The output handoff is bound-overlapping-neighbourhood/collection.json with nineteen original-source children. Observed night panes are a separate assembly and must remain separate from daytime colour. The road-like source mesh strip is not authoritative public-space geometry.

This is an artwork candidate requiring actual city, opposing-view and source-aperture comparison. The model can shift observed features despite registered inputs. No generation count, texture coverage or unchanged geometry establishes visual acceptance. Built-in image generation of these fields also does not establish a practical whole-municipality production cost.
