# Map data

Written by AI, gpt-6-astra, 2026-10-24.

The map uses public geographic records. Its geometry is not generated from a visual prompt. Code is MIT; the source datasets retain their own licenses.

## Municipality and overview

`dist/data/municipality.geojson` is the exact, unsimplified GM0599 geometry returned by [Kadaster's official municipal boundaries API](https://api.pdok.nl/kadaster/brk-bestuurlijke-gebieden/ogc/v1/collections/gemeentegebied/items?naam=Rotterdam&f=json). It includes the port, Maasvlakte, Hoek van Holland, Rozenburg, Pernis and the eastern and southern districts. Coordinates are longitude, latitude (CRS84).

`dist/data/overview.geojson` contains polygons from [Kadaster BRT TOP10NL](https://api.pdok.nl/kadaster/brt-top10nl/ogc/v1), restricted to the municipality. It is intended for wide map views, not street-scale inspection. Features have `properties.kind`: `land`, `water`, `urban`, `farmland`, `grass`, `forest` or `sand`.

The build reads the `waterdeel_vlak` and `terrein_vlak` collections over the municipal bounding box, follows pagination to completion, projects the features to RD New (EPSG:28992), clips them to GM0599, merges surfaces of each class and simplifies them with a 6-metre tolerance. Individual source polygons smaller than 100 m² are excluded from this overview. The base land geometry is the municipal polygon minus the source water polygons. Municipal boundary geometry itself remains unsimplified.

Both API landing pages declare **CC BY 4.0**. Attribution: **Kadaster / PDOK — BRT TOP10NL and Bestuurlijke Gebieden**, linked to [the license](https://creativecommons.org/licenses/by/4.0/). The overview has been clipped, simplified and classified for display. The raw source responses are cached in the local `work/data-cache/` directory; they are not part of the public site or source repository.

## Destinations

`dist/data/destinations.json` is an array of public places. Each entry contains `id`, `name`, `category`, `longitude`, `latitude`, `span`, `sourceUrl` and `sourceId`. `span` is a presentation choice in metres; coordinates come from the [PDOK Locatieserver](https://api.pdok.nl/bzk/locatieserver/search/v3_1/free). Queries are restricted to municipality 0599 and a specific record type, and the build requires the expected result label rather than accepting a broad search fallback.

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
| Buildings, LOD2 | `8b5d0ded-a222-4e44-bc70-2992bc2192fc/tileset.json` |
| Bridges | `06595036-c78e-4081-ab25-e8f88b66bc19/tileset.json` |
| Storage tanks | `c70023a7-2878-41e9-bb81-a7c454bc310a/tileset.json` |
| Trees | `b9294d5b-79e0-4744-ac88-b61e3e90d5bc/tileset.json` |
| BGT streets, water, ground and quays | `0025cb58-e0f5-4169-bb4c-5339a3bc2a7e/tileset.json` |
| Light masts | `2602863a-3d22-44c2-8c95-bbf88a20bf37/tileset.json` |

The geometry uses 3D Tiles 1.0 with embedded glTF 2.0, batched models and instanced models. Cross-origin browser requests receive `Access-Control-Allow-Origin: *`. Buildings have multiple detail levels; the BGT surface set has 1,463 fixed-detail tiles and should not all be loaded at municipality zoom. The lightweight overview supplies that view.

The model's public-space objects and building records do not all have the same date. Rotterdam describes building updates as annual or biennial and public-space object updates as monthly. A centre building sample had a 2023-09-04 creation date. This is a dataset observation, not a claim that all buildings are current. The map must not imply live construction or live traffic data.

The textured building layer is intentionally not the primary source: a sampled tile was older, heavier and used legacy glTF shader extensions. Stylized colors are applied to the more suitable untextured geometry. BGT surface colors derive from each feature's `KLASSE_IMG`, `KLASSE`, `FYSIEKVK` and `FUNCTIE` metadata, indexed through the geometry's batch ID.

## Rebuilding

Run `python3 scripts/fetch-data.py` in a Nix or devenv environment containing Python 3, Shapely 2 and pyproj 3. It writes the boundary, overview and destinations into `dist/data/`. Run `python3 scripts/fetch-data.py --destinations-only` to refresh only the place list. Remove or move the local response cache before requesting a newer source snapshot; otherwise builds reuse the exact cached source responses.

## Future national coverage

[3DBAG](https://3dbag.nl/nl/download) provides nationwide LoD2.2 building geometry under [CC BY 4.0](https://docs.3dbag.nl/nl/copyright/). It is a possible future source for extending the product beyond Rotterdam, not a dependency of the current municipal map. Its required attribution differs from the Rotterdam model and must be added if that data is used.
