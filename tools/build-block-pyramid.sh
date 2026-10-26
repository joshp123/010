#!/usr/bin/env bash
# Written by AI on 2026-10-26 by model Claude Opus 5.5.
# Picture pyramids for the 1 km² Delfshaven block (area "core"): day with
# depth and night, all six levels from 7.5 cm to 2.4 m, WebP quality 80,
# rendered from a pinned asset snapshot (tools/snapshot-assets.py) whose hash
# is written to each pyramid's snapshot.txt.
# Usage: tools/build-block-pyramid.sh NAME "35 125 215 305"
set -euo pipefail
data="/Volumes/Josh Extreme Pro USB4 4TB/010"; repo="$data/repo"; name="${1:?name}"; bearings="${2:?bearings}"
snapshot="$(python3 "$repo/tools/snapshot-assets.py")"
levels="--levels 0.075 0.15 0.3 0.6 1.2 2.4 --quality 80"
url="http://127.0.0.1:8790/t1.html?capture=1&area=core&assets=./assets-snapshots/$snapshot"
start=$(date +%s)
mkdir -p "$data/pyramids/$name-day" "$data/pyramids/$name-night"
echo "$snapshot" > "$data/pyramids/$name-day/snapshot.txt"; echo "$snapshot" > "$data/pyramids/$name-night/snapshot.txt"
python3 "$repo/tools/build-pyramid.py" "$url" "$data/pyramids/$name-day" --bearings $bearings $levels --depth --depth-mpp 0.3
python3 "$repo/tools/build-pyramid.py" "$url&light=night" "$data/pyramids/$name-night" --bearings $bearings $levels
for b in $bearings; do python3 "$repo/tools/pack-depth.py" "$data/pyramids/$name-day/b$b"; done
echo "snapshot $snapshot; took $(( $(date +%s) - start )) s"
