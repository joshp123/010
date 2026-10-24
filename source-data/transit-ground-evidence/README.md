# Bounded native ground evidence

Acquired by AI on 2026-10-24 for the rejected metro view at latitude51.9251404, longitude4.5126138. The gzip file retains the unmodified public municipal tile response. `inspection.json` records its source URL, decoded/compressed SHA-256, attribution, class counts and exact vertical source-triangle intersections. CC BY4.0, Gemeente Rotterdam; see the linked catalog evidence in the report.

Rerun the retained query coordinates with `python scripts/inspect-transit-ground.py --refresh-report`. Inspect another point within this tile with `python scripts/inspect-transit-ground.py LONGITUDE LATITUDE`. Dependencies: NumPy and pyproj; the script reuses the retained municipal B3DM/accessor parser. Source Y-up and RTC transforms are applied before a local geodetic vertical query. Heights are source ellipsoid values, not renderer local Y. No renderer fallback or smoothing is applied.

The section sample coordinates cover ±38m around the closest physical axis (`129886927`); runtime route-axis matching may select a different feature. These are diagnostic source samples, not a claim that the runtime used exactly these vertices.

The raw report intersects `Wegdeel` at−0.986m. Negative-axis samples intersect `Wegdeel` between−1.07m and−0.78m. The centre and positive-axis samples intersect `Pand` at−1.180m, with no eligible semantic terrain beneath them. **Those Pand triangles are flat ground footprints in this tile, not elevated roofs.** The presence of840 Pand records alone does not explain the screenshot's elevated fins. A terrain-only query requires an explicit nearby-terrain estimate under those footprints; actual runtime sample heights, selected feature and coordinate transforms must still be checked. No visual acceptance is implied.

Two adjacent native building tiles are also retained, with hashes/URLs in `building-sources.json`. They supply the actual source triangles around this rejected view for `python scripts/build-metro-source-fixture.py`. The output uses a rigid local frame aligned with the nearby rail axis, without mesh simplification or building extrusion. The geometry-only CPU renderer can compare the former screen slit with whole-feature ghosting; it does not replace actual browser review.

The manager subsequently verified all 22 runtime ground samples at this view: measured surveyed ground, surface range −1.4759…−1.0602m and floor −13.4759…−13.0602m. The failure is therefore presentation/occlusion, not elevated ground sampling. The current candidate removes entire intersecting source features, retaining faint source outlines; visual acceptance remains pending.

Retained raw files and diagnostic renders are available in [metro-source-section-candidate.zip](https://chatgpt.com/library?file_id=libfile_dbe20ccd22ac81919d094b60d9031195&account_id=personal). Extract at repository root to rerun the optional actual-source fixture; ordinary runtime assets do not depend on this archive.
