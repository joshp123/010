# Adjoining southern ground binding

This extends the source preparation to the immediately adjoining southern 128 m crop. It is a concrete native-survey binding and material candidate, **not accepted visual art**. Current single-crop files are unchanged. The dated 2026 orthophoto is pending acquisition; no source-visible markings have yet been approved for this second area.

## Retained source proof

- Original crop RD `[90249,436036,90377,436164]`; adjoining crop `[90249,435908,90377,436036]`. The shared edge is exactly northing 436036. Both are 1600² at 8 cm.
- Retained native `33577/6934` covers both crops; no synthetic or proxy ground was substituted. Complete decoded source extent is RD `[90000.205,435554.125]`–`[90491.600,436218.791]`.
- Every one of the southern crop's 2,560,000 pixels has native triangle coverage. Of those, 949,471 are eligible native semantic surfaces; 932,546 are selected paved ground. Buildings/unknown/vegetation remain untouched.
- The exact feature attributes, DGDT identities, source hash, affine binding and coverage counts are in `source-data/public-space-south/native-binding-proof.json`.
- `docs/images/ground-artwork-south-native-binding.png` shows actual native semantics beside the compiled material candidate. It is not a photographic validation or a WebGL capture.

## One acquisition command

```sh
python3 scripts/acquire-public-space-pilot.py --area source-data/public-space-areas/schiedamseweg-south.json --acquire
```

The JSON specifies exact bounds, output identity and year. It saves `source-data/public-space-south/schiedamseweg-south-2026.jpg` and matching JSON with URL, hash, date, license and pixel grid. Python requires pyproj. The direct attempt here was rejected with `Network access to https://service.pdok.nl:443 was blocked by policy.` Existing 2025 residential imagery is a smaller, differently dated subset and was not substituted or relabelled.

Then:

```sh
python3 scripts/prepare-public-space-mask.py --area source-data/public-space-areas/schiedamseweg-south.json
python3 scripts/inspect-ground-markings.py --area source-data/public-space-areas/schiedamseweg-south.json
# Visually review contact sheets against the dated source, recording accepted
# component IDs and image hash in source-data/public-space-south/marking-review.json.
python3 scripts/compile-ground-artwork.py --area source-data/public-space-areas/schiedamseweg-south.json
python3 scripts/assemble-ground-areas.py --inputs public/data/ground-artwork public/data/ground-artwork-south --output public/data/ground-artwork-adjoining
```

No review means zero markings. Accepted components must match the acquired source image hash. Paint may appear on native roads of either open or closed paving; material class alone does not decide whether a source-visible marking is valid. Model swatches are shared, while area-specific physical material overrides use stable source IDs. The original `310` batch override remains confined to the original legacy crop, not inherited by the next area. Texture phase is anchored in RD coordinates across crops.

## Runtime handoff to scene owner

The existing `createGroundArtwork` module supports the combined atlas without a new scene framework. A review scene may select `baseUrl:'./data/ground-artwork-adjoining/'`; current default remains the original single area. Do not silently enable an unreviewed extension.

The combined atlas is 1600×3200, binds 99 actual source identities and places both images without resizing or geographic overlap. Its fitted join error is 0.00203 pixels. The northern 1600×1600 RGBA array is bit-for-bit equal to the existing candidate; no original marking, material pixel or alpha value was altered. Source manifests and hash records remain attached per area. Runtime filtering still uses source ID, near-horizontal world normal, exact bounds and alpha, and it continues to respond to the same real fixture fields and shadows.

Limits: the new area has no source-reviewed road/rail markings yet; model-painted paving joints are material interpretation rather than individually surveyed objects; photographic validation and actual 3D day/night/phone judgment remain required. This is progress on reproducible adjoining coverage, not completion of the whole-city visual rescue.
