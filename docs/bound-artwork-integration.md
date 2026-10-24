# Adjoining neighbourhood review candidate

The neighbourhood collection now replaces its eight-building row with the complete
32-building architectural handoff for municipal tile `18/268620/55473`. The Schans
apartment remains alongside it. This is one replacement, not overlapping row and
block layers. The earlier `illustrated-row` and `appearance=current` views remain
available independently.

From the downloaded `010-adjoining-32-building-runtime.zip`:

```sh
unzip 010-adjoining-32-building-runtime.zip -d work/bound-adjoining
python3 scripts/prepare-bound-artwork.py work/bound-adjoining/assets --output public/data/illustrated-neighbourhood/adjoining --retained source-data/bound-artwork/adjoining-32 --collection public/data/illustrated-neighbourhood --replaces row/tileset.json
```

This command retains the apartment entry already prepared below. Replacement
requires the new exact identity set to contain every removed row identity.
The block preserves source positions, UVs, BAGs and the root transform, with RTC
applied once. It keeps only source-observed glazing from the original row;
newly illustrated buildings receive no invented emission. Original external
atlases and annotations remain in the retained handoff.

Review `?lat=51.90955&lon=4.44711&span=160&bearing=125&light=day&appearance=illustrated-neighbourhood&ground=illustrated`, then rotate to 305 and switch to night. The richer street rows/courts are a substantial adjoining-area candidate, not accepted art: hard pale edges, some photographic recesses, uncertain blank wall treatment and roof microdetails still need actual scene judgment. Northern adjoining tile `18/268620/55472` remains separate work.

## Earlier assets and preparation


The corrected row V5, Schans 66–80 apartment and OST_14427971 tank handoffs were
inspected in their opposing source/painted previews before integration. Their
remaining art limits are retained in each supplied README: rear unknown walls,
minor source/model joins, roof detail and pale tank material need actual city
review. The earlier collection contained only the row and apartment.
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

The actual tile-cache estimator is overridden for appearance layers in app code.
It counts geometry attributes and one upload per shared Texture.Source/sampler
key; UV-transform clones do not allocate another image. The vendor object-based
estimator previously evicted the city despite shared atlas storage. This changes
admission accounting, not atlas resolution or the cache limit. Actual complete
city and port rendering must be reviewed after the correction.
