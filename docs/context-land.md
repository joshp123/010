# Surrounding coastal land

Written by AI on 2026-10-24 by model GPT-6.

`python3 scripts/fetch-context-land.py` rebuilds `public/data/context-land.geojson` with the existing Shapely/pyproj environment. The source is [Kadaster BRT TOP10NL through PDOK](https://api.pdok.nl/kadaster/brt-top10nl/ogc/v1), licensed CC BY 4.0. Credit Kadaster / PDOK. Natural Earth is no longer used for this asset: its 1:10 million shoreline put visible land over sea near the Rotterdam coast.

The stage uses official sea polygons for the regional extent 3.3–5.2 E / 51.4–52.4 N. Every connected candidate land component needs an official terrestrial source record at its interior point; this prevents the outer edge of mapped sea coverage from becoming false offshore land. Retained source water records also remove major adjoining estuary/harbour waters. Covered or culverted water is excluded, and open water below one hectare is omitted in this quiet context. This is surrounding context, not complete regional hydrography.

Geometry is simplified by 2 m in the Dutch projected coordinate system. The exact Rotterdam municipality is subtracted afterwards, so none of this layer can replace surveyed municipal land or water. The shoreline can deviate within the simplification tolerance; no coast was drawn or adjusted by hand. The output is 1.36 MB raw / 540 KB gzip. Surrounding land carries no labels, structures or extra detailed surface classes.

`source-data/context-land.json` records queries, original response hashes/headers/times, source component evidence, water record dates and the output hash. Raw responses remain in `work/data-cache/context-land/`; the existing BRT response cache supplies retained major-water records. The source water records have differing acquisition dates up to 2025; API publication is not a new survey of each feature.

Geometry validation found no municipal overlap. Offshore checks west and north of Hoek van Holland remain water; adjacent coastal land continues outside the municipality. Exact output checks are in `work/source-quality/context-land-validation.json`. Integrated visual acceptance belongs to the map preview.

The integrated 1,440 × 900 daytime view at 51.995 N / 4.125 E, span 2,500 m and bearing 35° was inspected after fixing the cartographic draw order (`work/visual-qa/coast-correct-water-order.jpg`). Open sea now continues above the beach; quiet land on the right is neighbouring territory. The earlier grey sea was the municipal land fallback painting over correctly classified water, not a coastline or hole error. Explicit layer order keeps water above fallback land while leaving measured geometry in front. Three checked blue holes in the neighbouring land match two retained BRT `meer, plas` polygons and one `waterloop` polygon; checked dune ponds also match source water. The holes are meaningful geography, not triangles to fill. This confirms this coastal view, not every shoreline or source record.
