# Municipal source delivery decision

Written by AI on 2026-10-25 by model GPT-6 Astra.

The product outcome is a genuine Rotterdam city arriving promptly, then refining to unchanged native source detail. A smaller download alone does not establish that outcome. Current two loading corrections are independently releasable; this study proposes the next delivery mechanism and makes no visual acceptance claim.

## Existing resources and terms

- Existing public repository `joshp123/010`, MIT application code; no releases at inspection. Geographic assets retain their own terms.
- Current textured source edition `3adbe5af-d05c-475a-b34c-59e69ba8dadc`: Gemeente Rotterdam, CC BY 4.0. Exact current-layer/catalog linkage is retained in runtime `source-data/current-building-evidence/catalog-evidence.json`; https://hub.clearly.app/datasets/65ef2475fe2ac522c6ac7b63/information . Do not substitute the older public-domain CityGML listing. Derived assets must identify source edition, attribution, licence and texture-level transformation.
- GitHub permits 1000 assets per release, each under 2 GiB, and states no total release size or bandwidth quota: https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases . Its general excessive-bandwidth policy still allows throttling/suspension: https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies . This is available project distribution, not a guaranteed CDN SLA.
- REST general authenticated quota is 5000 requests/hour, with general content creation limits of 80/minute and 500/hour: https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api . Release upload POSTs have no documented exemption in the inspected docs. A per-tile upload schedule must conservatively allow this constraint, rather than discovering it after tens of thousands of uploads.
- Release immutability is available, but repository settings were NOT changed. Exact-hash filenames and non-replaced versioned tags are sufficient for the proposed initial contract; enforcing account/repository settings is a separate decision.

## Actual source scope and measured cost

`hierarchy-census.json` enumerates every content URI in the 40 source subtree JSONs. Exact counts: 1176 level15, 3471 level16, 9435 level17, 23901 level18; total37983. Source metadata itself is small enough to retain locally.

`payload-samples.json` contains one median-order finest tile from EACH of the40 geographic subtrees, plus8 level15 samples. This is spatial stratification, not a random sample or upper bound. Source wire SHA256, bytes, image totals, download and encoding time are recorded. Finest samples downloaded54.396MiB, range0.0366–6.580MB; a separately inspected ordinary central tile was10.294MB, so larger outliers are known.

For each finest sample, images were BOX-resized to128/256/512 and encoded as lossless WebP, keeping the original image whenever smaller. Geometry, metadata and UVs were not simplified. The image representation is lossless relative to the derived mip, not relative to native photography. Native close fallback remains essential.

Weighting each sample by the EXACT number of finest tiles in its own subtree gives these planning estimates:

| Output | Approximate municipality size |
| --- | ---: |
| Native source wire downloads |39.87GiB |
|128px images + original geometry/metadata |2.05GiB |
|256px images + original geometry/metadata |4.98GiB |
|512px images + original geometry/metadata |16.13GiB |
|256+512 combined |21.11GiB |

These include duplicated original geometry for each level and do not credit cross-tile image deduplication. Derived B3DM header/JSON padding or gzip savings are not fully compiled here. Texture distributions can vary within each subtree; a production compiler must record actual totals before upload. No statement that this fits the Sites archive is warranted: it plainly belongs outside that227MiB delivery archive.

The40 finest sample downloads took76.969 aggregate seconds; decoding/encoding all three derived levels took24.275 aggregate seconds with two concurrent workers. Subtree weighting projects15.79 sequential download-hours and4.60 aggregate processing-hours for all THREE levels. These are machine/origin-specific planning figures, not elapsed-time promises;2–4 bounded workers overlap transfer. The actual raw download estimate is40GiB, so free disk/raw-retention capacity must be checked before municipality compilation. No full municipality download or upload was started.

## Serving evidence

An actual official GitHub CLI release asset request followed302 to release-assets.githubusercontent.com, returned206 for Range0–99, and advertised Accept-Ranges bytes. Neither redirect nor final response exposed Access-Control-Allow-Origin. Actual Chrome fetch from localhost failed. Thus direct release URLs cannot be assumed to work in this browser loader. The existing Sites Worker can stream a fixed repository/release asset through a same-origin route, forwarding Range and caching exact immutable bytes. No codec, credentials in browser, arbitrary URL relay, new storage account or image server is needed. Signed redirect URLs are transient; retain the stable versioned GitHub release URL, never a signed redirect.

## Recommended bounded path

1. Reuse the existing offline texture-level compiler. Emit source-preserving B3DM/GLB levels with unchanged positions, RTC, UVs, batch identities and materials except image representation. Keep native official source as final close fallback; retain original source hashes/provenance. No request-time image processing.
2. Compile256/512 only when they materially reduce a tile. Record per-tile image sampling footprint using the existing physical-screen residency convention. A compact manifest supplies immutable derived URL, source URL/hash and level sampling error.
3. Feed those levels into the existing source hierarchy/REPLACE loader, preserving the presented genuine ancestor until replacement is ready. Select by physical-screen detail; final close must still select native. Do not fetch all levels serially or replace identity reconciliation.
4. A fixed-origin Worker route streams/cache exact release bytes. Browser requests continue to look like normal B3DM/GLB requests; errors return to existing source fallback.

**Publication decision:** one asset per tile/level is the simplest serving contract, but23901×2=47802 assets means at least48 releases and, under the documented general500 content-creations/hour ceiling, roughly96 upload-hours before retries. This endpoint's exact secondary-limit behavior is unproven because no upload was authorized. Even one level requires23901 assets/~48hours under that conservative ceiling.

If that publication cost is unacceptable, the narrow alternative is plain spatial byte concatenation (or uncompressed tar) capped around64MiB per release asset, with compiler-recorded offset/length per unchanged tile. Approximately21GiB implies roughly338 such assets, all within one release; actual packing totals will differ. The SAME fixed-origin Worker maps tile ID to one immutable asset+Range and returns just that tile as a normal200 response. This adds a byte-offset table and Range forwarding, not a browser codec, pack platform or cache service. Range support is actually observed; cold range delivery latency through the Worker remains to be proven. Upload count drops to hundreds; one missing pack can still fall back to original source. Do not introduce packing merely for aesthetics: it addresses the concrete tens-of-thousands-of-POST publication constraint.

The next substantive experiment should compile a COMPLETE existing source subtree spanning an ordinary city/Hoek exploration area and expose its full progressive hierarchy in the existing main renderer after root approves storage/publication. Watch cold arrival, zoom, opposing rotation and genuine metro jumps, with identical final native detail and continuous source context. An isolated2-BAG render cannot accept this path. No release, tag, settings or upload was created by this study.
