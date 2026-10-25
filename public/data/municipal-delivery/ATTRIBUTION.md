# Rotterdam central source download level

Derived from Gemeente Rotterdam — 3D Rotterdam, current textured building edition `3adbe5af-d05c-475a-b34c-59e69ba8dadc`.

Source: https://www.3drotterdam.nl/datasource-data/3adbe5af-d05c-475a-b34c-59e69ba8dadc/tileset.json
Catalogue and attribution: https://hub.clearly.app/datasets/65ef2475fe2ac522c6ac7b63/information
Licence: Creative Commons Attribution 4.0 International, https://creativecommons.org/licenses/by/4.0/

Changes: source photography is resized with BOX filtering to at most 256 pixels per image and encoded with lossless WebP. Original geometry, UVs, normals, scene/node transforms, RTC and BAG identity tables are retained. Tiles are independently gzip-compressed and concatenated in bounded content-addressed packs; the manifest records exact source/derived hashes and byte ranges. This intermediate representation is not the native close-view source; the app retains unchanged native detail as its final fallback.

Coverage: all 230 finest source leaves intersecting west 4.474, south 51.914, east 4.491, north 51.922, around Beurs/Blaak. Outside coverage uses the original source. This is a bounded operational pilot, not municipality-wide coverage or a claim of illustrated final art. No endorsement by the municipality is implied. The source dataset licence is separate from the repository's code licence.

Pack filenames are SHA256-addressed. This release must not be overwritten or retagged; changed data requires a new release identity. See manifest.json for source attribution, edition, transformations, per-tile hashes and exact pack offsets/lengths.
