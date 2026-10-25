# Written by AI on 2026-10-25 by model Claude Opus 5.5.
# T3: turn painted squares into a pyramid with the same layout as T2.
#
# 1. Blend overlapping painted squares with weights that fall to zero at each
#    square's edge, so joins fade instead of stepping.
# 2. Stamp rails and road markings back on from data (a data-overlay render of
#    the same window), so the painter can never move, drop or invent them.
# 3. Slice level 0 into 512 px tiles and downsample for the coarser levels.
#
# Usage: python3 tools/build-painted-pyramid.py CAPTURE_URL T2_BEARING_DIR SQUARES_DIR OUT_BEARING_DIR
import base64, io, json, os, sys
import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

capture_url, t2_dir, squares_dir, out_dir = sys.argv[1:5]
TILE, SQUARE, MARGIN = 512, 1024, 8
RAIL = np.array([88, 76, 72], float)
MARKING = np.array([242, 240, 230], float)

meta = json.load(open(os.path.join(t2_dir, "meta.json")))
level0 = meta["levels"][0]
width, height = level0["columns"] * TILE, level0["rows"] * TILE

# T2 underneath, for any pixel no painted square covers.
canvas = np.zeros((height, width, 3), float)
for row in range(level0["rows"]):
    for column in range(level0["columns"]):
        path = os.path.join(t2_dir, "0", f"{column}_{row}.webp")
        if os.path.exists(path):
            canvas[row * TILE:(row + 1) * TILE, column * TILE:(column + 1) * TILE] = np.asarray(Image.open(path).convert("RGB"), float)

ramp = 1 - np.abs(np.arange(SQUARE) + 0.5 - SQUARE / 2) / (SQUARE / 2)
weight_square = np.outer(ramp, ramp)[..., None]
accumulated = np.zeros_like(canvas)
weights = np.zeros((height, width, 1))
for name in sorted(os.listdir(squares_dir)):
    if not name.startswith("square_") or not name.endswith(".png"):
        continue
    column, row = map(int, name[len("square_"):-len(".png")].split("_"))
    painted = np.asarray(Image.open(os.path.join(squares_dir, name)).convert("RGB").resize((SQUARE, SQUARE), Image.LANCZOS), float)
    y, x = row * TILE, column * TILE
    h, w = min(SQUARE, height - y), min(SQUARE, width - x)
    accumulated[y:y + h, x:x + w] += painted[:h, :w] * weight_square[:h, :w]
    weights[y:y + h, x:x + w] += weight_square[:h, :w]
# Outside the scene the render is plain background; the painter invents
# water or streets there, so keep the background wherever the render has it.
background = np.all(np.abs(canvas - np.array([0xc9, 0xd3, 0xdd], float)) < 6, axis=-1)
covered = (weights[..., 0] > 1e-3) & ~background
canvas[covered] = accumulated[covered] / weights[covered]

# Data overlay: red = rail, green = road marking (web/miniature/renderer.js).
with sync_playwright() as p:
    browser = p.chromium.launch(args=["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"])
    page = browser.new_page(viewport={"width": 800, "height": 800})
    page.goto(capture_url)
    page.wait_for_function("window.captureReady === true", timeout=600000)
    for row in range(level0["rows"]):
        for column in range(level0["columns"]):
            left = level0["left"] + column * TILE - MARGIN
            top = level0["top"] - row * TILE + MARGIN
            data = page.evaluate(f"window.renderWindow({left}, {top}, {TILE + 2 * MARGIN}, {TILE + 2 * MARGIN}, {meta['bearing']}, {level0['metres_per_pixel']}, true)")
            overlay = np.asarray(Image.open(io.BytesIO(base64.b64decode(data.split(",", 1)[1]))).convert("RGB"))[MARGIN:MARGIN + TILE, MARGIN:MARGIN + TILE]
            block = canvas[row * TILE:(row + 1) * TILE, column * TILE:(column + 1) * TILE]
            block[overlay[..., 0] > 128] = RAIL
            block[(overlay[..., 1] > 128) & (overlay[..., 0] <= 128)] = MARKING
    browser.close()

image = Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8))
out_meta = dict(meta, levels=[], painted=True)
for level in range(len(meta["levels"])):
    info = meta["levels"][level]
    scale = 2 ** level
    level_image = image if level == 0 else image.resize((width // scale, height // scale), Image.LANCZOS)
    columns, rows = -(-level_image.width // TILE), -(-level_image.height // TILE)
    os.makedirs(os.path.join(out_dir, str(level)), exist_ok=True)
    for row in range(rows):
        for column in range(columns):
            tile = Image.new("RGB", (TILE, TILE), (0xc9, 0xd3, 0xdd))
            tile.paste(level_image.crop((column * TILE, row * TILE, (column + 1) * TILE, (row + 1) * TILE)), (0, 0))
            tile.save(os.path.join(out_dir, str(level), f"{column}_{row}.webp"), quality=88, method=6)
    # Downsampled levels keep level 0's origin, at their own scale.
    out_meta["levels"].append({"level": level, "metres_per_pixel": level0["metres_per_pixel"] * scale,
                               "left": level0["left"] / scale, "top": level0["top"] / scale, "columns": columns, "rows": rows})
json.dump(out_meta, open(os.path.join(out_dir, "meta.json"), "w"), indent=1)
image.save(os.path.join(out_dir, "level0-full.webp"), quality=85)
print("done", width, height)
