# Written by AI on 2026-10-26 by model Claude Opus 5.5.
# Pack a site's pyramid tiles 4 x 4 to a file, so a deep pyramid fits the
# host's file-count limit. Run on the site build (dist), never on the SSD
# originals. Each pack: b"P010", uint32 count (16), then 16 x (uint32 offset,
# uint32 length) little-endian, then the tile bytes. Tile (c, r) of a level is
# entry (r % 4) * 4 + (c % 4) of pack p{c // 4}_{r // 4}.pack. The Worker
# (worker/index.js) serves the original tile URLs out of the packs.
# Usage: python3 tools/pack-tiles.py DIST/pyramids
import os, re, struct, sys
from collections import defaultdict

root = sys.argv[1]
packed = files = 0
for directory, _, names in os.walk(root):
    tiles = defaultdict(dict)
    for name in names:
        m = re.fullmatch(r"(\d+)_(\d+)\.webp", name)
        if m:
            c, r = int(m[1]), int(m[2])
            tiles[(c // 4, r // 4)][(r % 4) * 4 + (c % 4)] = name
    for (pc, pr), entries in tiles.items():
        blobs = [open(os.path.join(directory, entries[i]), "rb").read() if i in entries else b"" for i in range(16)]
        header = bytearray(b"P010" + struct.pack("<I", 16))
        offset = 8 + 16 * 8
        for blob in blobs:
            header += struct.pack("<II", offset, len(blob))
            offset += len(blob)
        with open(os.path.join(directory, f"p{pc}_{pr}.pack"), "wb") as f:
            f.write(header + b"".join(blobs))
        for name in entries.values():
            os.remove(os.path.join(directory, name))
        packed += 1
        files += len(entries)
print(f"packed {files} tiles into {packed} files")
