# Actual map views

Written by AI on 2026-10-24 by model GPT-6 Astra.

These captures come from the running map in the Codex in-app browser. The requirements and original steering remain the quality target; these images make the current interpretation inspectable by the next person or model.

Public release verification on 2026-10-24 used `https://010.jjpcodes.com`: centre/night, coast/day, the whole municipality, Kralingen search and phone-sized pan/zoom. Both transit providers returned reports through the hosted Worker. A later public sample at 04:12 UTC contained fresh bus, tram, metro and train reports; it establishes all four modes in that sample, not continuous or complete service coverage (see `source-data/transit/live-layer.md`). Landscape export produced a 3840 × 2016 PNG; clipboard contained the PNG, exact public view link and `@jjpcodes`. Public captures and the downloaded image are retained in `work/visual-qa/published-*` on the SSD.

| View | Reproduce | What the capture establishes |
| --- | --- | --- |
| [Entire municipality](images/whole-municipality.jpg) | `lat=51.925&lon=4.265&span=30000&bearing=0&light=day` | City, harbour chain, Maasvlakte and Hoek share one continuous geographic model; surrounding municipalities remain quiet context. |
| [Wide city centre](images/wide-central.jpg) | `lat=51.925&lon=4.480&span=3400&bearing=35&light=day` | Continuous city fabric across both riverbanks, with every requested visible tree tile loaded. |
| [Centre at night](images/centre-night.jpg) | `lat=51.91050&lon=4.48750&span=900&bearing=35&light=night` | Unified stylised streets and buildings, inhabited windows, street illumination and visible bridge structure. Lighting is illustrated. |
| [Public bridge close-up](images/bridge-closeup-night.jpg) | `lat=51.91050&lon=4.48750&span=450&bearing=260&light=night` | Final public release: coherent stylised streets and native bridge geometry after the loading-order correction, with zero pending/refused tiles or errors. |
| [Coast](images/coast-day.jpg) | `lat=51.995&lon=4.125&span=2500&bearing=35&light=day` | Surveyed dune/path geometry, open sea, adjacent municipal context and source-backed ponds. |
| [Maasvlakte detail](images/port-day.jpg) | `lat=51.95609&lon=4.00802&span=550&bearing=35&light=day` | Measured cranes/container forms and continuous quay surfaces after missing-height repair. |
| [Port district](images/port-district.jpg) | `lat=51.955&lon=4.035&span=4200&bearing=35&light=day` | Final local reconstruction across terminal source boundaries; thin members remain incomplete. |
| [Reclaimed quay](images/reclaimed-quay.jpg) | `lat=51.89402&lon=4.36935&span=350&bearing=120&light=day` | Current BGT land and survey-based ground resolve the older shoreline beneath newer observed structures. |
| [Waalhaven](images/waalhaven-day.jpg) | `lat=51.87823&lon=4.40691&span=1000&bearing=35&light=day` | A different industrial district, source-aligned roads and dated laser-survey objects. These are not live ship positions. |
| [Metro cutaway](images/metro-cutaway.jpg) | `lat=51.91600&lon=4.48400&span=650&bearing=35&light=day`, then Transport → Metro cutaway | Source tunnel plan, illustrated cut depth and track details. Surface routes remain above ground. |
| [Eastern neighbourhoods](images/east-neighbourhood.jpg) | `lat=51.945&lon=4.546&span=1800&bearing=35&light=day` | Ordinary housing, waterways, trees and motorway infrastructure share the same style. All visible requested detail settled; no cache refusals. |
| [Hoogvliet](images/hoogvliet-day.jpg) | Search `Hoogvliet`, then Day | Public-site check of ordinary housing, canals, roads and green space in the southwest. |
| [Nesselande](images/nesselande-day.jpg) | Search `Nesselande Rotterdam`, then Day | Public-site check at the municipality's eastern edge, including lakefront housing and waterways. Detail took seconds to arrive. |
| [Mobile neighbourhood](images/mobile-delfshaven.jpg) | `lat=51.90720&lon=4.44900&span=700&bearing=35&light=day`, 390 × 844 viewport | Quiet controls and usable neighbourhood exploration at a phone-sized viewport. This is not a physical-phone performance measurement. |

The image-sharing path produced and downloaded landscape (3840 × 2016), square (2160 × 2160) and story (2160 × 3840) PNGs. All were opened and inspected. Copy image + caption placed both PNG bytes and the coordinate/lighting link with `@jjpcodes` on the browser clipboard. Full-resolution files and rejected diagnostic captures remain on the SSD in ignored `work/visual-qa/`; rejected images are not style targets.

Known interpretation limits: building colours and windows are illustrative; source geometry has acquisition dates and omissions; industrial scans retain some rough thin structures and transient objects. Metro depth is not surveyed. Current transport markers retain actual reported coordinates and timestamps, but upstream feed completeness is not guaranteed. Physical-device performance and public-hosting measurements must be distinguished from local browser checks.

## Terminal and shoreline release

Reviewed by GPT-6 Astra on 2026-10-24. Sites version 6 deployed successfully at 04:55 UTC from source `99a89513bed8d6aafea68aebb43a850c445680a1`. The public `010.jjpcodes.com` shore/day, terminal/night and whole-municipality/day views were inspected after deployment and settled with no pending/refused tiles or failed readiness; live transport and weather also returned. Captures are `work/visual-qa/published-v6-shore-day.jpg` , `published-v6-port-night.jpg` and `published-v6-municipality-day.jpg`. These checks do not establish complete source coverage or physical-device performance.

- **Municipality and coast:** `work/visual-qa/whole-city-day-context-candidate.jpg`, `coast-day-context-candidate.jpg`, `whole-municipality-subdued-context-night.jpg` and `west-city-integrated-night.jpg`. Surrounding land uses 0.72 linear reflectance in daylight and 0.45 at night. The city-to-port chain reads more clearly; the municipal detail boundary remains explicit. No zoom-dependent tint.
- **Port reconstruction:** `port-district-final-day.jpg`, `terminal-integrated-west-day.jpg` and `terminal-integrated-waalhaven-day.jpg`. The district settled with no pending/refused tiles or failed readiness. Closed storage forms and measured crane members remain distinguishable; thin members still become skeletal marks at district scale.
- **Reclaimed quay:** `terminal-reclaimed-ground-{day,night}.jpg`, at 51.89402, 4.36935, 350 m span. Newer dry-land geometry repairs an obsolete shoreline beneath observed objects. The bounded candidate uses local ground fits where DTM is absent. Its 878 triangles enter the vehicle surface query, but the captured view does not prove a vehicle crossing the patch. The final conversion inspected all 123 retained industrial source segments and produced two affected-shore tiles. Final captures `terminal-final-shore-day.jpg` and `second-shore-final-day.jpg` settled without pending/refused tiles or failed readiness.
- **Lighting:** `terminal-measured-masts-night.jpg` and `neighbourhood-after-measured-masts-night.jpg`. Supported measured tall fixtures produce broader illustrated pools; ordinary native pools remain consistent. This does not establish complete private-terminal fixture coverage or operational lighting state.

An isolated upper structural member at the small quay is supported by retained same-flight returns, but its lower connections are incomplete. The source check is retained in `work/source-quality/port-form-prototype/isolated-member-source-check.json`. It must not be described as a complete reconstructed crane.
