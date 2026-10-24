# Surveyed lighting beyond the native lamp model

Written by AI on 2026-10-24 by model GPT-6.1 Sol.

The municipal 3D lamp service has no leaf geometry at the sampled Maasvlakte location. BGT records light-mast positions there and elsewhere in the municipality. The supplementary layer fills missing surveyed positions using the same restrained glow, ground-pool and shaft materials as the existing city lamps. It introduces no dynamic lights or browser dependency.

`source-data/supplementary-lamps.geojson.gz` retains the original selected BGT features and all request URLs and response hashes. The source is Kadaster / PDOK BGT `paal`, queried with `plus_type=lichtmast`, snapshot `2026-10-24T00:00:00Z`. Selection keeps existing, unterminated records inside the exact municipality. Its licence is CC0 1.0. These registry records are neither live operational reports nor measured lamp-head positions.

The acquisition covers the municipality's entire bounding rectangle in eight strips, follows every pagination link and clips the results to the municipal boundary. Complete response bytes remain in `work/data-cache/supplementary-lamps/`. This does not establish that every real fixture was registered.

Native prepared lamp bases and BGT points overwhelmingly coincide within 10 cm. The generator retains the nearest-native distance histogram in its manifest. It excludes only BGT points within 10 cm of an existing native base; the native preparation quantizes positions within 2 cm per axis. The rule preserves distinct nearby points and supplements internal source gaps as well as western terminals. Records that moved since the native snapshot can remain separate; neither source proves whether an older physical fixture was removed.

Ground height comes from the same AHN6 0.5 m DTM edition used by the industrial reconstruction, under CC BY 4.0. Original GeoTIFFs and their georeferencing remain in `work/data-cache/industrial-structures/`. The output manifest records their exact URLs and hashes. A source point samples its terrain cell; if that cell has no data, the generator uses the median of valid terrain cells in the surrounding 2 m window. Missing terrain yields an explicit omitted fixture, never a guessed height. BGT points with nonzero relative height level are omitted from the supplement because terrain does not locate an elevated bridge deck. The map's existing NAP numeric height convention and Earth curvature are preserved; applying a geoid conversion to this layer alone would misalign it with the native model.

Pole height is an illustrative 10 m above measured terrain. BGT does not distinguish ordinary fixtures from taller terminal floodlight towers. Warm glow, light colour, apparent brightness and 9 m pools are illustration. A pool is emitted only where its whole footprint lies inside municipal land and outside the retained unsimplified BRT water polygons. Day rendering excludes the lamp layers. Supplementary straight poles remain visible at close night scales because there is no native pole model for these records.

Rebuild with the project's Nix environment:

```sh
.devenv/profile/bin/python3 scripts/build-supplementary-lamps.py --acquire
```

Omit `--acquire` to reuse the retained BGT source. Terrain acquisition reuses the retained AHN index at `work/data-cache/industrial-structures/ahn6-copc-index.json`; its original URL is recorded in `scripts/fetch-industrial-structures.py`. Existing GeoTIFFs are reused; missing selected tiles are fetched from the same public AHN6 source. All browser outputs are standard 3D Tiles and glTF under `public/data/supplementary-lamps/`. Float32 vertex offsets are relative to individual 2 km tile centres, keeping coordinate error below 1 mm. Mesh extras retain source feature identifiers.

The source records, native reconciliation, terrain sampling and illustrative height/appearance are separate replacement boundaries. A future reconstruction can survey actual head heights or change the illustration without reacquiring or guessing the geographic points. The existing build generates gzip sidecars for this directory through `public/compressed-models.js`; the shared runtime plugin fetches and decompresses them. Each 2 km tile has three batched meshes, with no individual fixture objects or dynamic lights.

The actual-map night review shows restrained, aligned pools on quay and roads without flooding the water. Terminal container stacks remain dark: these measured fixture positions and illustrative 10 m poles do not establish terminal floodlight positions, heights, beam directions or operational state. This layer improves surveyed street/quay coverage; it does not complete realistic terminal work-area illumination. The local runtime transfer check exercised all 99 gzip routes and the shared decompression path, matching every resulting GLB byte for byte to its source. Inspect ordinary neighbourhoods and day/night views alongside the port before publishing.
