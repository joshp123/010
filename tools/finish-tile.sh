#!/usr/bin/env bash
# Written by AI on 2026-10-26 by model Claude Opus 5.5.
# Finish a tile's generated walls, in order: stitch every elevation whose
# chunks are all generated, check its lettering against the photo and blank
# signs the photo does not show, then match each wall's colour to its photo.
# Each step skips work already done, so this can run repeatedly while
# generation continues. Verification and assembly are pipeline/assets.
# Usage: tools/finish-tile.sh TILE [LETTERING_RUNS]
set -uo pipefail
tile="${1:?tile}"
runs="${2:-2}"
data="/Volumes/Josh Extreme Pro USB4 4TB/010"
repo="$data/repo"
n=0
for chunks in "$data/assets/v1/elevations/$tile-elevation-"*/chunks; do
  d="$(dirname "$chunks")"
  missing=0
  for c in "$chunks"/*/; do [ -f "$c/generated-raw.png" ] || missing=1; done
  if [ "$missing" = 0 ] && [ ! -f "$d/generated-raw.png" ]; then
    python3 "$repo/tools/chunk-elevations.py" --stitch "$d" && n=$((n+1))
  fi
done
echo "$tile: stitched $n elevations"
python3 "$repo/tools/lettering-pass.py" "$tile" detect "$runs"
python3 "$repo/tools/lettering-pass.py" "$tile" apply
python3 "$repo/tools/colour-match.py" "$tile"
