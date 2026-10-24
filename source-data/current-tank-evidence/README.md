# Current textured storage-tank evidence

One actual port sample from **Opslagtanks LOD2 texture - Actueel**, resource
`25da2fa9-d5b7-4d44-b100-7ab3b3bf51dc`. The selected leaf is
`16/67119/13875.b3dm`, around **51.889845 N, 4.349129 E** in the Pernis port area.
Its bounds are 4.347672–4.350586 E, 51.888428–51.891262 N.

## Actual source

The retained 12,381,016-byte B3DM contains **14 tank features**, **23 meshes /
23 primitives**, **2,996 triangles**, and **22 original 1024² texture images**.
Identifiers are `OST_12968350` etc., **not BAG IDs**. Attributes retain
`creationDate: 2024-05-23`; this is a model record, not a photographic capture
date. Current geometry, normals, UVs, material definitions, node transforms and
feature-table RTC placement are retained unchanged.

`source-views.jpg` and the two PNGs are actual CPU depth-buffer renderings of
these original source meshes with original source textures from opposite local
Y-up camera directions. No palette filter, illustration, generated details or
added scene lights are used. Rendered tanks show roof seams/spokes, wall tones,
ladder/stair markings and some photographic ground contamination. Markings in
an image do not establish modeled 3D railings or surveyed machinery. Bright
sunlit surfaces remain strongly exposed. This is richer appearance evidence,
not a finished miniature scene or browser visual acceptance.

## Licence and retained provenance

Attribution: **Gemeente Rotterdam — 3D Rotterdam**, **CC BY 4.0**,
https://creativecommons.org/licenses/by/4.0/ . The manager independently verified
this exact tank endpoint in the resource table on the same live Clearly dataset
whose licence is CC BY 4.0:
https://hub.clearly.app/datasets/65ef2475fe2ac522c6ac7b63/information .
`catalogue-evidence.json` records the observation chain explicitly; no separate
tank-specific catalogue URL is invented. The downloaded municipal application
module independently confirms the exact tank resource and layer name, retained
as `raw/module.json.gz`. This current resource's terms must not be replaced by
the older endpoint's public-domain assumption.

Original root/index/B3DM bytes are losslessly compressed under `raw/`. Sidecars
retain source URLs, request timestamps, response headers, decoded sizes and
SHA256 hashes. The extraction helper copies the embedded GLB **literally** into
`work/current-tank-evidence/original.glb`, using its declared GLB length (the
B3DM also has container padding). No duplicate 12 MB derived GLB is committed.
`inspection.json` retains original batch attributes, material/transform records,
source node bounds and hashes. No extra ZIP duplicates these retained bytes.

## Compatibility with the existing implementation

The transport is standard B3DM / glTF2 PBR with POSITION, NORMAL, TEXCOORD_0 and
_BATCHID. The current building converter's decoding and vertex compaction are
reusable, **but its identity and metadata contract is not tank-safe**: it labels
meshes `BAG_...`, emits `extras.bagId`/`bagIds`, and describes the result as a
building source. Feeding `OST_*` through it would fabricate BAG identities.
Tank features need their original tank-ID namespace; do not reconcile or hide
buildings by those IDs.

The current scene loads the **older** tank endpoint
`c70023a7-2878-41e9-bb81-a7c454bc310a`; its `colorModel` replaces tank source
materials, and `featureColor('tanks')` returns uniform `#d9d9cb`. Merely swapping
the URL would therefore still discard this appearance evidence. A source-rich
port path can use these native textured tiles while retaining their PBR maps,
with shared lighting/cutaway applied without overwriting appearance. Replace the
old tank layer rather than overlaying duplicate cylindrical geometry. This
probe has not changed any runtime or converter code.

Offline reproduction: `python scripts/inspect-current-tanks.py`.
Explicit bounded acquisition: append `--acquire`. Dependencies are NumPy and
Pillow plus the existing source-inspection helpers. Cached sources are hash
verified. Both views fit the entire source group without clipping. No paid
resource or account is required.
