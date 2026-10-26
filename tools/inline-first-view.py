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
columns = range(max(0, int((left - level["left"]) // 512)), min(level["columns"] - 1, int((left + 390 - level["left"]) // 512)) + 1)
rows = range(max(0, int((level["top"] - top) // 512)), min(level["rows"] - 1, int((level["top"] - top + 844) // 512)) + 1)
preloads = "".join(f'<link rel="preload" as="image" href="./{base}/b{bearing}/0/{c}_{r}.webp" media="(max-width: 700px)">\n' for r in rows for c in columns)

# A low-resolution picture of the first view, inside the HTML: on a phone it
# is on screen after one round trip, and the real tiles replace it. It is cut
# from the coarse level (4 art pixels per pixel) around the same centre, so it
# lines up exactly with the tiles that replace it.
import base64, io
from PIL import Image
coarse = meta["levels"][2]
scale = coarse["metres_per_pixel"] / mpp
csx, csy = sx / scale, sy / scale
half_w, half_h = 60, 118  # covers phones up to 480 x 944 CSS pixels
mosaic = Image.new("RGB", (coarse["columns"] * 512, coarse["rows"] * 512), (0xc9, 0xd3, 0xdd))
for r in range(coarse["rows"]):
    for c in range(coarse["columns"]):
        mosaic.paste(Image.open(f"{dist}/{base}/b{bearing}/2/{c}_{r}.webp"), (c * 512, r * 512))
cx, cy = csx - coarse["left"], coarse["top"] - csy
crop = mosaic.crop((round(cx - half_w), round(cy - half_h), round(cx + half_w), round(cy + half_h)))
buffer = io.BytesIO()
crop.save(buffer, "WEBP", quality=45)
placeholder = base64.b64encode(buffer.getvalue()).decode()
first_view = (
    f'<img id="first-view" alt="" src="data:image/webp;base64,{placeholder}" '
    f'style="position:fixed;left:calc(50vw - {half_w * scale}px);top:calc(50vh - {half_h * scale}px);'
    f'width:{2 * half_w * scale}px;height:{2 * half_h * scale}px;image-rendering:pixelated;pointer-events:none">'
    '<script>if (innerWidth < 700 && !location.search) requestAnimationFrame(() => performance.mark("map-first-view")); '
    'else document.getElementById("first-view").remove();</script>'
)
html = html.replace('<div id="map" class="pyramid"></div>', '<div id="map" class="pyramid"></div>\n' + first_view)

inline = f'<script>window.inlinedPyramidMeta = {{"./{base}/b{bearing}": {json.dumps(meta, separators=(",", ":"))}}};</script>\n'
html = html.replace("</head>", preloads + inline + "</head>")
html = re.sub(r'<script type="module" src="\./pyramid\.js"></script>', lambda _: f'<script type="module">{code}</script>', html)
css = open(f"{dist}/miniature/page.css").read()
html = html.replace('<link rel="stylesheet" href="./miniature/page.css">', f"<style>{css}</style>")
open(f"{dist}/{page}", "w").write(html)
print(f"{page}: placeholder {len(placeholder)} chars, preloads {len(list(rows)) * len(list(columns))} tiles, html {len(html)} bytes")
