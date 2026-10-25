# Written by AI on 2026-10-26 by model Claude Opus 5.5.
# Make a pyramid page arrive in as few round trips as possible: inline the
# bundled viewer code and the first bearing's metadata, and preload the tiles
# a phone sees on arrival at the default view.
# Usage: python3 tools/inline-first-view.py DIST PAGE.html BUNDLE.js PYRAMID_BASE BEARING
import json, math, re, sys
dist, page, bundle, base, bearing = sys.argv[1:6]
html = open(f"{dist}/{page}").read()
meta = json.load(open(f"{dist}/{base}/b{bearing}/meta.json"))
code = open(bundle).read()

# Tiles in view for a 390 x 844 phone at the default zoom (level 0, one CSS
# pixel per art pixel) centred on Aelbrechtskolk at street height.
x, y, z = 90341 - meta["origin_rd"][0], 3.0, -(436174 - meta["origin_rd"][1])
b, e = math.radians(meta["bearing"]), math.radians(meta["elevation_degrees"])
right = (math.cos(b), 0, math.sin(b))
up = (math.sin(b) * math.sin(e), math.cos(e), -math.cos(b) * math.sin(e))
level = meta["levels"][0]
mpp = level["metres_per_pixel"]
sx = (right[0] * x + right[2] * z) / mpp
sy = (up[0] * x + up[1] * y + up[2] * z) / mpp
left, top = round(sx - 195), round(sy + 422)
columns = range(max(0, (left - level["left"]) // 512), min(level["columns"] - 1, (left + 390 - level["left"]) // 512) + 1)
rows = range(max(0, (level["top"] - top) // 512), min(level["rows"] - 1, (level["top"] - top + 844) // 512) + 1)
preloads = "".join(f'<link rel="preload" as="image" href="./{base}/b{bearing}/0/{c}_{r}.webp" media="(max-width: 700px)">\n' for r in rows for c in columns)

inline = f'<script>window.inlinedPyramidMeta = {{"./{base}/b{bearing}": {json.dumps(meta, separators=(",", ":"))}}};</script>\n'
html = html.replace("</head>", preloads + inline + "</head>")
html = re.sub(r'<script type="module" src="\./pyramid\.js"></script>', lambda _: f'<script type="module">{code}</script>', html)
css = open(f"{dist}/miniature/page.css").read()
html = html.replace('<link rel="stylesheet" href="./miniature/page.css">', f"<style>{css}</style>")
open(f"{dist}/{page}", "w").write(html)
print(f"{page}: preloads {len(list(rows)) * len(list(columns))} tiles, html {len(html)} bytes")
