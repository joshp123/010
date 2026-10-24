# Rescue brief

Written by AI on 2026-10-24 by model GPT-6, from Josh's correction.

The current published map is rejected on visual quality. Existing screenshots, successful builds and past agent reviews do not establish acceptance. Read this with [the original steering](steering.md) and [the product contract](README.md).

Josh's further steering: **“the work and approach must be deep and holistic btw not tiny patches”.** Evaluate and improve the full source-to-image approach and the whole experience. Small candidates may validate an approach before scaling; isolated fixes or a handful of polished buildings do not satisfy the rescue.

Josh also asked: **“compare with how the prior art versions did it btw?”** Compare the actual production methods in [NYC's writeup](https://cannoneyed.com/projects/isometric-nyc) and [London's writeup](https://tiny.london/how/), not just their screenshots. Both use geographically aligned textured renders as input to offline model-generated illustration, then serve image pyramids. NYC uses fine-tuning and neighbour-aware infill; London uses fine-tuning and overlapping shared-latent sampling. Assess whether this architecture is the right foundation here, including source fidelity, consistent adjoining areas, free-resource feasibility, and geographic alignment of transport, night and metro presentation. Do not assume inherited live-3D materials can achieve the same result.

Latest direct steering: **“i like our 3d idea but it should be combined with the model stuff you found to ensure we have something that's at the pareto optimal principle of image quality ; realism; and blazing fast performance (image quality most important; we shouldn't \"guess\" or \"invent\" parts of the city they should all look basically perfect jnkeeping with our style as you zoom in”**. Retain 3D as the foundation and combine it with source-grounded model interpretation. The prior-art comparison informs that hybrid; it does not authorize replacing the product with a static image. Image quality has priority. Preserve real architecture, facade/roof identity and detail consistently across zoom and viewpoints. Acquire missing evidence instead of inventing architectural detail. Optimise speed after the appearance is worthy of the brief.

Josh also corrected the manager: **“why did you stop your turn btw. you need to use the mechanisms in the tweet to keep working until the entire project is complete.”** Keep workers moving, actively inspect and iterate on their actual results, and retain scheduled manager follow-up until the whole project is complete. A plan, pilot or idle interval is not completion.

## Corrections

Further direct steering: **“not sure what happened with car and bicyclist routes but we should be making use of eg vector maps of all the routes to ensure that they are locgicsl routes for cars and bikes (usually separate in rotterdam)”**. Use appropriate source-backed connected networks for cars and bikes, including valid directions, junction transitions and crossings. Separate cycleways alone do not establish complete bicycle journeys; real road lines alone do not establish legal car turns. Review actual movement through representative streets, bridges and junctions.

Josh explicitly renewed **better** and **raise-the-ambition**: keep thinking holistically about the whole body of work. Deeper source interpretation and a coherent successful city experience are the mission; isolated patches and defensible intermediate artifacts do not close it.

- Buildings have strange colours and far too little detail. The result must resemble a miniature pixel-art Rotterdam, with recognisable architecture and coherent materials throughout the municipality. A coarse 3D map with generic windows does not meet the references.
- Simulated cars move implausibly. Inspect actual motion through junctions, bends, two-way streets and bridges; static screenshots and vehicle counts do not prove this works.
- Cyclists are missing. They belong in the living Dutch city, using appropriate routes and credible motion.
- Phone controls are noisy and hide the map. Make exploration the dominant experience, with secondary controls revealed when needed. Test the real rendered page and interactions at phone sizes.
- The metro cutaway looks poor and appears to lack metros. Inspect trains in the cutaway and reconcile the real feed, underground visibility and physical route geometry. An empty trench is not a useful cutaway. Preserve the distinction between observations and illustrated/estimated movement.
- These are examples of failures, not an exhaustive issue list. Independently inspect the whole experience against the user's original words and live references.

## Working method

Use a manager with separate implementation threads and a scheduled progress check. Write down every steer and reconcile it against the overall goal before dispatching work, following [Eric Provencher's pattern](https://x.com/pvncher/status/2113794328690647521).

The manager owns product judgement and reviews the actual map. Implementation workers own concrete, reviewable changes. Keep raw source data and replaceable visual interpretation. Choose substantive quality improvements; do not settle for repeated shader adjustments, performance optimisation or isolated landmark detail while the whole-city art direction remains wrong.

Make it look good first, then make it fast. The free-resource constraint, public MIT code, source licensing, no personal data, weather, proper night lighting, real transit, social exports and entire-municipality scope remain binding. Marine traffic remains optional.

## Review

Compare the actual map with [Tiny London](https://tiny.london/) and [Isometric NYC](https://isometric.nyc/), plus independent real-city evidence. Inspect ordinary streets as carefully as landmarks, across close, neighbourhood and city scales, day and night. Inspect car and cyclist motion over time. Test finding, navigating and sharing a place on desktop and phone. Export resolution, geometry counts and a passing build support the work but cannot substitute for these checks.

Continue until the map meets this brief. Report material limits honestly instead of turning them into acceptance.
