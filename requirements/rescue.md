# Rescue brief

Written by AI on 2026-10-24 by model GPT-6, from Josh's correction.

The current published map is rejected on visual quality. Existing screenshots, successful builds and past agent reviews do not establish acceptance. Read this with [the original steering](steering.md) and [the product contract](README.md).

## Corrections

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
