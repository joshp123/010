# Schiedamseweg ground illustration candidate

This is a bounded **review candidate**, not accepted whole-scene art direction. It adds actual parking recesses, source material distinctions, sidewalk and brick paving, and source-visible worn crossings / 30 / cycle dashes around the eight-BAG row. No aerial RGB, vehicle, photographic shadow, tree canopy or displaced roof is in the runtime texture. Unknown/non-ground pixels are transparent. The scene retains its real 3D terrain, buildings, lights and shadows.

The exact 2026 PDOK crop is RD `[90249,436036,90377,436164]`, 1600² at 8 cm. Native BGT tile is `15/33577/6934.b3dm`, retained with acquisition URLs and decoded hashes in `source-data/public-space-pilot`. Source handoff: `schiedamseweg-ground-2026.zip`; public request URLs and decoded hashes identify the source without private handoff identifiers. Metadata year bug was corrected in the acquisition script; no source reacquisition occurred.

## What controls geography

- Native BGT triangle masks, highest-surface selection, actual physical class/function and DGDT identities. Fitted world→image mapping maximum residual is 0.00270 source pixels across the crop.
- 4,395 accepted original photo pixels supply binary road-paint silhouettes. Paint RGB is newly illustrated ivory. Visual component decisions are retained in `marking-review.json`; unreviewed components never enter the asset. Source shadow/actor interruptions remain absent instead of being reconstructed.
- Model generation supplies four material swatches only, never geographic lines. Actual open/closed paving and function select each swatch; the observed rust-toned tram reservation has one documented feature override. Each swatch is antialiased to its metre scale before raster sampling. Individual joints are material illustration, not claims about measured joint positions.
- Native grass/planting, buildings, unresolved small structures and all other ground are left to the existing scene. Off-crop artwork is absent. No new rails or street furniture were added.

The full-image model redraw was rejected: it invented cycle dashes through hidden regions, erased parking recesses and redrew concealed courtyard layouts. `generation/schiedamseweg-geography-REJECTED.png` remains evidence only. The earlier residential rehearsal is also rejected and not in runtime.

## Runtime binding (scene owner)

Import `createGroundArtwork` from `./ground-artwork.js`; initialize with `{enabled:true, requestRender}`. The default remains disabled until the review scene opts in.

Apply to `materials.ground` after existing miniature/fixture shader setup. Register native `kind === 'ground'` models after `publicSpaceStyle.addModel(model)`. Their DGDT IDs and near-horizontal world normals gate the texture. Remove them on disposal. No generated ground plane is needed.

After any `sourceFusion.update()` that regenerates geometry, call `groundArtwork.refresh()`; this attaches IDs to any new geometry if it wasn't available when the retained source geometry was captured. Repeated calls skip already prepared buffers. Add `groundArtwork.diagnostics()` to the actual scene audit and dispose the module with the scene. Existing seam children are explicitly excluded.

The shader replaces diffuse albedo only. It retains current shadowing, source fixture fields and view transitions; it adds no independent night glow. Existing night bands and the photographic facade island remain unresolved larger style issues.

## Reproduce

```sh
python3 scripts/acquire-public-space-pilot.py --year 2026
python3 scripts/prepare-public-space-mask.py --year 2026
python3 scripts/inspect-ground-markings.py --year 2026
python3 scripts/compile-ground-artwork.py
```

Python dependencies: NumPy, SciPy, Pillow, pyproj. Native imagegen prompts, source inputs, rejected outputs, accepted material output and hashes are retained; stochastic generation is not claimed byte-identical. The retained swatches make compilation deterministic. Tool/model version was not exposed by the native generator.

Review `docs/images/ground-artwork-source-comparison.png`, `public/data/ground-artwork/schiedamseweg-ground.png` and actual front/rear/phone/night rendering. Top-down source comparison is evidence of alignment and exclusions, not visual acceptance of a 3D result. Current limitation: unobserved markings are sparse, paving interpretation is repeated material, source inventory dates may differ from the 2026 photo, and no real WebGL capture was possible in this environment.

Integrated runtime opt-in: `ground=illustrated`, retained in shared links. Artwork loading participates in readiness; export waits for the texture. The source texture is sampled with capability-clamped anisotropy. Example: `?appearance=illustrated-row&ground=illustrated&lat=51.90963&lon=4.44711&span=100&bearing=125&light=day`.
