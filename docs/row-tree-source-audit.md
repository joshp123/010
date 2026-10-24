# Large crown in actual Schiedamseweg phone view

Written by AI, GPT-6, 2026-10-24. This checks **placement and dimensions**, not artistic acceptance or present-day inventory truth.

The actual canonical `illustrated-row-day-front-phone.png` was fetched and visually inspected. Its upper-left tree is substantially larger than adjoining trees/buildings and its clustered-sphere appearance remains rejected.

Independent decoding of `source-data/vegetation-style/15_33577_6934.cmpt.gz` identifies it as **bm_83722_K / Boom_id 83722**, prototype `proto_8.glb`, source instance 3. The source records Watergeusstraat, Ulmus minor, planted 1975, source date 2023-10-15, total height 22 m, crown diameter 15 m, trunk/stem length 6 m, ground `Hoogte` 3.2133 m. The nearby small crown is a different source instance, bm_404110_K, diameter 3 m and total height 8 m.

The decoded large crown base is 9.2071 m, agreeing within 7 mm with source ground plus stem. `SCALE_NON_UNIFORM` is [15,15,16], i.e. crown diameter in both horizontal dimensions and height minus stem vertically after the native Y-up-to-Z-up adjustment. `NORMAL_RIGHT`, `NORMAL_UP` and their cross product have unit length. The original prototype has x/z extent −0.5…0.5 and y extent −0.003309…0.996691. Applying the actual complete source transform produces crown heights 9.1541…25.1541 m in the native vertical convention.

Using the actual 51.90963,4.44711,100 m,125° camera and 390×844 viewport, the independently projected original prototype occupies **[93.81,44.20,220.06,181.93] pixels**. This matches the actual rendered giant crown. The nearby small crown independently projects to [217.77,190.34,243.02,222.69], also matching the actual image. There is no evidence here of a second scale multiplication or misplaced crown base.

![Original-source projected bounds over the actual rendered phone image](images/row-tree-source-projection.png)

Run `python scripts/inspect-row-tree.py` with NumPy and pyproj. It decodes source bytes, the original GLB node transforms, i3dm quantized positions, rotation vectors and nonuniform scales, then applies the same geographic/camera frame independently in Python. The full report and nearby instances are retained in `source-data/vegetation-style/row-tree-instance-audit.json`.

This does **not** establish that the 2023 inventory's 15 m diameter or 22 m height matches the present tree. The requested 2026 orthophoto pilot covers its RD position [90283.81,436074.20], and should supply independent canopy evidence when acquired. Do not shrink the tree to fit adjacent buildings on the strength of aesthetics. The source supports a large tree here; it does not support the current repeated plastic foliage spheres. Shape/material interpretation needs improvement independently of scale.
