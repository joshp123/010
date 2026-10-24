# Optional runtime binding

Original attachment is retained unchanged as `010-source-glazing-emission.zip`; `integration-manifest.json` records its content hash. Source annotations, masks and fitting scripts remain available. Public text copies omit private handoff identifiers. This file and the integration manifest describe our separate binding step.

Rebuild the baseline using `python scripts/prepare-illustrated-row.py ROW_ARCHIVE_OR_DIRECTORY`, then run:

```
python scripts/prepare-row-emission.py EMISSION_ARCHIVE.zip
node tests/illustrated-row-runtime.mjs --emission
node tests/appearance-emission.test.mjs
```

The helper requires the exact baseline row manifest hash and matching municipal source hash. It verifies original material/image mapping (material10→image9; untextured material9 remains untouched), UV0, dimensions and zero emitting pixels outside supplied masks. Geometry binary, root transforms, normals, UVs, identities and base-color images remain unchanged. RGB emission is standard glTF sRGB; mask/phase are copied linear data with metadata only, not additional runtime texture loads. Ten RGB emission maps are fetched by the production GLTFLoader alongside ten base-color maps.

Runtime emissiveFactor is1, multiplied by the optional shared scene night uniform: day0, night1. The scene must pass that uniform to prepareAppearanceModel; without it this asset emits during daytime. Fixture light contribution is added after the source gate. There is no dynamic occupancy shader: supplied RGB encodes illustrative stable occupancy, never live occupancy.

The supplied source-annotation and four-view day/night CPU preview were inspected. They show partial observed glazing rather than a generic window grid. This does not establish exact phone/oblique runtime alignment or art acceptance. Full-scene day/night review remains necessary. Ten additional2048² maps add roughly223.7MB decoded RGBA including mipmaps; no resolution reduction was applied.

## Lossless emission border crops

The runtime helper now removes only unused black borders, keeping two native black padding pixels where available and retaining every original nonzero pixel. It skips entirely black image07. Nine NPOT RGB PNGs plus `KHR_texture_transform` preserve original UV0 source sampling without changing geometry/base-color UVs. Native originals remain above. Decoded emission allocation including mipmaps is32,362,278bytes rather than223,696,213bytes. The material's `emissionCropGuard` zeros source radiance outside transformed[0,1] before the emissive map and before fixture lighting, preventing clamp/mip-edge leakage beyond the observed rectangle.

`python tests/row-emission-crops.py` checks exact full-image reconstruction, every nonzero original texel sampled through the UV affine transform, empty07 omission, material10/image9 identity and unchanged geometry binary. Production-loader test now checks nine emission requests, transform scale/offset and image orientation. These preserve native pixels, not a lower-resolution rendition. GPU alignment remains a separate manager review.
