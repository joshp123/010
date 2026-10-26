# Written by AI on 2026-10-26 by model Claude Opus 5.5.
# Measure the colour vocabulary of reference pictures per surface type, in
# OKLab, so the renderer's palette is set from measurement, not by eye.
# Surface types by colour rule (references have no class map): vegetation,
# water, road (dark neutral), paving (light neutral), brick/tile (warm red).
# Usage: python3 tools/measure-palette.py OUT.json IMAGE [IMAGE ...]
import json, sys
import numpy as np
from PIL import Image

def oklab(rgb):
    c = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    l = 0.4122214708 * c[:, 0] + 0.5363325363 * c[:, 1] + 0.0514459929 * c[:, 2]
    m = 0.2119034982 * c[:, 0] + 0.6806995451 * c[:, 1] + 0.1073969566 * c[:, 2]
    s = 0.0883024619 * c[:, 0] + 0.2817188376 * c[:, 1] + 0.6299787005 * c[:, 2]
    l, m, s = np.cbrt(l), np.cbrt(m), np.cbrt(s)
    return np.stack([0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
                     1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
                     0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s], -1)

pixels = np.concatenate([np.asarray(Image.open(p).convert("RGB")).reshape(-1, 3) / 255.0 for p in sys.argv[2:]])
lab = oklab(pixels)
L, C = lab[:, 0], np.hypot(lab[:, 1], lab[:, 2])
H = (np.degrees(np.arctan2(lab[:, 2], lab[:, 1])) + 360) % 360
types = {
    "vegetation": (H > 100) & (H < 160) & (C > 0.04),
    "water": (H > 180) & (H < 250) & (C > 0.03) & (L < 0.75),
    "road": (C < 0.03) & (L > 0.2) & (L < 0.5),
    "paving": (C < 0.03) & (L >= 0.55) & (L < 0.88),
    "brick": (H > 15) & (H < 55) & (C > 0.06),
}
def summary(mask):
    if mask.sum() < 100:
        return None
    return {"share": round(float(mask.mean()), 3), "L": [round(float(np.percentile(L[mask], q)), 3) for q in (10, 50, 90)],
            "C": round(float(np.median(C[mask])), 3), "H": round(float(np.median(H[mask])), 1),
            "median_srgb": [round(float(v), 3) for v in np.median(pixels[mask], axis=0)]}
out = {"all": {"L": [round(float(np.percentile(L, q)), 3) for q in (2, 10, 50, 90, 98)], "C_median": round(float(np.median(C)), 3)},
       **{name: summary(mask) for name, mask in types.items()}}
json.dump(out, open(sys.argv[1], "w"), indent=1)
print(json.dumps(out, indent=1))
