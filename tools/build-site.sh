#!/usr/bin/env bash
# Written by AI on 2026-10-25 by model Claude Opus 5.5.
# Assemble the static site for ChatGPT Sites: pages and code from web/, the
# phone-sized scene and the pyramids from the SSD. Generated data never enters
# the GitHub repository; it is copied into the Sites deployment only.
# Usage: tools/build-site.sh OUT_DIR
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
data="/Volumes/Josh Extreme Pro USB4 4TB/010"
out="${1:?output directory}"
dist="$out/dist/client"
mkdir -p "$dist"
# The live-3D comparison page (t1) and its scene stay out of the deployment:
# Sites allows 256 MiB per deployment and the pyramids need it all.
rsync -a --delete --exclude 'transit-feed.js' --exclude 'vendor' --exclude 't1.html' --exclude 't1.js' --exclude 'compare.html' "$repo/web/" "$dist/"
mkdir -p "$dist/pyramids"
# Pyramids without the raw per-tile depth (the site uses the packed dd/).
for name in t2 t2n; do
  if [ -d "$data/pyramids/$name-live" ]; then rsync -a --delete --exclude 'd[0-9]' "$data/pyramids/$name-live/" "$dist/pyramids/$name/"; fi
done
# Angles rendered so far (default all four).
if [ -n "${BEARINGS:-}" ]; then
  for page in index.html t2.html; do perl -pi -e "s#<body>#<body data-bearings=\"$BEARINGS\">#" "$dist/$page"; done
fi
mkdir -p "$dist/networks"
for kind in cars bikes transit; do
  [ -f "$data/scene/v1/networks/$kind.json" ] && cp "$data/scene/v1/networks/$kind.json" "$dist/networks/"
done
cp "$data/renders/compare/og.jpg" "$dist/og.jpg"
# The home page: viewer code and first metadata inlined, first tiles preloaded.
esbuild "$repo/web/pyramid.js" --bundle --minify --format=esm --target=es2022 --outfile="$TMPDIR/010-pyramid.bundle.js" --log-level=warning
python3 "$repo/tools/inline-first-view.py" "$dist" index.html "$TMPDIR/010-pyramid.bundle.js" pyramids/t2 35
python3 "$repo/tools/inline-first-view.py" "$dist" t2.html "$TMPDIR/010-pyramid.bundle.js" pyramids/t2 35
python3 "$repo/tools/pack-tiles.py" "$dist/pyramids"
build_id="$(git -C "$repo" rev-parse --short HEAD)-$(date +%Y%m%d%H%M%S)"
export SITE_BUILD="$build_id"
perl -pi -e "s/__BUILD__/$build_id/" "$dist/sw.js"
node "$repo/worker/build.mjs" "$out"
total=$(du -sk "$out/dist" | cut -f1)
echo "files: $(find "$dist" -type f | wc -l)  bytes: $total KB"
# Sites rejects deployments over 256 MiB.
if [ "$total" -gt 255000 ]; then echo "too large for Sites: $total KB > 255000 KB" >&2; exit 1; fi
