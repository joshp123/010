# Local source-to-illustration pilot (unreviewed)

This bounded experiment runs on the manager's Apple Silicon Mac, from the project's pinned `devenv`. It changes no runtime assets. No cloud installation or inference has been performed. M4 Pro / 24GB feasibility and visual quality remain untested: upstream's published memory measurements use a **64GB M4 Pro**. The official 4B checkpoint is public, ungated and Apache-2.0; no paid service, account or training is needed. Model weights are approximately 15GB; dependencies, caches and peak memory add to that.

The first input is an actual front facade of BAG `0599100000671699`, selected source triangles 624/625 from the retained eight-building row. It has four clearly observed upper-storey windows, pale frames/bands and red-brown masonry. This excludes the known party-wall roof-projection failures. The second input must be the manager's actual style-reference crop; it is not architectural evidence or implied approval. Source photo blur and slight image-projection skew remain visible. The helper rectifies the **measured plane**, not the photographed windows; it does not silently straighten or invent architecture. Inspect generated opening registration against this source before any UV transfer. Further photo-projection correction would need an explicit recorded correspondence, not a guessed new window layout.

## Run on the Mac

From the SSD project checkout, enter `devenv shell`. `uv` is supplied by `devenv.nix`; Python dependencies install into an isolated SSD environment, not the Nix Python environment. Substitute the real SSD and retained style-reference path:

```sh
python scripts/run-mflux-pilot.py \
  --ssd-root /Volumes/ExternalSSD/010-mflux \
  --style /absolute/path/to/manager-retained-reference.png \
  --run-name facade-seed42-first \
  --run
```

Omit `--run` and choose a distinct run-name to prepare/prove the command and provenance without installing or downloading anything. Real execution checks macOS arm64. It clones the exact upstream commit, uses its frozen `uv.lock`, installs Python 3.13 into the SSD cache, downloads the exact HF model revision into the SSD, then runs offline inference. The helper records resolved Python version/packages, upstream lock hash, model file hashes, copied input hashes, command, log and output hash in the run folder. The source/style/prompt copies stay with that run. Failed runs retain their evidence and cannot be overwritten accidentally. Cached weights and dependency downloads are reused across new run names.

Pinned MFLUX commit: `a3b21fcaa88726b2267bd42bfc2e2d722f7d5a47` (project version 0.23.0). Model revision: `e7b7dc27f91deacad38e78976d1f2b499d76a294`. Primary source audit is retained in `source-data/mflux-pilot/upstream-audit.json` and `upstream/`. The actual current CLI accepts local weights through **`--model /snapshot --base-model flux2-klein-4b`**, not a `--model-path` argument. Verified controls: multiple `--image-paths`, `--prompt-file`, four `--steps`, seed 42, `--quantize 8`, `--low-ram`, explicit 512×1024, `--metadata`. No experimental small text encoder or LoRA is enabled. If memory fails, preserve the log; a separate explicitly recorded 4-bit experiment can be made, rather than silently changing this run.

## Exact surface contract

`python scripts/prepare-mflux-surface.py` regenerates the source panel and mapping from retained original GLB and triangle evidence. `source.json` records hashes and source license (Gemeente Rotterdam, CC BY 4.0). `surface-map.npz` records, at each integer panel pixel centre, the original `triangle_index`, original top-left `uv`, and original `image_index`; uncovered pixels are -1/NaN. `local_to_image` maps original local XYZ to panel XY/depth. No geometry, mesh normals, atlas UVs or source image bytes are changed.

The white region of `edit-mask.png` allows **only the upper two storeys**. The storefront and illegible lettering remain original. The image model does not enforce this mask; it is a hard boundary for a later reviewed bake. To bake a reviewed candidate, rasterize each selected original atlas UV triangle and transform its barycentric source XYZ through `local_to_image`; sample the candidate only where `edit-mask` is white, preserving every other atlas texel. Use the original GLB's image indices and verify atlas UV sharing before writing. Do not simply stretch the generated image over the whole building. The existing whole-row source renders and retained original geometry provide independent oblique views for judging registration after bake.

