# Written by AI on 2026-10-26 by model Claude Opus 5.5.
# Vehicle sprite sheets from the 3D vehicle models (web/miniature/vehicles.js),
# drawn by the city renderer: per vehicle kind (and colour variant), per map
# bearing, per pyramid scale, 16 headings in one row. The viewer picks the
# heading nearest the vehicle's direction of travel.
# Output: OUT/<kind><variant>/b<bearing>/<mpp>.png and OUT/sprites.json.
# Usage: python3 tools/build-sprites.py URL OUT
import base64, io, json, math, os, sys
from PIL import Image
from playwright.sync_api import sync_playwright

url, out = sys.argv[1], sys.argv[2]
BEARINGS = [35, 125, 215, 305]
SCALES = [0.075, 0.15, 0.3, 0.6, 1.2]
KINDS = {"tram": 1, "metro": 1, "train": 1, "bus": 1, "car": 6, "bike": 4}
LENGTH = {"tram": 31.5, "metro": 60.4, "train": 61, "bus": 12, "car": 4.4, "bike": 1.8}
HEADINGS = 16
meta = {"headings": HEADINGS, "bearings": BEARINGS, "scales": SCALES, "kinds": KINDS, "cells": {}}
with sync_playwright() as p:
    browser = p.chromium.launch(args=["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"])
    page = browser.new_page(viewport={"width": 1100, "height": 1100})
    page.on("pageerror", lambda e: print("pageerror:", e))
    page.goto(url)
    page.wait_for_function("window.spriteReady === true")
    for kind, variants in KINDS.items():
        for scale in SCALES:
            # Square cell that holds the vehicle at any heading, at least 8 px.
            size = max(8, int(math.ceil((LENGTH[kind] + 3) / scale / 2)) * 2)
            if size > 1000:
                continue
            meta["cells"][f"{kind}/{scale}"] = size
            for variant in range(variants):
                for bearing in BEARINGS:
                    sheet = Image.new("RGBA", (size * HEADINGS, size))
                    for h in range(HEADINGS):
                        data = page.evaluate(f"window.renderSprite('{kind}', {variant}, {bearing}, {scale}, {2 * math.pi * h / HEADINGS}, {size})")
                        sheet.paste(Image.open(io.BytesIO(base64.b64decode(data.split(",", 1)[1]))).convert("RGBA"), (h * size, 0))
                    folder = os.path.join(out, f"{kind}{variant}", f"b{bearing}")
                    os.makedirs(folder, exist_ok=True)
                    sheet.save(os.path.join(folder, f"{scale}.png"), optimize=True)
            print(kind, scale, size, flush=True)
    browser.close()
json.dump(meta, open(os.path.join(out, "sprites.json"), "w"), indent=1)
