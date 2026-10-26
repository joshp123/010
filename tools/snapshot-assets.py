# Written by AI on 2026-10-26 by model Claude Opus 5.5.
# The asset pipeline rewrites tiles' buildings.glb while it runs; a render
# that reads a half-written file falls back to the raw 2018 buildings. This
# copies each tile's GLBs once they are complete (the GLB header's length
# equals the file size, twice in a row) into builds/dev/assets-snapshot,
# which renders read as ?assets=./assets-snapshot.
# Usage: python3 tools/snapshot-assets.py
import shutil, struct, time
from pathlib import Path

DATA = Path("/Volumes/Josh Extreme Pro USB4 4TB/010")
SNAPSHOT = DATA / "builds/dev/assets-snapshot/tiles"


def complete(path):
    data = path.read_bytes()
    return len(data) >= 12 and data[:4] == b"glTF" and struct.unpack_from("<I", data, 8)[0] == len(data)


copied = 0
for source in sorted((DATA / "assets/v1/tiles").glob("*/buildings*.glb")):
    target = SNAPSHOT / source.parent.name / source.name
    for attempt in range(60):
        if complete(source):
            stamp = source.stat().st_mtime_ns
            time.sleep(0.5)
            if source.stat().st_mtime_ns == stamp and complete(source):
                break
        time.sleep(5)
    else:
        raise SystemExit(f"{source} never settled")
    if not target.exists() or target.stat().st_mtime_ns < source.stat().st_mtime_ns:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied += 1
print(f"snapshot: {copied} files updated in {SNAPSHOT}")
