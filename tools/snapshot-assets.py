# Written by AI on 2026-10-26 by model Claude Opus 5.5.
# A pinned snapshot of the building assets for renders. The asset pipeline
# rewrites tiles' GLBs while it runs; a render must never read a file that can
# change under it. This copies every tile's GLBs once each is complete (GLB
# header length equals file size, unchanged for half a second) into a new
# folder named by the hash of its contents:
#   builds/dev/assets-snapshots/<hash>/tiles/<tile>/buildings*.glb and their
#   assembly records (buildings*.json), plus snapshot.json
# A snapshot is never modified; an identical one is reused. Prints the hash.
# Renders read it as ?assets=./assets-snapshots/<hash>.
# Usage: python3 tools/snapshot-assets.py
import hashlib, json, shutil, struct, time
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("/Volumes/Josh Extreme Pro USB4 4TB/010")
ROOT = DATA / "builds/dev/assets-snapshots"


def settled(path):
    for attempt in range(60):
        data = path.read_bytes()
        stamp = path.stat().st_mtime_ns
        if len(data) >= 12 and data[:4] == b"glTF" and struct.unpack_from("<I", data, 8)[0] == len(data):
            time.sleep(0.5)
            if path.stat().st_mtime_ns == stamp:
                return data
        time.sleep(5)
    raise SystemExit(f"{path} never settled")


staging = ROOT / f".staging-{time.time_ns()}"
files = {}
sources = sorted((DATA / "assets/v1/tiles").glob("*/buildings*.glb"))
for source in sources + [p for p in sorted((DATA / "assets/v1/tiles").glob("*/buildings*.json"))]:
    data = settled(source) if source.suffix == ".glb" else source.read_bytes()
    relative = f"tiles/{source.parent.name}/{source.name}"
    (staging / relative).parent.mkdir(parents=True, exist_ok=True)
    (staging / relative).write_bytes(data)
    files[relative] = hashlib.sha256(data).hexdigest()
digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:16]
target = ROOT / digest
if target.exists():
    shutil.rmtree(staging)  # identical snapshot already pinned
else:
    json.dump({"hash": digest, "taken_at": datetime.now(timezone.utc).isoformat(), "source": str(DATA / "assets/v1/tiles"), "files": files},
              open(staging / "snapshot.json", "w"), indent=1)
    staging.rename(target)
print(digest)
