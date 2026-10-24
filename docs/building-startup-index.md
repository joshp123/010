# Building startup metadata

Written by AI on 2026-10-24 by model GPT-6.

`public/data/building-index/tileset.json` composes the existing native building tileset and its six external JSON indexes into one same-origin metadata request. It changes no building geometry, source feature metadata, measured detail or styling. All 4,849 native B3DM content URLs remain absolute upstream URLs. This removes the sequential remote root-index → external-index metadata requests before a visible building asset can start; it does not make those geometry downloads instantaneous.

Parent integration is the native buildings tileset URL only: use `./data/building-index/tileset.json` instead of the remote root URL. Keep the existing building kind, colour assignment, LOD/empty-node handling, loader and lifecycle. Hosting must serve the JSON with normal HTTP compression: the asset is 1,590,909 decoded bytes and approximately 160,878 gzip bytes. Actual first-building and first-useful-map times must be measured in the browser; no 100 ms result is claimed by this preparation.

Rebuild with `python3 scripts/build-building-index.py`. Retained compressed source responses live in `source-data/building-index/`, with original public URLs, acquisition timestamps, selected HTTP headers, decoded SHA-256 hashes and the output hash in `provenance.json`. Rebuilds reuse those pinned responses; archive/move that source directory before intentionally acquiring a newer edition. The upstream B3DM assets remain externally served and can change independently of the retained metadata edition; stale metadata requires a deliberate source refresh.

Each external content pointer becomes an additional child containing the entire external root. The original wrapper stays in place, preserving its bounding volume, geometric error, refinement and transform. The external root also retains all its fields. Existing children remain in their original order. Every non-JSON content URI is resolved against the source document URL before composition. Unexpected external up-axis changes or top-level extensions stop the build rather than silently losing their semantics. This is a static source transformation, with no runtime tree framework.

An independent comparison rebuilt the logical hierarchy directly from the seven pinned responses and compared every resulting field against the output. All 4,849 geometry URLs, six external roots and source bounds/error/refinement fields matched. The acquired metadata contains no transform fields; the composition still retains both wrapper and external-root nodes instead of relying on that absence. Original source responses remain available for independent verification and replacement.

Existing 3D Rotterdam source licence/attribution notices apply unchanged. This is metadata rearrangement of an already used source, not a new geometry dataset. The independent preparation script is MIT.
