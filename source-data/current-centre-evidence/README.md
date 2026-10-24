# Current municipal centre-tower evidence

BAG **0599100000753300**, Van der Hoevenplein 9–243, Kop van Zuid. This probe
retains original current municipal source evidence for the same tower/podium
already present in the bounded legacy candidate. No artwork, facade filter,
scene change or publication is included.

## Source and terms

Current resource: `3adbe5af-d05c-475a-b34c-59e69ba8dadc`, leaf
`18/268679/55479.b3dm`, from https://www.3drotterdam.nl/datasource-data/ .
The 22,690,392-byte decoded B3DM contains this one BAG, with 23 textured
primitives. Original B3DM bytes are retained losslessly compressed under `raw/`,
along with selection indexes, request URLs, timestamps, response headers and
SHA256 sidecars. The neighbouring leaf inspected during selection is retained
separately and is not mistaken for the requested tower.

The exact resource is listed as **Gebouwen LOD2 texture - Actueel** in the
municipal application configuration. The linked resource-specific catalogue
states **Creative Commons Attribution 4.0**, maintained by Gemeente Rotterdam:
https://hub.clearly.app/datasets/65ef2475fe2ac522c6ac7b63/information . The rendered
catalogue and application-link evidence is retained separately at
`../current-building-evidence/catalog-evidence.json`. Attribution:
**Gemeente Rotterdam — 3D Rotterdam**, https://creativecommons.org/licenses/by/4.0/ .
Do not reuse an older public-domain statement for this current resource.

The source attribute `creationDate` is **2024-10-28**. It is a model record,
**not an established photographic capture date**. HTTP Last-Modified is also
not flight-date evidence. No claim of 2026 photography is made.

## Observed differences

`comparison.jpg` shows original legacy/current source materials on original
geometry from two opposite oblique directions and a roof-biased direction.
Each building is independently fitted to the same image frame; these CPU
material probes have no added lighting and are not browser scene screenshots.
Raw photos' baked sunlight and shadows remain visible.

- Geometry changes: **1,226 → 1,394 triangles**, with **3 → 23 primitives**;
  legacy has two textured primitives, current has 23. Original world-space
  expanded triangles are not equal. Maximum numeric source height changes
  from 161.898 to 159.584; current source `measuredHeight` is 156.21 m above its
  approximately 3.377 numeric base. Horizontal bounds also change slightly.
- This is therefore **not only a texture substitution**. Original mesh and
  original UVs must remain paired. Vertex-distance statistics in the report
  include different tessellation; they are not surveyed surface-error estimates.
- The current source contains twenty-two 1024² atlases plus one 256² atlas;
  the legacy tile images used here are 2048² and 2048×1024. Larger source image
  storage is genuine retained evidence, not fabricated super-resolution.
- Shadowed facade details and tower-top roof objects are more legible. The
  podium roofs show materially different green/gravel surface evidence from
  the old atlas. Strong photo highlights remain on the sunny side. These are
  useful inputs for coherent whole-building illustration, not finished art.

## Reproduce and inspect

```sh
python scripts/inspect-current-centre.py           # offline retained sources
python scripts/inspect-current-centre.py --acquire # explicit bounded acquisition
```

Dependencies: NumPy, Pillow, SciPy and pyproj; reuses the current building
extraction helper. The script verifies retained source hashes and exact expanded
POSITION/NORMAL/UV attributes, node transforms and embedded image bytes for
all 1,394 extracted triangles. The original current GLB is regenerated at
`work/current-centre-evidence/current-original.glb`; its 22 MB duplicate is not
also committed because the original B3DM is retained. RTC placement is recorded
in `comparison.json` and the B3DM feature table. Materials, UVs and transforms
must not be discarded when passing this source to an artworker.

`comparison.json` records source attributes, geometry statistics, world bounds,
atlas dimensions and verification. Individual PNG probes remain available.
For render-only legacy primitives lacking texture, a constant-colour 1×1 texel
represents their original material factor; this does not modify saved source
geometry or introduce new surface features.
