# Written by AI on 2026-10-26 by model Claude Opus 5.5.
# Pack a pyramid's level-0 depth tiles (d0/, 256 px per 512 px image tile)
# into dd/: one 256 px file per 2 x 2 image tiles, 1.2 m per depth sample.
# Each output sample keeps the nearest surface of the four it covers, so a
# building edge still hides what is behind it. Cuts depth files by 75%.
# Usage: python3 tools/pack-depth.py PYRAMID_BEARING_DIR
import json, os, sys
import numpy as np
from PIL import Image

folder = sys.argv[1]
meta = json.load(open(os.path.join(folder, "meta.json")))
level = meta["levels"][0]
os.makedirs(os.path.join(folder, "dd"), exist_ok=True)
for row in range(-(-level["rows"] // 2)):
    for column in range(-(-level["columns"] // 2)):
        units = np.zeros((512, 512), np.int32)
        for dy in (0, 1):
            for dx in (0, 1):
                path = os.path.join(folder, "d0", f"{2 * column + dx}_{2 * row + dy}.png")
                if os.path.exists(path):
                    a = np.asarray(Image.open(path).convert("RGB")).astype(np.int32)
                    units[dy * 256:(dy + 1) * 256, dx * 256:(dx + 1) * 256] = a[..., 0] * 256 + a[..., 1]
        blocks = units.reshape(256, 2, 256, 2).transpose(0, 2, 1, 3).reshape(256, 256, 4)
        empty = blocks == 0
        nearest = np.where(empty, 1 << 20, blocks).min(axis=-1)
        nearest[empty.all(axis=-1)] = 0
        out = np.zeros((256, 256, 3), np.uint8)
        out[..., 0], out[..., 1] = nearest // 256, nearest % 256
        Image.fromarray(out).save(os.path.join(folder, "dd", f"{column}_{row}.png"), optimize=True)
print("packed", folder)
