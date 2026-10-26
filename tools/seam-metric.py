# Written by AI on 2026-10-26 by model Claude Opus 5.5.
# Seam metric for a pyramid level: mean colour jump across tile joins divided
# by the mean jump across the middle row and column of the same tiles (a
# matched control: same content, no join). 1.0 means joins are invisible. Usage: python3 tools/seam-metric.py LEVEL_DIR
import os, re, sys
import numpy as np
from PIL import Image

folder = sys.argv[1]
tiles = {}
for name in os.listdir(folder):
    m = re.fullmatch(r"(\d+)_(\d+)\.webp", name)
    if m:
        tiles[(int(m[1]), int(m[2]))] = np.asarray(Image.open(os.path.join(folder, name)).convert("RGB"), float)
across, inside = [], []
for (c, r), a in tiles.items():
    h = a.shape[1] // 2
    if (c + 1, r) in tiles:
        inside.append(np.abs(a[:, h] - a[:, h - 1]).mean())
    if (c, r + 1) in tiles:
        inside.append(np.abs(a[h] - a[h - 1]).mean())
    if (c + 1, r) in tiles:
        across.append(np.abs(tiles[(c + 1, r)][:, 0] - a[:, -1]).mean())
    if (c, r + 1) in tiles:
        across.append(np.abs(tiles[(c, r + 1)][0] - a[-1]).mean())
print(f"seam metric {np.mean(across) / np.mean(inside):.3f} over {len(across)} joins")
