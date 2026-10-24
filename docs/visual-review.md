# Actual map views

Written by AI on 2026-10-24 by model GPT-6 Astra.

These captures come from the running map in the Codex in-app browser. The requirements and original steering remain the quality target; these images make the current interpretation inspectable by the next person or model.

Public release verification on 2026-10-24 used `https://010.jjpcodes.com`: centre/night, coast/day, the whole municipality, Kralingen search and phone-sized pan/zoom. Both transit providers returned reports through the hosted Worker; current observations were mostly late-night buses, so this does not prove every mode's coverage. Landscape export produced a 3840 × 2016 PNG; clipboard contained the PNG, exact public view link and `@jjpcodes`. Public captures and the downloaded image are retained in `work/visual-qa/published-*` on the SSD.

| View | Reproduce | What the capture establishes |
| --- | --- | --- |
| [Entire municipality](images/whole-municipality.jpg) | `lat=51.925&lon=4.265&span=30000&bearing=0&light=day` | City, harbour chain, Maasvlakte and Hoek share one continuous geographic model; surrounding municipalities remain quiet context. |
| [Wide city centre](images/wide-central.jpg) | `lat=51.925&lon=4.480&span=3400&bearing=35&light=day` | Continuous city fabric across both riverbanks, with every requested visible tree tile loaded. |
| [Centre at night](images/centre-night.jpg) | `lat=51.91050&lon=4.48750&span=900&bearing=35&light=night` | Unified stylised streets and buildings, inhabited windows, street illumination and visible bridge structure. Lighting is illustrated. |
| [Public bridge close-up](images/bridge-closeup-night.jpg) | `lat=51.91050&lon=4.48750&span=450&bearing=260&light=night` | Final public release: coherent stylised streets and native bridge geometry after the loading-order correction, with zero pending/refused tiles or errors. |
| [Coast](images/coast-day.jpg) | `lat=51.995&lon=4.125&span=2500&bearing=35&light=day` | Surveyed dune/path geometry, open sea, adjacent municipal context and source-backed ponds. |
| [Maasvlakte detail](images/port-day.jpg) | `lat=51.95609&lon=4.00802&span=550&bearing=35&light=day` | Measured cranes/container forms and continuous quay surfaces after missing-height repair. |
| [Waalhaven](images/waalhaven-day.jpg) | `lat=51.87823&lon=4.40691&span=1000&bearing=35&light=day` | A different industrial district, source-aligned roads and dated laser-survey objects. These are not live ship positions. |
| [Metro cutaway](images/metro-cutaway.jpg) | `lat=51.91600&lon=4.48400&span=650&bearing=35&light=day`, then Transport → Metro cutaway | Source tunnel plan, illustrated cut depth and track details. Surface routes remain above ground. |
| [Eastern neighbourhoods](images/east-neighbourhood.jpg) | `lat=51.945&lon=4.546&span=1800&bearing=35&light=day` | Ordinary housing, waterways, trees and motorway infrastructure share the same style. All visible requested detail settled; no cache refusals. |
| [Hoogvliet](images/hoogvliet-day.jpg) | Search `Hoogvliet`, then Day | Public-site check of ordinary housing, canals, roads and green space in the southwest. |
| [Nesselande](images/nesselande-day.jpg) | Search `Nesselande Rotterdam`, then Day | Public-site check at the municipality's eastern edge, including lakefront housing and waterways. Detail took seconds to arrive. |
| [Mobile neighbourhood](images/mobile-delfshaven.jpg) | `lat=51.90720&lon=4.44900&span=700&bearing=35&light=day`, 390 × 844 viewport | Quiet controls and usable neighbourhood exploration at a phone-sized viewport. This is not a physical-phone performance measurement. |

The image-sharing path produced and downloaded landscape (3840 × 2016), square (2160 × 2160) and story (2160 × 3840) PNGs. All were opened and inspected. Copy image + caption placed both PNG bytes and the coordinate/lighting link with `@jjpcodes` on the browser clipboard. Full-resolution files and rejected diagnostic captures remain on the SSD in ignored `work/visual-qa/`; rejected images are not style targets.

Known interpretation limits: building colours and windows are illustrative; source geometry has acquisition dates and omissions; industrial scans retain some rough thin structures and transient objects. Metro depth is not surveyed. Current transport markers retain actual reported coordinates and timestamps, but upstream feed completeness is not guaranteed. Physical-device performance and public-hosting measurements must be distinguished from local browser checks.
