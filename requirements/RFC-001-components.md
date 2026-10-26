# RFC-001: 010 components and contracts

Written by AI on 2026-10-26 by Claude Fable 5.1, at Josh's request ("decompose this into proper components RFC style"). Status: proposed. Josh's words in `steering.md` outrank this document.

## Goal

A living pixel-art miniature of the whole gemeente Rotterdam that is true to the city in every object, better than tiny.london and isometric.nyc on truth, depth, light, craft, life and rotation, loads in under a second on a phone, and can be redone stage by stage by a better model later. The 3D city scene underneath it is a reusable asset in its own right.

## Principles

- Evidence and appearance are separate. Facts come from data and photos; appearance comes from model-made assets composed from those facts; style comes from one renderer.
- Every component has one input contract and one output contract on disk, with provenance. A better model reruns one component without touching the others.
- Nothing is invented silently. Where evidence is missing, the output is marked interpreted and is replaceable.
- One renderer decides the look everywhere, so the city has no seams and no style drift.
- The standard is per object class against that class's evidence, applied to the whole city, not to a demo tile.

## Components

Each component: purpose, contract, what is fixed and what is open, owner, how it is verified. Paths are under `/Volumes/Josh Extreme Pro USB4 4TB/010/` unless they are code (git, branch `v2`).

### C1 Sources

Purpose: every external dataset as fetched, forever. Contract: `sources/<dataset>/<date>/` with raw bytes and `manifest.json` (URL, SHA-256, size, fetch time, licence, credit). Fixed: layout and manifest. Open: nothing. Owner: Sol. Verified by: manifest hashes match files; licence file present. Datasets: Rotterdam 3D Tiles (buildings 2018 textured and LOD2, bridges, trees, BGT ground, lamps, terrain), PDOK 2026 ortho, Kadaster GM0599, BAG, BGT objects, NWB roads and cycle paths, BRT rail, OVapi GTFS, NDOV and NS live, Open-Meteo, Wikimedia Commons vehicle photos.

### C2 City scene

Purpose: the one model of the city that everything else reads. Contract: `scene/v1/` as documented in `pipeline/README.md`: RD New and NAP, 250 m tiles, `buildings.glb` with BAG ids, `ground.glb` with classes, `ortho.jpg` and `classes.png` at 10 cm, `objects.json` (trees with species, height, crown; lamps; furniture), `manifest.json`. Camera: one affine transform from RD x, y, NAP z to picture pixels per bearing, published in the manifest. Fixed: coordinate system, tile grid, file contract, camera transform. Open: nothing structural; content grows city-wide. Owner: Sol builds, Opus owns the contract. Verified by: tile counts against BAG; coverage map of the whole gemeente; the 2026 ortho under every tile.

Build the whole gemeente here early. This component does not depend on any look decision and every later component reads it.

### C3 Perception

Purpose: facts about each object from its evidence. Contract: `facts/v1/buildings/<bag_id>.json`: per wall plane material class, mean colour, window rows and openings with pixel and metre positions, doors and shop fronts, roof type and equipment, occlusion mask and verified fraction; `facts/v1/trees`, `lamps`, `furniture` from registers; each file records model, date, prompt hash, reference hashes. Fixed: the schema. Open: the model and batching (many walls per call), and the share of walls that need measurement at all (street-facing with photo evidence first). Owner: Sol runs; Opus owns the schema. Verified by: code re-measures the photo at the reported positions (edge agreement, colour agreement) and rejects mismatches; a sample is checked by eye against the photo every round.

### C4 Asset library

Purpose: the appearance of every object class, made by models, composed from C3 facts. Contract: `assets/v1/<class>/<id>/` with the asset (textures, meshes or sprite sheets), `provenance.json` (model, date, evidence, verified fraction, interpreted regions), and a `reference.png` where photos exist. Classes: building elevations and roofs (tier 2: composed from a model-made parts library of swatches, windows, doors, cornices, gables, roof materials, driven by facts; tier 1: fully generated elevation for distinctive façades); vehicles (RET Citadis, RET metro, NS Sprinter and Intercity, RET bus, Dutch cars, cyclists; modelled from datasheet dimensions and at least eight current photos); trees per species; lamps per municipal design; street furniture; ground materials per BGT class. Fixed: the contract and the rule that every asset is verified against its evidence or marked interpreted. Open: the tier 1 versus tier 2 share for buildings; the parts library's contents. Owner: Sol produces; Opus judges. Verified by: per-class checks against the photo or datasheet; a vehicle rendered at a photo's angle beside the photo; a cold reviewer names the vehicle; per-building cost measured.

