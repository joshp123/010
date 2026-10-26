#!/usr/bin/env bash
# Written by AI on 2026-10-26 by model Claude Opus 5.5.
# Stitch every elevation whose chunks are all generated, then verify and
# assemble the tile's building assets (Sol's pipeline/assets tools).
set -uo pipefail
tile="${1:?tile}"
data="/Volumes/Josh Extreme Pro USB4 4TB/010"
repo="$data/repo"
n=0
for chunks in "$data/assets/v1/elevations/$tile-elevation-"*/chunks; do
  d="$(dirname "$chunks")"
  missing=0
  for c in "$chunks"/*/; do [ -f "$c/generated-raw.png" ] || missing=1; done
  if [ "$missing" = 0 ] && { [ ! -f "$d/generated-raw.png" ] || [ "$chunks" -nt "$d/generated-raw.png" ] || [ -n "$(find "$chunks" -name generated-raw.png -newer "$d/generated-raw.png")" ]; }; then
    python3 "$repo/tools/chunk-elevations.py" --stitch "$d" && n=$((n+1))
  fi
done
echo "stitched $n elevations"
