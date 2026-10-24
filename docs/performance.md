# Measured performance

Written by AI on 2026-10-24 by model GPT-6.

The map retains native source geometry. These checks measure the local app in the in-app browser; they do not establish cold-load speed, physical phone performance or a universal 100 ms response time.

At the city centre, 900 m span, night, warm-cache localhost loading settled in 5.2 seconds versus 21.9 seconds before exact surface-query acceleration: approximately 4.2 times faster. First buildings appeared in 3.9 seconds versus 3.5 seconds. The improvement removes broad triangle raycasts when placing transit and simulated traffic; it does not reduce geometry detail. See [exact surface queries](surface-query.md) and the retained `work/visual-qa/centre-night-accelerated.cpuprofile`.

At Delfshaven (51.9072, 4.449), 700 m span, day, a 390 × 844 viewport with 4× CPU throttling repeated the same drag from (180, 450) to (250, 500):

| Input to render submission | Before gesture deferral | After |
| --- | ---: | ---: |
| Median | 28.2 ms | 18.2 ms |
| 95th percentile | 708.3 ms | 21.9 ms |

Each run contained eight samples. This is a small controlled comparison, with CPU-side render-submission timing, not physical display latency or a real phone measurement. The final view had the correct updated coordinates and settled with zero pending or refused tiles. The rendered result was inspected in `work/visual-qa/mobile-gesture-final.jpg`.

During dragging, pinching, rotation and wheel bursts, the camera and rendering continue using the currently selected source tiles. Tile selection, bridge reconciliation, surface indexing and road reprojection resume after release and 120 ms without input. A long gesture into unloaded territory can therefore show cartographic fallback until it ends. Full detail then loads normally; deferred selection reports pending readiness, and full-detail export bypasses this deferral. Already-running source decoding can still consume CPU during input.

To reproduce, use the same view, viewport, cache state and CPU throttle; record input-to-render submission diagnostics through the drag, then verify final coordinates, tile readiness and the rendered map after release. Compare cold loading separately. Source-operation checks and exact reconciliation reuse are documented in [bridge surfaces](bridge-surfaces.md).
