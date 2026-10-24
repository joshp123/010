Written by AI on 2026-10-25 by model GPT-6.

The observation vectors identify conservative pane interiors in the retained municipal source elevations. They are model judgements, not an automatic dark-pixel classification. Frames, signs, shutters, tree-obscured panes and uncertain recesses are excluded. Their depth-tested projection uses original source triangles and UVs; horizontal roof triangles cannot receive the glazing channel.

Warm emission is an illustrated glazing response. It does not represent occupancy, household activity, opening hours or real-time interior lights. There is no random occupancy selection or invented household schedule. Unobserved surfaces remain dark.

Raw source: `source-data/source-bound-painter/raw/18_268620_55472.b3dm` in the art checkout. Source/camera/depth views: `source-data/source-bound-painter/north-complete-block/model-fields/`. The original source hash and each observed image hash are pinned in observations.json; per-view projection records preserve the cameras and depth hashes. Daytime artwork remains owned by the source-bound painter. Re-run the aperture assembly against a newer handoff without changing these source judgements, or replace the observations after reviewing the raw source again.

Assembly uses `scripts/prepare-source-aperture-emission.py --source RAW --views VIEWS_JSON --observations OBSERVATIONS_JSON --handoff DAYTIME_HANDOFF --output NIGHT_HANDOFF --painter-scripts SOURCE_PAINTER_SCRIPTS`. Existing `prepare-bound-artwork.py` and `prepare-artwork-residency.py` pack the result into runtime BAG assets; the existing shared night uniform gates glTF emission.
