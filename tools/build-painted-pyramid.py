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
from skimage.color import rgb2gray
from skimage.filters import sobel
from skimage.registration import phase_cross_correlation
from skimage.transform import AffineTransform, PolynomialTransform, warp

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
# Squared tent: each square dominates near its centre, so where two paints
# differ the blend zone is narrow.
weight_square = (np.outer(ramp, ramp) ** 2)[..., None]


def register(painted, render):
    """The painter sometimes shifts or slightly warps its output. Measure the
    offset of each 128 px block against the render, drop blocks that disagree,
    fit a smooth map, and pull the painting back onto the render.
    Returns (None, reason) if it will not fit."""
    a, b = sobel(rgb2gray(render / 255)), sobel(rgb2gray(painted / 255))
    block = 128
    targets, sources = [], []
    for by in range(0, SQUARE, block):
        for bx in range(0, SQUARE, block):
            ra, rb = a[by:by + block, bx:bx + block], b[by:by + block, bx:bx + block]
            if ra.std() < 0.015 or rb.std() < 0.015:
                continue  # plain background: nothing to match
            shift, _, _ = phase_cross_correlation(ra, rb, upsample_factor=4)
            if np.abs(shift).max() > 40:
                continue
            centre = np.array([bx + block / 2, by + block / 2], float)
            targets.append(centre)
            sources.append(centre - shift[::-1])
    targets, sources = np.array(targets), np.array(sources)
    if len(targets) < 3:
        # Mostly background: judge the city part as a whole, shift only.
        shift, _, _ = phase_cross_correlation(a, b, upsample_factor=4)
        if np.abs(shift).max() > 4:
            return None, "too little structure to match"
        transform = AffineTransform(translation=-shift[::-1])
        return warp(painted / 255, transform, output_shape=(SQUARE, SQUARE), mode="edge") * 255, "ok"
    if len(targets) < 12:
        # Small piece of city at the area edge: allow a plain shift only.
        offsets = sources - targets
        median = np.median(offsets, axis=0)
        if np.abs(offsets - median).max(axis=1).mean() > 3:
            return None, "edge blocks disagree"
        transform = AffineTransform(translation=median)
    else:
        transform = None
        for model in (AffineTransform(), PolynomialTransform()):
            keep = np.ones(len(targets), bool)
            for _ in range(3):
                if model.__class__ is PolynomialTransform:
                    model.estimate(targets[keep], sources[keep], order=2)
                else:
                    model.estimate(targets[keep], sources[keep])
                error = np.linalg.norm(model(targets) - sources, axis=1)
                keep = error < max(3.0, np.median(error) * 3)
            if keep.mean() > 0.7 and np.median(error[keep]) < 2.0:
                transform = model
                break
        if transform is None:
            return None, f"warp too irregular (median error {np.median(error):.1f} px)"
    warped = warp(painted / 255, transform, output_shape=(SQUARE, SQUARE), mode="edge") * 255
    return warped, "ok"


accumulated = np.zeros_like(canvas)
weights = np.zeros((height, width, 1))
for name in sorted(os.listdir(squares_dir)):
    if not name.startswith("square_") or not name.endswith(".png"):
        continue
    column, row = map(int, name[len("square_"):-len(".png")].split("_"))
    painted = np.asarray(Image.open(os.path.join(squares_dir, name)).convert("RGB").resize((SQUARE, SQUARE), Image.LANCZOS), float)
    y, x = row * TILE, column * TILE
    render = canvas[y:y + SQUARE, x:x + SQUARE]
    if render.shape[:2] != (SQUARE, SQUARE):
        continue
    painted, residual = register(painted, render)
    if painted is None:
        print(f"{name}: dropped, could not be aligned with the render ({residual})")
        continue
    h, w = min(SQUARE, height - y), min(SQUARE, width - x)
    accumulated[y:y + h, x:x + w] += painted[:h, :w] * weight_square[:h, :w]
    weights[y:y + h, x:x + w] += weight_square[:h, :w]
# Outside the scene the render is plain background; the painter invents
# water or streets there, so keep the background wherever the render has it.
# The render's background colour went through the palette, so read it from a
# corner of the canvas, which always lies outside the scene.
background_colour = canvas[2, 2].copy()
background = np.all(np.abs(canvas - background_colour) < 10, axis=-1) | np.all(canvas == 0, axis=-1)
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
            # Crop only inside the image: PIL fills anything beyond it with black.
            box = (column * TILE, row * TILE, min((column + 1) * TILE, level_image.width), min((row + 1) * TILE, level_image.height))
            tile.paste(level_image.crop(box), (0, 0))
            tile.save(os.path.join(out_dir, str(level), f"{column}_{row}.webp"), quality=88, method=6)
    # Downsampled levels keep level 0's origin, at their own scale.
    out_meta["levels"].append({"level": level, "metres_per_pixel": level0["metres_per_pixel"] * scale,
                               "left": level0["left"] / scale, "top": level0["top"] / scale, "columns": columns, "rows": rows})
json.dump(out_meta, open(os.path.join(out_dir, "meta.json"), "w"), indent=1)
image.save(os.path.join(out_dir, "level0-full.webp"), quality=85)
print("done", width, height)