After inference, bake a separate original-geometry review GLB and two opposing source/candidate views:

```sh
python scripts/bake-mflux-pilot.py \
  --candidate /Volumes/ExternalSSD/010-mflux/runs/facade-seed42-first/candidate.png \
  --output work/mflux-facade-seed42-first
```

This command verifies the retained source/mapping/mask hashes, rejects a changed output size, samples the candidate through exact barycentric UV/XYZ mappings, protects texels shared by unselected source triangles, and asserts all other atlas texels are identical. It appends PNG image data while retaining the complete original binary prefix, mesh/accessor/node/material/texture contracts. `candidate-row.glb` and `view-a-source-candidate.png` / `view-d-source-candidate.png` are separate review artifacts. Source is left, candidate right; no production file changes. `bake.json` records hashes and changed/protected texel counts. Model-weight hashing streams 1 MiB chunks, avoiding a multi-gigabyte memory allocation. `--style-status` is optional descriptive provenance with a neutral reference-only default, not an approval requirement.

The runnable helper ends with an **unreviewed image**, not an automatic acceptance gate or publication step. Review the four opening contours, pane divisions, slim frame widths, masonry/stone boundaries and source occlusions; reject shifted windows, invented decoration or generic source-erasing fills. The present pilot is a source-and-runtime test within the whole-city rescue, not evidence that isolated facade styling completes it.

## Controlled second trial

The manager's first actual Mac run completed in 200.55 s wall time (187.6 s denoising, four steps, reported peak MLX 10.33 GB). This verifies that specific operating path, not total system-memory usage or general performance. The manager/root inspected the image and opposing-view bake: four windows were crisp, but the result remained too photographic and shifted opening proportions/positions. Storefront lettering was hallucinated but excluded from the GLB by the hard mask. **Art/fidelity failed; do not scale that result.** These are manager-reported observations; the cloud worker did not rerun inference.

The exact first prompt is retained as `interpretation-v1-rejected.txt`, including its incorrect “authoritative rectified” wording. The default prompt now correctly describes a plane-unwrapped photograph with remaining projection warp. `interpretation-v2-painted.txt` asks for the actual painted facade reference's miniature/pixel drawing language while distinguishing pixel registration from architectural truth. It permits no guessed straightening or opening movement. That geometric problem needs separately supported correspondences, not stronger prompt assertions.

For trial two, supply the **actual independent artwork v4 plane90 facade-panel file** held by the manager/artworker. It has not been supplied to this cloud worker and is not labelled approved. Do not substitute an unrelated illustration. The source image, edit mask, mapping, model revision, 512×1024 size, 8-bit quantization, four steps and seed 42 stay unchanged. Only the prompt and style reference change; this is a controlled interpretation comparison, not a single-variable attribution of improvement.

```sh
python scripts/run-mflux-pilot.py \
  --ssd-root /Volumes/ExternalSSD/010-mflux \
  --style /absolute/path/to/actual-v4-plane90-facade-panel.png \
  --prompt-file source-data/mflux-pilot/interpretation-v2-painted.txt \
  --run-name facade-seed42-painted-v2 \
  --run
python scripts/bake-mflux-pilot.py \
  --candidate /Volumes/ExternalSSD/010-mflux/runs/facade-seed42-painted-v2/candidate.png \
  --output work/mflux-facade-seed42-painted-v2
```

The runner copies and hashes the selected prompt and exact style file, records the prompt path and runner-code hash, and leaves previous runs untouched. Compare the source with both trial images and their actual baked opposing views: did the rendering become deliberately illustrated, and did opening displacement worsen or persist? A cleaner illustration with moved openings still fails. No second-trial inference or result is claimed here; the full block remains the intended art scope after this bounded operating experiment.
