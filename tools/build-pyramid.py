# Written by AI on 2026-10-25 by model Claude Opus 5.5.
# T2: render the scene offline into an image pyramid with the same renderer
# and shader the live view uses (web/t1.js?capture=1), one pyramid per bearing.
#
# Output: <out>/b<bearing>/meta.json and <out>/b<bearing>/<level>/<col>_<row>.webp
# Level 0 is the finest. Every level is rendered, not downscaled, so each level
# is real pixel art at its own scale.
#
# Usage: python3 tools/build-pyramid.py URL OUT --bearings 0 90 180 270
import argparse, base64, io, json, os, time
from PIL import Image
from playwright.sync_api import sync_playwright

TILE = 512
MARGIN = 8  # outlines look at neighbours; render a border and crop it off
LEVELS = [0.3, 0.6, 1.2, 2.4]

parser = argparse.ArgumentParser()
parser.add_argument("url", help="capture page, e.g. http://127.0.0.1:8790/t1.html?capture=1")
parser.add_argument("out")
parser.add_argument("--bearings", type=float, nargs="+", default=[0])
parser.add_argument("--quality", type=int, default=90)
args = parser.parse_args()

with sync_playwright() as p:
    browser = p.chromium.launch(args=["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"])
    page = browser.new_page(viewport={"width": 800, "height": 800})
    page.on("pageerror", lambda e: print("pageerror:", e))
    page.goto(args.url)
    page.wait_for_function("window.captureReady === true", timeout=600000)
    for bearing in args.bearings:
        folder = os.path.join(args.out, f"b{int(bearing)}")
        meta = {"tile": TILE, "bearing": bearing, "levels": []}
        started = time.time()
        count = 0
        for level, mpp in enumerate(LEVELS):
            bounds = page.evaluate(f"window.screenBounds({bearing}, {mpp})")
            columns = -(-(bounds["right"] - bounds["left"]) // TILE)
            rows = -(-(bounds["top"] - bounds["bottom"]) // TILE)
            meta["levels"].append({"level": level, "metres_per_pixel": mpp, "left": bounds["left"], "top": bounds["top"], "columns": columns, "rows": rows})
            os.makedirs(os.path.join(folder, str(level)), exist_ok=True)
            for row in range(rows):
                for column in range(columns):
                    left = bounds["left"] + column * TILE - MARGIN
                    top = bounds["top"] - row * TILE + MARGIN
                    size = TILE + 2 * MARGIN
                    data = page.evaluate(f"window.renderWindow({left}, {top}, {size}, {size}, {bearing}, {mpp})")
                    image = Image.open(io.BytesIO(base64.b64decode(data.split(",", 1)[1]))).convert("RGB")
                    image = image.crop((MARGIN, MARGIN, MARGIN + TILE, MARGIN + TILE))
                    image.save(os.path.join(folder, str(level), f"{column}_{row}.webp"), quality=args.quality, method=6)
                    count += 1
        with open(os.path.join(folder, "meta.json"), "w") as f:
            json.dump(meta, f, indent=1)
        print(f"bearing {bearing}: {count} tiles in {time.time() - started:.1f}s")
    browser.close()
