# Written by AI on 2026-10-26 by model Claude Opus 5.5.
# The image tool returns square or 3:2 images, so a long street elevation is
# cut into pieces no wider than 3:2, preferably where one wall meets the next
# (from wall-ids.png), each padded with absent-evidence grey to exactly 3:2.
# Only groups with enough photo evidence are cut; the rest go to tier 2.
# Usage: python3 tools/chunk-elevations.py TILE MIN_M2 MIN_PHOTO_FRACTION
#        python3 tools/chunk-elevations.py --stitch ELEVATION_DIR
import json, math, sys
from pathlib import Path
import numpy as np
from PIL import Image

GREY = (160, 160, 160)  # absent evidence inside a wall
OUTSIDE = (255, 255, 255)  # padding outside the building, to be kept white
DATA = Path("/Volumes/Josh Extreme Pro USB4 4TB/010")

def chunk(d):
    ref = Image.open(d / "reference.png").convert("RGB")
    w, h = ref.size
    ids = np.asarray(Image.open(d / "wall-ids.png").convert("RGB")).astype(int)
    key = ids[..., 0] * 65536 + ids[..., 1] * 256 + ids[..., 2]
    # Outside every wall (sky above the roofline, gaps): white, so the model
    # knows the building's true outline and cannot add storeys. Grey stays
    # only where a wall exists but the 2018 photo does not show it.
    pixels = np.asarray(ref).copy()
    pixels[key == 0] = OUTSIDE
    ref = Image.fromarray(pixels)
    # Column boundaries where the dominant wall changes.
    dominant = [np.bincount(np.unique(key[:, x], return_inverse=True)[1]).argmax() if True else 0 for x in range(w)]
    col_key = [np.unique(key[:, x])[np.bincount(np.unique(key[:, x], return_inverse=True)[1]).argmax()] for x in range(w)]
    cuts = [x for x in range(1, w) if col_key[x] != col_key[x - 1]]
    limit = int(1.5 * h)
    pieces, start = [], 0
    while start < w:
        end = min(w, start + limit)
        if end < w:
            options = [c for c in cuts if start + limit * 0.5 < c <= end]
            if options:
                end = options[-1]
        pieces.append((start, end))
        start = end
    out = d / "chunks"
    out.mkdir(exist_ok=True)
    for i, (a, b) in enumerate(pieces):
        canvas = Image.new("RGB", (limit, h), OUTSIDE)
        canvas.paste(ref.crop((a, 0, b, h)), (0, 0))
        p = out / f"{i:02d}"
        p.mkdir(exist_ok=True)
        canvas.save(p / "reference.png")
        json.dump({"x0": a, "x1": b, "padded_width": limit, "height": h}, open(p / "chunk.json", "w"))
    return len(pieces)

def stitch(d):
    ref = Image.open(d / "reference.png")
    w, h = ref.size
    out = Image.new("RGB", (w, h), GREY)
    calls = []
    for p in sorted((d / "chunks").iterdir()):
        info = json.load(open(p / "chunk.json"))
        g = Image.open(p / "generated-raw.png").convert("RGB").resize((info["padded_width"], info["height"]), Image.LANCZOS)
        out.paste(g.crop((0, 0, info["x1"] - info["x0"], h)), (info["x0"], 0))
        calls.append(json.load(open(p / "generation.json")))
    out.save(d / "generated-raw.png")
    json.dump({"tool": "image_gen.imagegen", "method": "chunked-3x2-v1", "call_count": len(calls), "chunks": calls,
               "written_by": "AI, Claude Opus 5.5 stitcher (tools/chunk-elevations.py), 2026-10-26"}, open(d / "generation.json", "w"), indent=1)

if sys.argv[1] == "--stitch":
    stitch(Path(sys.argv[2]))
    sys.exit()
tile, min_area, min_photo = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
groups = json.load(open(DATA / f"assets/v1/tiles/{tile}/elevations-inventory.json"))["elevations"]
total = n = 0
for g in groups:
    if g.get("area_m2", 0) < min_area or g["photo_pixels"] / max(1, g["geometry_pixels"]) < min_photo:
        continue
    d = Path(g["directory"])
    total += chunk(d); n += 1
print(f"{n} elevations cut into {total} chunks")
