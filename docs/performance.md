# Measured performance

Written by AI on 2026-10-24 by model GPT-6.

The map retains native source geometry. These checks measure the local app in the in-app browser; they do not establish cold-load speed, physical phone performance or a universal 100 ms response time.

The first public-domain check on 2026-10-24 at `010.jjpcodes.com`, 900 m centre view at night, submitted buildings at 5.37 s and settled at 11.69 s. This was the first visit to that origin, but external native tiles could already be in the browser cache. A public Kralingen pan at a 390 × 844 viewport recorded eight input-to-render submissions: median 12.7 ms, p95 14.7 ms, with zero pending/refused tiles after settling. No CPU or network throttling was applied. These measurements distinguish responsive camera movement from much slower detail streaming; the 100 ms loading aspiration has not been achieved.

At the city centre, 900 m span, night, warm-cache localhost loading settled in 5.2 seconds versus 21.9 seconds before exact surface-query acceleration: approximately 4.2 times faster. First buildings appeared in 3.9 seconds versus 3.5 seconds. The improvement removes broad triangle raycasts when placing transit and simulated traffic; it does not reduce geometry detail. See [exact surface queries](surface-query.md) and the retained `work/visual-qa/centre-night-accelerated.cpuprofile`.

At Delfshaven (51.9072, 4.449), 700 m span, day, a 390 × 844 viewport with 4× CPU throttling repeated the same drag from (180, 450) to (250, 500):

| Input to render submission | Before gesture deferral | After |
| --- | ---: | ---: |
| Median | 28.2 ms | 18.2 ms |
| 95th percentile | 708.3 ms | 21.9 ms |

Each run contained eight samples. This is a small controlled comparison, with CPU-side render-submission timing, not physical display latency or a real phone measurement. The final view had the correct updated coordinates and settled with zero pending or refused tiles. The rendered result was inspected in `work/visual-qa/mobile-gesture-final.jpg`.

During dragging, pinching, rotation and wheel bursts, the camera and rendering continue using the currently selected source tiles. Tile selection, bridge reconciliation, surface indexing and road reprojection resume after release and 120 ms without input. A long gesture into unloaded territory can therefore show cartographic fallback until it ends. Full detail then loads normally; deferred selection reports pending readiness, and full-detail export bypasses this deferral. Already-running source decoding can still consume CPU during input.

To reproduce, use the same view, viewport, cache state and CPU throttle; record input-to-render submission diagnostics through the drag, then verify final coordinates, tile readiness and the rendered map after release. Compare cold loading separately. Source-operation checks and exact reconciliation reuse are documented in [bridge surfaces](bridge-surfaces.md).

Prepared model transfer uses `public/_headers` to request `model/gltf-binary` and gzip for `/data/*.glb`. Cloudflare's single wildcard matches nested paths, so this covers prepared model tiles in subdirectories. Original GLB bytes, URLs and geometry stay unchanged; no sidecars or build dependencies are added. The existing immutable policy for fingerprinted framework assets is retained, and model cache lifetimes are unchanged. This uses [static asset headers](https://developers.cloudflare.com/workers/static-assets/headers/) and the Workers runtime's [automatic response encoding](https://developers.cloudflare.com/workers/runtime-apis/response/); do not also precompress the GLB files, which would encode them twice with this setup.

In an isolated local Wrangler 4.92.0 asset server, Erasmus transferred as 21,638 gzip bytes versus 58,852 original bytes (63.2% less), and a single HTTP decode restored the exact original SHA-256. Across all 1,870 prepared GLBs, an offline gzip level 6 calculation estimates 108.6 MB versus 165.7 MB raw (34.5% less); this is a transfer estimate, not an observed aggregate production download. Rebuild and publish through the existing Sites workflow, then verify the hosted response has gzip encoding and that `curl --compressed` restores the original file hash. Production encoding remains an acceptance check; the headers do not change geometry decoding cost or compress externally hosted native tiles.

A wider central view (`lat=51.925&lon=4.480&span=3400&bearing=35&light=day`) exposed 67 refused tree tiles at the earlier 48 MiB ceiling. The current 128 MiB ceiling loaded the complete requested view using 79.7 MB of tree source data, with zero pending/refused tiles. First buildings appeared at 1.75 s and all detail settled at 15.25 s in this local run; wide-view loading therefore remains substantially slower than the interaction target. The 24 MiB unused-cache target limits retained off-screen trees. These limits allocate on demand.
