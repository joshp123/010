# Map data

Written by AI, gpt-6-astra, 2026-10-24.

The map uses public geographic records. Its geometry is not generated from a visual prompt. Code is MIT; the source datasets retain their own licenses.

The visible map uses a coherent miniature style. Raw photographic streets beside stylised buildings were explicitly rejected by the user. The photographic sources below are retained as research inputs and potential inputs to a future style-generation stage; they are not the desired final appearance. See [the requirements](../requirements/README.md).

## Municipality and overview

`public/data/municipality.geojson` is the exact, unsimplified GM0599 geometry returned by [Kadaster's official municipal boundaries API](https://api.pdok.nl/kadaster/brk-bestuurlijke-gebieden/ogc/v1/collections/gemeentegebied/items?naam=Rotterdam&f=json). It includes the port, Maasvlakte, Hoek van Holland, Rozenburg, Pernis and the eastern and southern districts. Coordinates are longitude, latitude (CRS84).

`public/data/overview.geojson` contains polygons from [Kadaster BRT TOP10NL](https://api.pdok.nl/kadaster/brt-top10nl/ogc/v1), restricted to the municipality. It is intended for wide map views, not street-scale inspection. Features have `properties.kind`: `land`, `water`, `urban`, `farmland`, `grass`, `forest` or `sand`.

The build reads the `waterdeel_vlak` and `terrein_vlak` collections over the municipal bounding box, follows pagination to completion, projects the features to RD New (EPSG:28992), clips them to GM0599, merges surfaces of each class and simplifies them with a 6-metre tolerance. Individual source polygons smaller than 100 m² are excluded from this overview. The base land geometry is the municipal polygon minus the source water polygons. Municipal boundary geometry itself remains unsimplified.

Both API landing pages declare **CC BY 4.0**. Attribution: **Kadaster / PDOK — BRT TOP10NL and Bestuurlijke Gebieden**, linked to [the license](https://creativecommons.org/licenses/by/4.0/). The overview has been clipped, simplified and classified for display. The raw source responses are cached in the local `work/data-cache/` directory; they are not part of the public site or source repository.

## Destinations

`public/data/destinations.json` is an array of public places. Each entry contains `id`, `name`, `category`, `longitude`, `latitude`, `span`, `sourceUrl` and `sourceId`. `span` is a presentation choice in metres; coordinates come from the [PDOK Locatieserver](https://api.pdok.nl/bzk/locatieserver/search/v3_1/free). Queries are restricted to municipality 0599 and a specific record type, and the build requires the expected result label rather than accepting a broad search fallback.

Neighbourhood destinations use CBS neighbourhood or BAG place centroids. Landmark destinations use a named public bridge or a published visitor address:

- [Rotterdam Centraal: Stationsplein 1](https://mijntickets.nsinternational.nl/NL/Stations/Rotterdam-Centraal)
- [Markthal: Ds. Jan Scharpstraat 298](https://markthal.nl/contact/)
- [Euromast: Parkhaven 20](https://monumentenregister.cultureelerfgoed.nl/monumenten/531142)

These are public place records, not personal locations. Destination provenance is retained in each entry. Credit PDOK, Kadaster and CBS for the underlying records. The locations indicate the public address or geographic centroid, not a surveyed point on the roof.

## Detailed 3D model

The [municipality publishes its 3D model and service links](https://www.rotterdam.nl/rotterdam-in-3d). The [national data catalogue identifies Rotterdam 3D as public domain](https://data.overheid.nl/dataset/10230-rotterdam-3d). Credit Gemeente Rotterdam for the model.

All URLs below start with `https://www.3drotterdam.nl/datasource-data/`:

| Layer | Tileset |
|---|---|
| Buildings, LOD2, newer untextured model | `8b5d0ded-a222-4e44-bc70-2992bc2192fc/tileset.json` |
| Buildings with photographic textures, mixed coverage | `a6aee273-9406-41c4-a504-de2a59f7d514/tileset.json` |
| Bridges with photographic textures | `69926a30-444d-46bb-995e-bb14b151d3ab/tileset.json` |
| Bridges, untextured alternative | `06595036-c78e-4081-ab25-e8f88b66bc19/tileset.json` |
| Storage tanks | `c70023a7-2878-41e9-bb81-a7c454bc310a/tileset.json` |
| Trees | `b9294d5b-79e0-4744-ac88-b61e3e90d5bc/tileset.json` |
| BGT streets, water, ground and quays | `0025cb58-e0f5-4169-bb4c-5339a3bc2a7e/tileset.json` |
| Light masts | `2602863a-3d22-44c2-8c95-bbf88a20bf37/tileset.json` |
| Terrain elevation, quantized mesh | `d60bdba8-c40b-42e2-bc47-78c8adabbb29/layer.json` |

The geometry uses 3D Tiles 1.0 with embedded glTF 2.0, batched models and instanced models. Cross-origin browser requests receive `Access-Control-Allow-Origin: *`. Buildings have multiple detail levels; the BGT surface set has 1,463 fixed-detail tiles and should not all be loaded at municipality zoom. The lightweight overview supplies that view.

The model's public-space objects and building records do not all have the same date. Rotterdam describes building updates as annual or biennial and public-space object updates as monthly. A centre building sample had a 2023-09-04 creation date. This is a dataset observation, not a claim that all buildings are current. The map must not imply live construction or live traffic data.

### Photographic building and bridge textures

Inspection on 2026-10-24 confirmed that the textured building service contains actual photographic facade and roof atlases, including windows, balconies and roof equipment. Replacing these materials with flat or random colors discards source detail. The legacy material format is an adaptation task, not a reason to reject the imagery.

Downloaded samples are retained in `work/source-quality/`. Filenames describe the sample area, not a claim that a particular landmark is present:

| Sample | Content path within its tileset | Verified content |
|---|---|---|
| Buildings near Wilhelminakade | `16/67169/13869.cmpt` | Three BAG objects; two JPEG atlases, 1024 × 1024 and 256 × 256; object creation dates 2018-06-05 |
| Buildings near Markthal | `17/134338/27729.cmpt` | One 2048 × 2048 JPEG atlas; object creation dates 2018-06-05 |
| Buildings in Hoek van Holland | `17/134074/27685.cmpt` | One 1024 × 512 JPEG atlas; object creation dates 2018-06-05 |
| Another Kop van Zuid tile | `17/134340/27739.cmpt` | Three objects dated 2019-06-05, but no image textures |
| Erasmusbrug | `17/134338/27736.b3dm` | Four JPEG atlases, including a 2048 × 2048 atlas with road and cycle-lane markings |

The building tileset HTTP `Last-Modified` value was 2019-11-22; the textured bridge tileset's was 2023-07-04. These are file dates. Object creation dates are model metadata, not verified photography capture dates. The examples prove useful textures and mixed ages; they do not prove current or complete textured coverage across the municipality. In particular, a textured sample in Hoek van Holland does not establish full port and Maasvlakte coverage.

The legacy building GLB materials store their image in `KHR_techniques_webgl.values.u_diffuse_tex` and their color in `u_diffuse_mat`; vertices have `TEXCOORD_0`. These can be expressed as standard glTF PBR `baseColorTexture` and `baseColorFactor`, with non-metallic rough materials, while retaining the original UVs. Composite `.cmpt` samples contain a building `.b3dm` part and a vector part. Preserve the source transforms and `CESIUM_RTC` origin. The inspected Erasmusbrug GLB already uses standard `pbrMetallicRoughness.baseColorTexture` and needs no legacy shader conversion.

Building identity matching is possible: the old and newer versions of the exact same tile `16/67169/13869` contain the same three BAG numbers, with a different order and `ID_` versus `BAG_` prefixes. The numbers also appear as `gebouwnummer` versus `GEBOUWNUMMER` in object metadata. All three newer records have creation date 2023-09-04. However, each object's vertex count changed, and maximum differences between corresponding local bounding coordinates are 1.03 m, 2.31 m and 0.032 m. Both tiles have the same origin and transform, so these are geometry differences. Copying UVs or materials by vertex index onto the newer model is not valid. An unchanged BAG number alone does not prove unchanged facades.

The practical route to photographic facades is to retain each textured mesh together with its own UVs and images. If combining old textured objects with newer geometry, match by BAG number and choose one version per object; do not render both on top of each other. Whole-municipality correspondence and selective texture transfer to changed surfaces remain unproved. The source age should remain explicit. Apply the pixel treatment after preserving this measured detail.

BGT surface colors derive from each feature's `KLASSE_IMG`, `KLASSE`, `FYSIEKVK` and `FUNCTIE` metadata, indexed through the geometry's batch ID. They describe surface classes, not photographic detail.

## Aerial imagery

The [PDOK open RGB aerial imagery service](https://www.pdok.nl/introductie/-/article/pdok-luchtfoto-rgb-open-) supplies the strongest verified improvement to ground detail. [PDOK announced nationwide 2026 high-resolution coverage on 2026-09-15](https://www.pdok.nl/-/hoge-resolutie-luchtfoto-2026-nu-beschikbaar-bij-pdok), available since 2026-09-14. The source is spring 2026 photography, at 5 cm or 8 cm depending on the acquisition parcel; do not describe every Rotterdam pixel as 5 cm.

The live [WMTS capabilities](https://service.pdok.nl/hwh/luchtfotorgb/wmts/v1_0?request=GetCapabilities&service=WMTS) were checked on 2026-10-24. Use the explicit `2026_orthoHR` layer for a reproducible edition; `Actueel_orthoHR` currently resolves to 2026 and can change. The EPSG:3857 tile matrix reaches zoom 21, with 256-pixel tiles and wildcard CORS:

```text
https://service.pdok.nl/hwh/luchtfotorgb/wmts/v1_0/2026_orthoHR/EPSG:3857/{z}/{x}/{y}.jpeg
```

License: **CC BY 4.0**. Credit **Samenwerkingsverband Beeldmateriaal / PDOK — Luchtfoto 2026**, link to the [source](https://www.pdok.nl/introductie/-/article/pdok-luchtfoto-rgb-open-) and [license](https://creativecommons.org/licenses/by/4.0/), and identify display modifications such as reprojection or pixel styling. This dataset remains separately licensed from the MIT code and public-domain Rotterdam 3D model.

Downloaded and visually inspected WMS samples in `work/source-quality/` show real streets, roofs, road markings and port infrastructure at Kop van Zuid, Hoek van Holland and Maasvlakte. `pdok-2026-street-detail.jpg` requests a 100-metre area at 1250 pixels (8 cm per output pixel); this is sampling resolution, not an independent measurement of the source ground resolution. Each `*-source.json` records the exact request. The national coverage statement plus these samples supports using the service throughout the municipality. Stream only the visible area rather than preloading the municipality at maximum resolution.

The projection experiment was rejected as the visible presentation. Orthophotos contain building lean, shadows and the acquisition-time state; projecting them indiscriminately onto ground and roofs creates false geometry cues. Retain these images as evidence and as input to a replaceable reconstruction/stylisation stage. They do not supply street-facing facade photographs. The Rotterdam elevation layer supplies terrain shape, not colour.

## Rebuilding

Run `python3 scripts/fetch-data.py` in a Nix or devenv environment containing Python 3, Shapely 2 and pyproj 3. It writes the boundary, overview and destinations into `public/data/`. Run `python3 scripts/fetch-data.py --destinations-only` to refresh only the place list. Remove or move the local response cache before requesting a newer source snapshot; otherwise builds reuse the exact cached source responses.

## Future national coverage

[3DBAG](https://3dbag.bk.tudelft.nl/nl/download) provides nationwide LoD2.2 roof geometry derived from BAG footprints and AHN airborne laser data. The [official release notes](https://github.com/3DBAG/3dbag-docs/blob/master/includes/release_notes.md) describe the 2025-09-03 release with 3D Tiles 1.1 and GLB content. Its published LoD2.2 endpoint is `https://data.3dbag.nl/v20250903/cesium3dtiles/lod22/tileset.json`. That host timed out during this investigation, so no actual Rotterdam sample from this edition was verified. It is a geometry alternative, not verified photographic facade coverage.

The [3DBAG copyright terms](https://docs.3dbag.nl/nl/copyright/) specify **CC BY 4.0**, credit **© 3DBAG by tudelft3d and 3DGI**, a source link and an indication of changes. These must be added if the data is used. The verified Rotterdam photo textures plus current PDOK imagery provide a more direct fidelity improvement than changing the building geometry source alone.

## Conflicting bridge surfaces

Native bridge meshes and BGT bridge parts overlap in the supplied datasets. `public/source-fusion.js` gives the complete native structure precedence: overlapping BGT bridge parts are suppressed, and paving within three metres of a native horizontal surface is clipped to its footprint. Adjacent paving remains. Source geometries and attributes are retained and restored when the native bridge unloads. This is geometric source reconciliation, not a correction to the upstream survey. The tolerance is a documented current choice; future source editions should be checked against it.

## Street network at neighbourhood scale

The same public Kadaster BRT TOP10NL API supplies `wegdeel_vlak`, `wegdeel_lijn` and `spoorbaandeel_lijn`. The retained municipality subset contains 64,204 road polygons, 2,495 paths and 1,925 rail lines. `source-data/transport-network.geojson.gz` preserves coordinates, source identities and the Dutch classification fields. It is input to the build, not downloaded by the browser.

`public/data/streets/manifest.json` records the exact source hash and transformation. The generated 354 standard 3D Tiles contain 233,864 triangles. The browser selects geographic tiles; a checked default desktop view requested 19 content tiles. Topology remains intact and quantisation error is bounded to 2 cm. Surface classes are styled at runtime.

`hoogteniveau` is relative ordering, not height in metres. Bridge/tunnel structures, underground levels, ferry links and disused features are excluded from this flat street layer. Narrow path widths and rail corridor widths are illustrations derived from supplied width classes/track counts. This source is not a live transport feed. Public transport observations use a separate live layer.

## Surrounding land

[Kadaster / PDOK BRT TOP10NL](https://api.pdok.nl/kadaster/brt-top10nl/ogc/v1) supplies quiet neighbouring land from official sea and major-water geometry. The source is CC BY 4.0. Geometry is simplified by 2 m in RD coordinates, then the exact municipality is subtracted so this layer cannot replace municipal land or water. Source records, acquisition metadata, component evidence and limitations are in [context-land.md](context-land.md) and `source-data/context-land.json`.

## Prepared municipal streetlights

`scripts/build-lamps.mjs` acquired all 653 advertised municipal light tiles and 154 prototypes. It extracts 104,728 unique source instance origins and source-derived head positions within GM0599 into 193 compact glTF/3D Tiles files. The full display layer is 3.88 MB raw, approximately 2.50 MB gzip; only nearby tiles are requested. The source manifest records every URL, hash, acquisition time, exclusion and coordinate assumption. Source positions are retained to roughly one-centimetre output quantisation; that is a processing bound, not survey accuracy. Straight distant shafts and glowing heads are stylistic interpretations, not observations that each lamp is currently on. Native pole geometry remains available at close range.

## Prepared public transport linkage

Written by AI on 2026-10-24 by model GPT-6.

The free [OVapi national GTFS archive](https://gtfs.ovapi.nl/nl/gtfs-nl.zip), feed version 9644 (2026-10-23 through 2026-12-12), supplies 150 routes, 793 municipality-clipped shapes and 54,584 trip links. `public/data/transit/map.pb.gz` is a 234 kB compact protobuf, defined in `source-data/transit/map.proto`. The exact Kadaster GM0599 polygon includes Hoek van Holland and the port. Source vertices are retained without simplification; clipping introduces boundary intersections and coordinates are quantised to 1e-7 degrees (at most 7 mm processing displacement). Shapes contain plan geometry, not measured tunnel depth or live positions.

The archive’s retained `licenses.txt` assigns **ODbL 1.0 to shapes.txt**, with **CC0 1.0** for the other timetable tables used. Ticketing tables with restrictive terms are excluded. Attribute **OVapi / Stichting OpenGeo, GTFS NL; shape database under ODbL 1.0** and link the [source](https://gtfs.ovapi.nl/README) and [licence](https://opendatacommons.org/licenses/odbl/1-0/). The adapted municipal shape database is available under ODbL, with share-alike terms; the MIT code licence does not replace these terms. Retain **Kadaster / PDOK, Bestuurlijke Gebieden, CC BY 4.0** for the clipping boundary and identify the transformations.

`python3 scripts/build-transit.py` in a Shapely 2 environment rebuilds retained raw input; `--download` refreshes the free sources. Full national ZIP/live snapshots remain on the SSD in ignored `work/data-cache/transit/`; public provenance, exact source licence and boundary are in `source-data/transit/`. The 23:35:26 UTC snapshot yielded 21 municipal reports (8 metro, 13 bus), all individually timestamped, ages 3–57 seconds. No municipal tram or train observation was present at that late hour; this is not a completeness result. `public/transit-feed.js` decodes upstream protobuf reports and joins metadata, preserving observation time separately from feed publication time. The app now reads both the NDOV feed and a separate NS HTTP bridge through two same-origin Worker routes. It renders unchanged reported coordinates, individual observation ages and disconnected/stale states. The local Worker and actual in-app browser path have been exercised; deployment verification remains separate. See [the live adapter](../source-data/transit/live-layer.md). The national archive has 36,882 of 937,368 trips without a shape ID, so selection through shapes cannot establish geographic completeness for those services. Unmatched municipal reports are preserved with unknown metadata.

The metro presentation uses a separate 8 KB gzip physical-form subset of the retained BRT TOP10NL rail network, credited to **Kadaster / PDOK under CC BY 4.0**. It retains 215 in-use metro/sneltram features and source IDs; only 12 explicitly tagged “in tunnel” features produce cutaway corridors. Neither missing physical tags nor relative levels establish depth. The constant graphical depth is illustrative, and the aboveground Hoek route is not made underground. Rebuild and precise display limits: [transit presentation provenance](../source-data/transit/presentation.md). This subset remains separate from the ODbL GTFS shapes database; independent renderer code is MIT.

Simulated general traffic follows actual **Rijkswaterstaat / PDOK NWB** road centre lines and junction IDs, under **CC0 1.0**. The municipality-clipped 1.19 MB gzip protobuf includes 27,218 motor-road pieces across city, Hoek and port; no straight shortcut connects disconnected roads. Kadaster / PDOK CC BY 4.0 boundary and BRT tunnel polygons supply clipping/exclusions. Cars and speeds are explicitly simulated, independently of observed transit; vertical road placement depends on rendered source surfaces. See [traffic source, licences, rebuild and limits](../source-data/traffic/README.md).
