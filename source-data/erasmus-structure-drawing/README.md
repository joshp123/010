# Erasmus structural drawing comparison

Written by AI on 2026-10-25 by model GPT-6 Astra.

This is a reversible MAIN comparison, enabled by `?bridgeDrawing=1`. It is not accepted miniature artwork. Original native bridge triangles provide the structural silhouette; generated plane UVs only store four registered drawing fields. BGT deck geometry, observed road paint, route identities and traffic remain unchanged.

The municipal shore BAG contains a photographed road surface about one metre above the native deck. The reconciliation subtracts only demonstrated overlapping upper roadway and directly connected upper road skins within the original deck footprint/height volume. Lower folded landscape walls remain. Both canonical raw sources are retained unchanged or reacquired by their pinned URLs/hashes; `shore-source.json`, `source-planes.json` and `reconciled-shore/duplicate-roadway-reconciliation.json` record them.

Preparation order: prepare-erasmus-structure-drawing.py; reconcile-erasmus-shore-source.py; render-erasmus-drawing-source.py (including --reconciled); bake-erasmus-structure-drawing.py; prepare-erasmus-drawing-review.py. The source renderer/binder uses the sibling 010-rescue-art/scripts/source-view-painter.py compiler. Prepare painted-reconciled-shore with existing prepare-bound-artwork.py into public/data/erasmus-drawn-shore. Native source cache is the existing build-bridge-surfaces.py cache contract. No source photographs or unused depth arrays are shipped to runtime.

Actual whole260m phone and north approach reviewed: road/shore continuity improves and pale structural faces retain source silhouette. The scene remains sparse/CAD; texture binding alone does not meet the whole-landmark art brief. Compare at lat51.9090 lon4.4867 span260 bearing125 and north lat51.9108 lon4.4830 span150 bearing305. Default has no bridgeDrawing query flag.
