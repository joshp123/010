# 010 requirements

Written by AI on 2026-10-24 by model GPT-6 Astra, from Josh's steering.

Build a beautiful, geographically faithful, living miniature of the entire gemeente Rotterdam that people can explore and share. The map is the product. The current coarse extrusion prototype does not meet the requested visual standard.

## Product contract

- Cover the whole municipality, including Hoek van Holland, Maasvlakte and the port. Expansion to the Netherlands is a possible later direction.
- Start from measured geography, buildings and imagery. Keep this model separate from the pixel/isometric presentation so visual fidelity can improve incrementally and support a more realistic view later.
- Aim for recognisable detail approaching satellite/Street View usefulness. Higher output resolution alone does not satisfy this: roof shapes, facades, streets, shoreline, infrastructure and ordinary neighbourhoods must be recognisable.
- Make night look inhabited: lit windows, streets, landmarks and plausible water reflections. A uniformly dark city is unacceptable. Current weather should affect the scene.
- Provide effortless exploration and shareable views. Copy/download high-resolution images suitable for Twitter and Instagram, with the view link and @jjpcodes credit. Use lessons from Nice Weather and monemap.
- Include accurate public transport: real-time trams, trains, buses and metros, alongside clearly simulated general traffic. Never present timetable interpolation as an observed position. Include a metro cutaway; source route geometry and underground depth where available, and distinguish measured geometry from illustration.
- Investigate marine traffic as an optional extension. Prefer actual, licensed vessel reports; do not silently turn simulated boats into a live-data claim.

## Constraints and delivery

- Free resources only. No paid APIs, imagery generation, subscriptions or domain purchase.
- Store work on the SSD, use a public Git repository and MIT license for code. Preserve source-data licenses and attribution separately.
- Publish through ChatGPT Sites at **010.jjpcodes.com**. The earlier .net request was explicitly corrected to .com.
- No personal data in the project or repository beyond Josh's name and public handle. Reuse lessons from private house work, never its data. Eventual private house-to-city zoom is a design direction, not permission to publish house material.
- Preserve restrained UI and simple implementation. No unnecessary churn, frameworks or feature bloat.
- Continue autonomously until the result meets the actual quality bar. Use `better` and `raise-the-ambition` to deepen the work, not expand process.
- Main browser testing belongs in the agent's in-app browser. Use Chrome only if necessary. Inspect many actual screenshots at city, neighbourhood and close-up scales, on desktop and small screens, day and night.
- Model coordination may use Astra; bounded implementation may use Sol 6.1 low/medium when efficient. This must not reduce delivered quality.

## Quality and performance order

First make it look good, then make it fast. The user suggested roughly 100 ms for loading and interaction, with current best practice and no loss of visual quality. Measure separately: first useful map, time to sharp detail, input-to-frame response, frame pacing, cold/warm cache, viewport and device class. A quick empty UI is not a fast map, and a warm desktop result is not proof for every device or connection.

Compare real rendered locations with independent source imagery and reference experiences. Assess the finished public site through the human path: load, explore, zoom, switch lighting/weather, find a place and share the actual image. Mechanical checks support this; they do not replace it.

## Scope sequencing

The current priority is the rejected visual fidelity gap. Source investigations for transit, underground infrastructure and optional marine traffic can proceed independently. They must not justify shipping the coarse prototype or interrupt the source-to-render fidelity work. Keep unavailable data and unfinished features explicit; do not claim this file means they are implemented.

The [steering record](steering.md) preserves the user's words, with private conversation references removed. [Transport data](transport-data.md) records source feasibility separately from requirements.
