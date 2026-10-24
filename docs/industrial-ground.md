# Large yards and crane tracks

Written by AI, gpt-6-astra, 2026-10-24.

The [official BGT API](https://api.pdok.nl/kadaster/bgt/ogc/v1/) supplies measured ground polygons and crane rails throughout the municipality. This adds the fixed layout of terminal and industrial sites without inventing container inventories, crane poses or traffic. The API declares [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/); credit Kadaster / PDOK and the BGT source holders.

Sources are `onbegroeidterreindeel` and `spoor`. BGT includes historical versions, so acquisition supplies an explicit `datetime` interval-selection value, retained with the exact request URLs. Records must have status `bestaand`, no termination date, and relative height level zero. Relative height level is not elevation in metres. Registration dates describe record maintenance, not a fresh survey or live observation.

| Display class | Source condition | Meaning |
|---|---|---|
| `open-paving` | `fysiek_voorkomen=open verharding` | Paving made of separate elements; not proof of a particular brick or slab material |
| `closed-paving` | `fysiek_voorkomen=gesloten verharding` | Continuous paving; not proof of asphalt rather than concrete |
| `yard` | `fysiek_voorkomen=erf` | Recorded yard extent; surface composition is unspecified |
| `crane-rail` | `spoor.plus_functie=(haven)kraan` | Surveyed crane track centreline; does not locate a crane on that track |

Ground polygons must cover at least 2,000 m² after clipping to the exact Rotterdam boundary. This targets large sites missing from the neighbourhood-scale street layer; close-view municipal BGT continues to supply smaller details. All qualifying crane tracks are retained. Source holes remain holes. Display geometry is simplified by one metre and rounded to approximately decimetre coordinate precision.

The acquired edition contains 2,825 yards, 484 areas of open paving, 168 areas of closed paving and 940 crane-track features. Together the ground polygons cover 49.76 km² and the track lines total 271.54 km. The API returned 321,904 ground and 11,762 track records for the bounding rectangle before exact municipal selection. Selected registration dates range from 2008 to October 2026; a current registry record is not evidence of a recent survey.

`source-data/industrial-ground.geojson.gz` retains the original selected source geometries, complete source attributes, collection names, request URLs, first/last API response timestamps and licence. Gzip uses a zero timestamp. Complete responses, including the unselected small objects, remain in `work/data-cache/`. The source file can rebuild the display without the network:

```sh
python3 scripts/fetch-industrial-ground.py --rebuild
node scripts/build-industrial-ground.mjs
```

Python requires the existing Nix Shapely and pyproj environment. Node uses the already-vendored Three.js library. To acquire a new edition instead, run `fetch-industrial-ground.py --snapshot <UTC timestamp>` without `--rebuild`; a different timestamp produces separate cached requests.

The intermediate GeoJSON is kept in `work/source-quality/port/industrial-ground.geojson`. Browser assets are standard 3D Tiles 1.1 and glTF 2.0 in `public/data/industrial-ground/`. One-kilometre buckets contain complete features, and tile bounds include their full extent. Meshes expose the four display classes through `extras.surfaceKind`. Source hashes and rendering choices are recorded in the generated manifest.

The edition produces 329 tiles, 153,990 triangles and 3.06 MB of GLB data. The original source gzip is 31.01 MB and stays outside the browser assets. All 4,417 selected geometries are valid and have distinct source IDs. The generated mesh areas agree with projected source areas within 0.012%; feature holes survive triangulation.

Polygons use the display elevation −0.65 m; crane-track ribbons use −0.62 m and an illustrative width of 0.35 m. These offsets place the layer above the overview and below roads; they are not surveyed heights or measured rail widths. Each GLB stores coordinates relative to its tile centre. The tileset root converts local east/north/up into WGS84 Earth-centred coordinates.

Rotterdam's published 3D catalogue does not list a dedicated port-crane mesh layer. BGT proves fixed footprints and tracks, not the contents of a yard. Container stacks and moving crane positions remain a source gap.
