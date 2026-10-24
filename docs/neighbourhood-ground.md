# Selected courtyard-block ground artwork

The activate-now review asset is `public/data/ground-artwork-neighbourhood/manifest.json` with `adjoining-ground.png`. It joins the existing source-covered Schiedamseweg frontage to the northern strip covering the selected 18-BAG Schiedamseweg25–39 / Noordschans14–28 block. Root selects this directory for the illustrated-neighbourhood review mode. Previous candidate files remain unchanged.

Visible changes are fuller source-visible crossings, speed30 and cycle dashes, including readable shaded parts of the southern carriageway, plus matte model-painted low planting inside the native green strips. Source image, old candidate and new frontage are compared in `docs/images/neighbourhood-ground-frontage-review.png`. Geography and paving remain driven by retained BGT triangles and source identities. New paint is original-source pixel support recoloured ivory, never photographic RGB. Individually inspected regions exclude parked cars; dash component filtering rejects isolated glints and steep pole-edge fragments without joining interrupted paint.

The full neighbourhood atlas is1600×2200 at8cm and uses71 native identities. The northern strip has source-semantic ground materials but no invented rear markings while the requested dated image remains pending. No rail strokes were added: overhead-wire shadows make some apparent linear source detail ambiguous, and this native tile contains no Spoor features.

Native imagegen produced `source-data/public-space-pilot/generation/planted-ground-paint.png`; its exact prompt, input, hash and output identifier are retained beside it. It changes ground albedo only. Tree crowns, ground heights, 3D geometry, source fixture lighting, shadows and all night behavior remain unchanged. No private library identifiers enter public provenance.

Rebuild after the standard crop-mask/material compilation:

```sh
python3 scripts/prepare-ground-street-details.py
python3 scripts/assemble-ground-areas.py --inputs public/data/ground-artwork-north public/data/ground-artwork-frontage --output public/data/ground-artwork-neighbourhood
```

This is ready for the actual integrated city review, not a claim that the holistic art direction has been accepted.
