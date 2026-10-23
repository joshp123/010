# Surveyed surfaces on native bridge decks

Written by AI on 2026-10-24 by model GPT-6.

`python3 scripts/build-bridge-surfaces.py` intersects retained BRT transport footprints with reviewed native deck triangles. It produces standard 3D Tiles/glTF in `dist/data/bridge-surfaces/`. It needs the existing Python environment with NumPy, pyproj and Shapely 2.1; no additional runtime dependency ships to the browser.

The source bridge remains the structure. The new geometry supplies road, cycleway and tram surface classes at interpolated native deck elevations. Mesh metadata uses `surfaceKind`, matching the street stage. Colour and the coplanar rendering offset belong to presentation. No colour, image, fixed ground elevation or extra bridge slab is baked into this geometry.

## Source contract

`source-data/bridge-decks.json` records explicit reviewed triangle indices and the SHA-256 of each native B3DM. The builder caches the decoded original bytes in `work/data-cache/bridge-surfaces/`. It can reacquire missing bytes from the recorded public URL; a changed edition stops regeneration and needs a new review. These selections are replaceable source data, independent of renderer code.

The transport input is `source-data/transport-network.geojson.gz`. Only features explicitly recorded as on a fixed or movable bridge, and in use, are eligible. Ordinary roads below bridges, tunnels and ferry connections are not draped. Road and cycleway boundaries come from polygons. A double tram centreline uses the existing street stage's 6 m ribbon interpretation; this width is illustrative, not a measured railbed boundary. The output manifest lists feature identifiers, source forms, source hashes, coordinate frame and omissions.

BRT is attributed to Kadaster / PDOK under CC BY 4.0. Municipal native geometry is public domain; credit Gemeente Rotterdam. See [the source inventory](data-sources.md). The retained transport features were simplified by 1 m during acquisition; original API responses remain in the SSD cache for a future rebuild with more precise footprints.

## Reviewed geometry and omissions

Erasmus has a continuous 260-triangle upper deck, 24,905 square metres, at source elevations 3.897–15.671 m. Its underside is a separate component about 1.067 m lower. Willems has a continuous 104-triangle upper deck, 15,265 square metres, at 7.730–13.700 m, with a separate underside 1 m lower. Shared-edge connectivity and shallow face normals established these components; the selected triangle lists are retained explicitly rather than recomputing a heuristic silently at runtime.

Taking the highest native surface is incorrect: a surveyed roadway point on Erasmus hits a cable at 23.066 m above the actual 15.237 m deck. Connected deck selection avoids draping roads onto cables or towers.

Van Brienenoord was inspected but is explicitly omitted. It has several broad shallow components, including an 85,645-square-metre component, and no unambiguous reviewed upper deck selection yet. Its native bridge still renders. No source supplies a continuous main-deck footway polygon here, so unknown strips remain the native bridge material; no pedestrian layout is invented.

## Validation and limits

The two GLBs contain 1,899 triangles and 71,000 bytes before HTTP compression, approximately 26 KB compressed. The vendored GLTFLoader parses both and retains all surface classes. Every decoded vertex lies within 1 mm of the selected deck footprint; the largest measured vertical difference after Float32 encoding is 0.038 mm. Child bounding boxes enclose all decoded vertices in the standard ENU tile frame.

The integrated Erasmus view was inspected in the in-app browser at a 620 m span: surface distinctions sit on the native deck without restoring the transverse duplicate slab. That observation covers this view; it does not establish correct source selection on every bridge. Add other bridges by reviewing their original geometry and recording selections, or replace the selection stage with a better source or reconstruction. Keep unresolved cases explicit.