### C5 Renderer

Purpose: the one place the look is decided. Contract: input C2 plus C4; output per bearing and per level `pyramids/<version>/b<bearing>/<level>/<col>_<row>.webp` colour plus aligned depth, normal and material buffers, at native pixel scale per level (0.075 m per pixel in built-up tiles, coarser elsewhere), four bearings. The recipe: sun by time with cast shadows, side-versus-roof shading, one-pixel outlines from depth and normal discontinuities, measured palette per surface class, dither, night from real light sources (register lamps, window masks by BAG use and time, lit landmarks). Fixed: output contract and that style lives only here. Open: the recipe values, decided on the POC tile against tiny.london as the floor. Owner: Opus. Verified by: the candidate sheet (aerial, 7.5 cm, overview, night, second bearing, tiny.london) and the seam metric.

### C6 Delivery

Purpose: the picture on a phone in under a second. Contract: immutable version folders; PMTiles archives per bearing and layer served by the Worker with range requests when Sites' 256 MiB or file limits bind; service worker caching HTML and tiles per deploy; viewer on OpenSeadragon with a WebGL overlay; inlined low-resolution first view; search via PDOK Locatieserver; share image with view link and @jjpcodes; og:image and og:video; compare mode. Fixed: targets of 100 ms warm and network floor plus 100 ms cold, measured with Playwright throttling. Open: PMTiles versus files, decided by the Sites upload test. Owner: Opus (UI), Sol (packing and speed script). Verified by: the speed script's recording and a phone-size walkthrough.

### C7 Living layers

Purpose: the city moving and lit in real time. Contract: WebGL overlay reading C2's camera transform, C4 sprites and C5 depth buffers; NDOV GTFS-RT and NS positions snapped to shapes with observation age; simulated cars on the NWB directed graph; cyclists on the NWB cycle network; weather from Open-Meteo; day, dusk and night by sun time; metro cutaway along BRT tunnel corridors. Fixed: everything uses the same camera and depth, so vehicles sit on their decks and hide behind buildings. Open: nothing structural. Owner: Sol (feeds, graphs), Opus (drawing). Verified by: a real tram watched through a junction and under a bridge; a cyclist on a red path; the cutaway with a live train.

### C8 Verification

Purpose: the review system, built once, used every round. Contract: per-class checks from C3 and C4; the candidate sheet layout; the seam metric; the speed script; compare mode in the product; a cold reviewer given only `steering.md`, the URL and the sheet; a scorecard per round over truth, depth, light, craft, life, rotation, speed, coverage, night, sharing. Fixed: a sheet is rejected if any class on it fails its check; "reads as" is not a pass. Owner: Opus runs it; Fable and Josh read it. Verified by: Josh recognising his streets on his phone.

### C9 Operations

Contract: code and manifests in git on `v2`, data on the SSD, `STATUS.md` under one page, free resources only, no Gemini, no new accounts, licences credited on the site, no personal data. Compute budgets stated per component (seconds per building for C3 and C4, seconds per km² per bearing for C5) and the projected whole-city totals kept current in `STATUS.md`.

## Dependencies and build order

```
C1 ─▶ C2 ─▶ C3 ─▶ C4 ─▶ C5 ─▶ C6
            │          ▲     │
            └──────────┘     ▼
                 C7 (reads C2 camera, C4 sprites, C5 depth)
C8 across all; C9 underneath all
```

1. Invariants first and city-wide: C1 complete, C2 for the whole gemeente, C8 tooling (per-class checks, sheet, speed script). None of this is thrown away by any later look decision.
2. The open questions, decided on one 250 m Delfshaven tile: C3 batching and coverage, C4 tier split and parts library, C5 recipe. The evidence is the candidate sheet with tiny.london as the floor.
3. Roll out: C5 and C6 for Delfshaven, then the centre, then the gemeente, with C7 live from the first published neighbourhood.

Nothing is published until step 2 passes.

## Open questions

| Question | Decided by | When |
|---|---|---|
| Share of buildings needing tier 1 generation versus tier 2 composition | Quality and cost on the POC tile | Step 2 |
| Renderer recipe values (shadow depth, outline rules, palette) | Candidate sheets against tiny.london and the aerial | Step 2 |
| PMTiles versus files on Sites | Upload test with a few thousand tiles | Step 1 |
| Compute for the whole gemeente | Measured per-building and per-km² costs | End of step 2, reported to Josh |
