# Bound artwork context candidate

The corrected row V5, Schans 66–80 apartment and OST_14427971 tank handoffs were
inspected in their opposing source/painted previews before integration. Their
remaining art limits are retained in each supplied README: rear unknown walls,
minor source/model joins, roof detail and pale tank material need actual city
review. The neighbourhood mode currently contains **only the row and apartment**.
The earlier `illustrated-row` and current municipal source assets remain intact.

Prepare from the three downloaded handoff ZIPs (each contains `assets/`):

```sh
unzip 010-corrected-row-v5-runtime.zip -d work/bound-row
unzip 010-apartment-bound-runtime.zip -d work/bound-apartment
unzip 010-tank-bound-runtime.zip -d work/bound-tank
python scripts/prepare-bound-artwork.py work/bound-row/assets --output public/data/illustrated-neighbourhood/row --retained source-data/bound-artwork/row-v5 --collection public/data/illustrated-neighbourhood
python scripts/prepare-bound-artwork.py work/bound-apartment/assets --output public/data/illustrated-neighbourhood/apartment --retained source-data/bound-artwork/apartment --collection public/data/illustrated-neighbourhood
python scripts/prepare-bound-artwork.py work/bound-tank/assets --output public/data/illustrated-tank --retained source-data/bound-artwork/tank
```

The same compiler accepts further bound handoffs; `--collection` appends their
external tileset and rejects overlapping exact identities. BAG uses unprefixed
16-digit `bagId`; OST keeps its full `featureId`, never masquerading as BAG.
Source fallback reconciliation remains owned by the runtime.

Original root matrices, positions, normals, UVs and batch attributes remain exact;
only triangle index groups/attribute storage are compacted. RTC is removed from
the GLB extension and applied once in its child tile transform. The compiler
reuses `uv_islands`/`pack_rectangles` from the existing appearance preparation to
copy native texels without resampling. `KHR_texture_transform` maps unchanged
source UVs into the packed external atlas. Two pixels of edge padding include
source-edge extrusion, preventing one-pixel materials from sampling an adjacent
packed patch. Floating texture-coordinate arithmetic still has ordinary texel
boundary precision limits; actual crisp sampling needs GPU review.

Only referenced images are read and retained; `.writing` intermediates are
excluded. Row emission reuses native lossless black-border crops, factor one,
the existing `emissionCropGuard`, and the shared scene night uniform (zero by day).
Apartment and tank have no emission maps or invented night window grid.

Final decoded RGBA+mip estimates: row 95.1 MB, apartment 15.1 MB, tank 45.8 MB.
These are context assets, not proven city-scale residency/performance. There are
315/47/109 material draws respectively; future tile-level consolidation may be
needed. Retained handoff geometry/images and generated public binaries are
reproducible from the archived handoffs, not duplicated in this source commit.

Checks run:

```sh
python tests/bound-artwork.py
node tests/bound-artwork-runtime.mjs
```

These verify exact triangle attributes/identities/RTC, native bilinear texel
correspondence, actual vendored GLTFLoader HTTP requests and PNG decoding,
texture transforms and the day/night emission hook. They do not establish
art quality, GPU sampling, placement appearance or city-context acceptance.
