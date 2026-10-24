# Illustrated row review artifact provenance

Original attachment: `010-current-row-runtime-candidate(1).zip`, preserved as
Library file **libfile_e8b039daa49c819191f9685d96ab9d8c**. The exact input archive,
input geometry and output geometry hashes are recorded in `manifest.json`.
`artifact-README.md` and `georeference-and-identities.json` are unmodified copies
from the attachment, including its explicit unresolved art issues. The original
artifact remains separately replaceable; this preparation is not art acceptance.

Reproduce from the original ZIP or its extracted directory:

```sh
python scripts/prepare-illustrated-row.py /path/to/010-current-row-runtime-candidate.zip
python tests/illustrated-row.py
node tests/illustrated-row-runtime.mjs
```

Without a path the helper uses `work/illustrated-row-review`. It copies all ten
2048×2048 PNGs byte-for-byte to `public/data/illustrated-row/textures/`, preserves
materials and all drawn positions/normals/UVs, and splits draw indices by the
original `_BATCHID` metadata. Every single-primitive output mesh carries explicit
16-digit `bagId`, suitable for the existing visibility reconciliation. There are
54 draws, eight buildings and 678 unchanged municipal source triangles.

The original root matrix is retained exactly. The duplicate `CESIUM_RTC`
extension is removed from the derived GLB and appears exactly once as the
3D Tiles child translation. The tight source-frame box is computed from original
positions and bounds are independently checked against retained municipal source.
Do not apply the artworker's separate legacy diagnostic alignment.

Runtime URL: `/data/illustrated-row/tileset.json`. This is a review-only layer;
default/current scene selection and any temporary review cache budget are owned
by scene integration. PNGs are not repacked, resampled or compressed differently.
All individual assets are below25MiB, although decoded texture memory remains
large and is not a production budget claim.

Independent tests compare all 678 output triangles to the original municipal
B3DM, prove BAG identity/root matrix/one-RTC placement and all ten PNG hashes.
The production GLTFLoader fetched the GLB and all ten external PNGs over HTTP200,
decoding ten2048² texture maps with eight actual mesh BAG identities. Khronos
validation reports zero errors/warnings. These are fidelity/loading checks;
the manager owns the actual city image and architectural acceptance.

## Actual city review

Use `?appearance=illustrated-row&lat=51.90963&lon=4.44711&span=100&bearing=35&light=day`, then rotate and switch night in View. `appearance=current` retains the original municipal photographic candidate; the default remains the previous source edition. Only the eight visible illustrated BAG identities suppress fallback buildings, and unloading them restores fallback indices.

The ten unchanged 2048² maps require about 224MB of decoded RGBA with mipmaps before surrounding city geometry. This explicit review mode uses a384MiB city-cache budget so that the supplied artwork cannot evict the essential ground. Other modes retain224MiB. This is a measured input-size accommodation for review, not a final phone performance or city-wide residency decision. No painted texture pixels were reduced. The shared scene also includes the separately reviewable public-space/foliage and neutral night-light candidate. Full-block verified night emission is still pending the art worker.
