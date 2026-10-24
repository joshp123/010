# Current municipal source: Schans 66–80

Exact BAG **0599100000670808**, centre approximately 4.4475440184 E, 51.9081870547 N. This is photographic source evidence, not finished miniature art.

Attribution: **Gemeente Rotterdam — 3D Rotterdam, CC BY 4.0**. License: https://creativecommons.org/licenses/by/4.0/. Current resource and license were checked on the official linked catalog https://hub.clearly.app/datasets/65ef2475fe2ac522c6ac7b63/information. See `catalog-evidence.json`. The older edition's public-domain catalog must not be substituted for these current terms.

`raw/` retains the complete native root index, relevant nested index and original b3dm leaf (gzip transport/storage only). `pilot-metadata.json` identifies URLs and SHA-256 hashes of decoded source bytes, original batch attributes and RTC centre. The model's creationDate is 2024-11-01 and upstream files were last modified December 2025; neither establishes photographic capture date.

`pilot-original.glb` contains only this BAG's original 158 triangles, compacted unchanged positions, normals and UVs, original photographic image bytes, materials and node matrices. Unused source meshes/materials/images are removed. No facade features have been drawn, repaired or inferred. The RTC centre is external metadata, not baked into this standalone GLB. For geographical placement compose RTC translation × glTF Y-up to 3D Tiles Z-up × original node world matrix. The original complete b3dm remains available for independent interpretation.

`pilot-view-a.png` and `pilot-view-b.png` are two CPU orthographic previews of the exact textured source geometry with nearest source-pixel sampling and no relighting. They are not browser product screenshots. View directions are source-local, not asserted cardinal bearings. Roof and facade seams, baked shadows and photographic occlusion remain. In particular, the renderer does not invent missing windows. The current source visibly resolves window frames, facade rhythm, central stair strip, balconies, roof fascia and roof equipment more clearly than the legacy model.

## Reproduce

Requirements: Python 3, NumPy, Pillow. From the extracted archive/repository root:

```sh
python scripts/inspect-current-building-evidence.py
python scripts/test-current-building-evidence.py
```

The archive includes both scripts and their appearance-helper dependency. If retained raw files are absent, `python scripts/inspect-current-building-evidence.py --acquire` fetches the three public URLs. Existing metadata pins source hashes: upstream changes must be reviewed explicitly, rather than silently replacing the observed edition.
