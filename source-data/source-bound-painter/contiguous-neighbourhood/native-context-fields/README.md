Written by AI on 2026-10-25 by model GPT-6.

This candidate replaces the rejected previous shared drawing fields. The architectural evidence is the retained municipal source collection; the only style authority is the actual Tiny London Brixton close reference. Previous generated artwork was excluded from model inputs.

Twelve overlapping source-camera fields retain the common geographic anchor and approximately six native drawing pixels/metre. Each building belongs to one field per camera orientation, with neighbouring context still present around it. This avoids cutting a facade between independently generated fields. Source images and exact camera/depth records are retained. Ten fields also use an exact same-camera, geometry-only render of the original triangles; the first two oblique fields predate that guide. Full prompts are retained beside each native generated image. All twelve outputs are 1254 square pixels.

Prepare and bake through the existing project environment:

    devenv shell -- python scripts/source-view-painter.py prepare-overlaps source-data/source-bound-painter/contiguous-neighbourhood source-data/source-bound-painter/contiguous-neighbourhood/native-context-fields
    devenv shell -- python scripts/source-view-painter.py bake source-data/source-bound-painter/contiguous-neighbourhood source-data/source-bound-painter/contiguous-neighbourhood/native-context-fields

Preparation regenerates observations, not illustrations. The retained paint files and their full prompts are the replaceable model interpretation. Baking preserves original source identities, geometry and UVs. The output handoff is bound-overlapping-neighbourhood/collection.json with nineteen original-source children. Observed night panes are a separate assembly and must remain separate from daytime colour. The road-like source mesh strip is not authoritative public-space geometry.

This is an artwork candidate requiring actual city, opposing-view and source-aperture comparison. The model can shift observed features despite registered inputs. No generation count, texture coverage or unchanged geometry establishes visual acceptance. Built-in image generation of these fields also does not establish a practical whole-municipality production cost.

The known-roof comparison for BAG 0599100000688734 includes an isolated mesh and the same focused camera with all neighbours retained. The isolated mesh exposes a vertical party wall whose municipal UV photograph depicts roofs; it is hidden in the neighbouring assembly. Its photographic rectangle is not evidence of a visible roof coverage failure. The geometry-only and neighbour-inclusive renders preserve that distinction. Judge visible architecture in the actual city before changing compilation.

The coherent-plane comparison uses the same twelve model images. Connected original faces sharing a BAG and edge, with adjacent normals within five degrees, choose one observation using their common normal and original depth visibility. Geometry, UVs and the depth tolerance are unchanged. Run `bake-coherent` in place of `bake`; the output uses the distinct `-coherent-planes` handoff suffix. Its paired same-camera bake still has fragmented bright boundaries; coherent view selection alone is not an accepted repair.
