# Pipeline

Written by AI on 2026-10-25 by model Claude Opus 5.5.

Rotterdam in miniature is built in stages. Each stage reads the previous stage's files and writes its own, so a better model or tool can redo one stage without touching the others.

```
sources  ->  scene  ->  render target  ->  site
raw bytes    one 3D     T1 live 3D, T2 pixel
as fetched   model of   pyramid, T3 painted
             the city   pyramid
```

Code lives here in git. Data lives on the SSD, never in git:

```
/Volumes/Josh Extreme Pro USB4 4TB/010/
  sources/<dataset>/<YYYY-MM-DD>/   raw responses exactly as fetched, plus manifest.json
  scene/v1/                         the scene (contract below)
  renders/                          offline renders and comparison images
  pyramids/                         image pyramids for T2 and T3
  builds/                           site builds ready to publish
```

## Sources

Each `sources/<dataset>/<date>/manifest.json` lists every file with its URL, SHA-256, byte size, fetch time, and the dataset's licence and credit line. Raw files keep their original bytes. Endpoints and licences are in [docs/data-sources.md](../docs/data-sources.md).

## Scene contract (v1)

The scene is one model of the city in the Dutch national grid (RD New, EPSG:28992) with heights in metres above NAP (EPSG:7415 for the compound system). It is not in Earth-centred coordinates: every Dutch dataset already lives in RD/NAP, and a flat camera over the whole gemeente stays flat.

**Grid.** Square tiles of 250 m aligned to multiples of 250 in RD. A tile is named by its south-west corner: `x90250_y436000` covers RD x 90250 to 90500 and y 436000 to 436250.

**Local axes inside a tile's glTF files** (glTF is Y-up, right-handed):

- glTF X = RD x − tile x-min (east)
- glTF Y = NAP height
- glTF Z = −(RD y − tile y-min) (so north is −Z)

All files of a tile share that origin. Objects in JSON use absolute RD x, y and NAP z.

**Files per tile**, in `scene/v1/tiles/<tile>/`:

| File | Content |
|---|---|
| `buildings.glb` | Every building whose footprint centroid falls in the tile, whole (not clipped), and the bridges likewise. Photo-textured 2018 geometry where it still matches the newer model, otherwise the newer untextured LOD2 geometry. One primitive per source material. Vertex attribute `_FEATURE_ID_0` indexes the feature table in the glTF root `extras.features`: `{bag_id, kind: "building" or "bridge", source: "textured2018" or "lod2", height_m, year, use}`. |
| `ground.glb` | The ground surface from the municipal BGT 3D tileset, with real heights, quay walls and vertical faces kept. Vertex attribute `_CLASS` holds the surface class (legend below). |
| `ortho.jpg` | 2026 aerial photo for exactly the tile, north up, 2500 × 2500 (10 cm per pixel), requested directly in RD. |
| `classes.png` | RGBA, 2500 × 2500, same footprint as `ortho.jpg`. R = surface class. G = line features as bits: 1 tram rail, 2 train or metro rail, 4 road marking, 8 kerb. B and A reserved (0 and 255). |
| `objects.json` | `trees: [{x, y, z, height_m, crown_m}]`, `lamps: [{x, y, z, height_m}]`, absolute RD/NAP. |

`scene/v1/manifest.json` holds the area, the grid, the tile list, the class legend, the source datasets with their manifest hashes, the git commit of the code that built it, and the per-tile counts (buildings by source, triangles, texture bytes).

**Surface classes** (R channel of `classes.png`, `_CLASS` in `ground.glb`):

| Value | Class | Value | Class |
|---|---|---|---|
| 0 | unknown | 9 | unpaved, sand, bare |
| 1 | carriageway | 10 | paved yard or square |
| 2 | cycle path | 11 | building footprint |
| 3 | footpath, pavement | 12 | bridge deck |
| 4 | parking | 13 | quay wall, civil structure |
| 5 | tram track bed | 14 | train or metro track bed |
| 6 | grass, planted verge | 15 | traffic island, crossing |
| 7 | shrubs, hedges | 16 | rail yard, ballast |
| 8 | water | | |

Anything that exists as data is drawn from data. Rails, road markings, kerbs, cycle paths, water edges, trees and lamps come from the sources above, never from an image model.
