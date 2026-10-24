Written by AI, gpt-6-astra, 2026-10-24.

This is an unchanged photographic surface from the official Rotterdam West mesh, centred on a Maasvlakte container terminal. The live municipal viewer publishes five mesh regions in its app configuration; this acquisition currently supports West only. It is separate from the BAG building service.

Run with the existing project Python environment:

```
python scripts/acquire-port-photogrammetry.py --lon 3.9884597488 --lat 51.9531925023 --output source-data/municipal-port-mesh --render
```

`raw/` retains original hierarchy responses and the selected GLB. `acquisition.json` records exact URLs and hashes. `tileset.json` references that unchanged GLB locally. `source-view.png` shows a temporary local-tangent rasterization of the original triangles and photographed pixels. No source geometry, UVs or images were changed.

The selected mesh includes measured container stacks, machinery, buildings and ground without BAG/object identities. Use it as source geometry and photographic context for replaceable offline interpretation. Adding the entire mesh over the present scene would duplicate photographed ground and structures. Exact building replacement requires a spatial source correspondence, rather than assuming this mesh has the BAG identity of the building service.

The West root has two overlapping branches: branch 1 is coarse untextured geometry; branch 2 is textured photogrammetry. The selected branch-2 tile reports 2.700057 metres geometric error. Its referenced finer JSON children returned HTTP 403; this is incomplete accessible detail, not evidence that finer observations do not exist. The capture date and mesh-specific reuse licence are not established. The older building catalogue's licence must not be silently applied to this distinct mesh.
