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
dist="$out/dist"
mkdir -p "$dist"
rsync -a --delete --exclude 'transit-feed.js' --exclude 'vendor' "$repo/web/" "$dist/"
mkdir -p "$dist/scene" "$dist/pyramids"
rsync -a --delete --exclude '*-phone.png' "$data/scene/web-v1/" "$dist/scene/"
# One minified bundle for the live view instead of three.js's unminified modules.
esbuild "$repo/web/t1.js" --bundle --minify --format=esm --target=es2022 \
  --alias:three="$repo/web/vendor/three/build/three.module.js" \
  --alias:three/addons="$repo/web/vendor/three/examples/jsm" \
  --legal-comments=eof --outfile="$dist/t1.js"
perl -0pi -e 's#<script type="importmap">.*?</script>\n##s' "$dist/t1.html"
for name in t2 t3; do
  if [ -d "$data/pyramids/$name-live" ]; then rsync -a --delete "$data/pyramids/$name-live/" "$dist/pyramids/$name/"; fi
done
mkdir -p "$dist/compare"
cp "$data/renders/compare/"t[123].webp "$dist/compare/"
cp "$data/renders/compare/og.jpg" "$dist/og.jpg"
# The home page: viewer code and first metadata inlined, first tiles preloaded.
esbuild "$repo/web/pyramid.js" --bundle --minify --format=esm --target=es2022 --outfile="$out/pyramid.bundle.js" --log-level=warning
python3 "$repo/tools/inline-first-view.py" "$dist" index.html "$out/pyramid.bundle.js" pyramids/t2 35
build_id="$(git -C "$repo" rev-parse --short HEAD)-$(date +%Y%m%d%H%M%S)"
perl -pi -e "s/__BUILD__/$build_id/" "$dist/sw.js"
mkdir -p "$out/.openai"
cat > "$out/.openai/hosting.json" <<'EOF'
{
  "project_id": "appgprj_6adbd00c69208191bb5e4884a7b60303",
  "static": {"directory": "dist"},
  "d1": null,
  "r2": null
}
EOF
echo "files: $(find "$dist" -type f | wc -l)  bytes: $(du -sk "$dist" | cut -f1) KB"
