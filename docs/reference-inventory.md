# Pixel city references

Written by AI on 2026-10-24 by model gpt-6-astra.

## Direct predecessors

| Project | Coverage | Approach | Useful distinction |
| --- | --- | --- | --- |
| [Isometric NYC](https://isometric.nyc/) by Andy Coenen | New York City | Google 3D render, generated training examples, Qwen Image-Edit fine-tuning, adjacent infill tiles | Recognisable streets and buildings, fixed camera, deep zoom. |
| [Isometric NYC: Snow](https://isometric.nyc/snow) | Same city, winter variant | Separate snow tile pyramid and animated snow | A separately generated seasonal appearance. |
| [London, drawn](https://sheets.works/data-viz/london) by Akash Wadhwani | 216 square kilometres, roughly Zones 1–4 | Around 1,700 rendered frames, 441 generated squares, nine zoom levels | Place search and 183 annotated buildings; smaller coverage. |
| [Tiny London](https://tiny.london/) by Boris Starkov | All Greater London, 1,591 square kilometres | A shared latent across overlapping generation windows, city-specific LoRA, multiscale image tiles | Whole-city consistency and fewer seams; place search, shareable views, geographic overlays. |

Primary process accounts: [NYC](https://cannoneyed.com/projects/isometric-nyc), [London, drawn](https://sheets.works/data-viz/london/story), [Tiny London](https://tiny.london/how/). The original launch posts are [NYC](https://x.com/_coenen/status/2014359718697799989) and [Tiny London](https://x.com/ktoya_me/status/2112439926071693741). Direct X retrieval returned 403; public FxTwitter copies and primary project accounts corroborated the launches.

The [NYC source](https://github.com/cannoneyed/isometric-nyc) is MIT. Its data and imagery have separate terms. Public source was not found for either London project in this investigation. Tiny London reports roughly 31 GPU-hours for its final run and about 70 H100-hours across experiments. Those figures are not a complete monetary cost.

## Related approaches

- [nyc.world](https://nyc.world/about): top-down procedural pixel map, NOAA and NYC open data, all five boroughs; drawing and parcel claims are a separate product layer.
- [8-Bit Cities](https://8bitnyc.com/): historical NES-style overhead maps including NYC and London, based on OSM; live site definitions remain, tile rendering not verified here.
- [Tiny Trains](https://github.com/liminalapps/tinytrains): geographically grounded toy train worlds including NYC and London; multiple rendering themes. A repository exists, but no licence was identified in this review.

This is a bounded inventory of the direct family and relevant adjacent projects, not a claim that no obscure versions exist. NYC and Tiny London were also opened and visually inspected.

## Decision for 010

Keep recognisable architecture, a coherent miniature aesthetic, quiet controls, effortless exploration and shared views. Use actual Rotterdam 3D geometry so buildings can respond to changing light. Night must remain legible through illuminated windows, streets and bridges rather than a dark tint over daytime art. Illustrative light patterns are not occupancy measurements.

Use the entire official municipal polygon, including the western port and Hoek van Holland. Verify central landmarks, ordinary streets, industrial areas and the coastline. Make image copying and mobile sharing part of the first usable experience.

Use freely available municipal data. A software licence does not relicense third-party map imagery. Google-derived generated imagery and research-only model licences are not required for this implementation.
