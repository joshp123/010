# Written by AI on 2026-10-26 by model Claude Opus 5.5.
# Per-class colour statistics of a picture, from sampled rectangles (for a
# reference with no class map) or from a class-code image of our own render.
# Reports OKLab lightness and chroma per class and the lightness step across
# strong edges (mean |dL| over the top 3% of gradient magnitudes).
# Usage: python3 tools/measure-classes.py IMAGE BOXES.json | --codes CODES.png
import json, sys
import numpy as np
from PIL import Image

def oklab(rgb):
    c = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    l = 0.4122214708 * c[..., 0] + 0.5363325363 * c[..., 1] + 0.0514459929 * c[..., 2]
    m = 0.2119034982 * c[..., 0] + 0.6806995451 * c[..., 1] + 0.1073969566 * c[..., 2]
    s = 0.0883024619 * c[..., 0] + 0.2817188376 * c[..., 1] + 0.6299787005 * c[..., 2]
    l, m, s = np.cbrt(l), np.cbrt(m), np.cbrt(s)
    return np.stack([0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
                     1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
                     0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s], -1)

image = np.asarray(Image.open(sys.argv[1]).convert("RGB")) / 255.0
lab = oklab(image)
L, C = lab[..., 0], np.hypot(lab[..., 1], lab[..., 2])
masks = {}
if sys.argv[2] == "--codes":
    # Class codes from the renderer's class output (web/miniature/renderer.js, classOutput).
    codes = np.asarray(Image.open(sys.argv[3]).convert("RGB")).astype(int)
    code = codes[..., 0] // 16
    names = {1: "asphalt", 2: "paving", 3: "grass", 4: "water", 5: "tree", 6: "roof", 7: "wall", 8: "cycle"}
    for value, name in names.items():
        masks[name] = code == value
else:
    for name, boxes in json.load(open(sys.argv[2])).items():
        mask = np.zeros(L.shape, bool)
        for x0, y0, x1, y1 in boxes:
            mask[y0:y1, x0:x1] = True
        masks[name] = mask
gy, gx = np.gradient(L)
g = np.hypot(gx, gy)
strong = g > np.percentile(g, 97)
out = {name: {"L": round(float(np.median(L[m])), 3), "C": round(float(np.median(C[m])), 3), "n": int(m.sum())} for name, m in masks.items() if m.sum() > 50}
out["edge_step"] = round(float(np.mean(g[strong]) * 2), 3)
out["L_median_all"] = round(float(np.median(L)), 3)
print(json.dumps(out))
