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
parser.add_argument("--depth", action="store_true", help="also write depth tiles for live layers (levels 0 and 1)")
parser.add_argument("--render-levels", type=int, default=len(LEVELS), help="render this many finest levels; coarser ones are downsampled 2x from the level below (much faster for large areas)")
args = parser.parse_args()

def open_page(p):
    browser = p.chromium.launch(args=["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"])
    page = browser.new_page(viewport={"width": 800, "height": 800})
    page.on("pageerror", lambda e: print("pageerror:", e))
    page.set_default_timeout(180000)
    page.goto(args.url)
    page.wait_for_function("window.captureReady === true", timeout=600000)
    return browser, page


def capture(page, left, top, size, bearing, mpp, depth=False):
    data = page.evaluate(f"window.renderWindow({left}, {top}, {size}, {size}, {bearing}, {mpp}, false, {'true' if depth else 'false'})")
    return Image.open(io.BytesIO(base64.b64decode(data.split(",", 1)[1]))).convert("RGB")


with sync_playwright() as p:
    for bearing in args.bearings:
        folder = os.path.join(args.out, f"b{int(bearing)}")
        if os.path.exists(os.path.join(folder, "meta.json")):
            print(f"bearing {bearing}: already complete")
            continue
        # A fresh browser per bearing keeps memory bounded; it is also
        # restarted if it crashes, and tiles already written are kept.
        browser, page = open_page(p)
        camera = page.evaluate("({origin: window.miniature.origin, elevation: window.miniature.style.elevationDegrees})")
        # Everything a viewer needs to map RD coordinates to pyramid pixels:
        # screen x = (p . right) / mpp, screen y (up) = (p . up) / mpp, where p is
        # (RD x - origin x, NAP z, -(RD y - origin y)) and right/up follow from
        # the bearing and camera elevation (web/miniature/renderer.js, screenAxes).
        meta = {"tile": TILE, "bearing": bearing, "origin_rd": [camera["origin"]["x"], camera["origin"]["y"]],
                "elevation_degrees": camera["elevation"], "levels": []}
        started = time.time()
        count = 0
        for level, mpp in enumerate(LEVELS):
            if level >= args.render_levels:
                # Coarse levels: each tile is four tiles of the level below,
                # halved. Same grid, origin halved.
                below = meta["levels"][level - 1]
                columns, rows = -(-below["columns"] // 2), -(-below["rows"] // 2)
                meta["levels"].append({"level": level, "metres_per_pixel": mpp, "left": below["left"] / 2, "top": below["top"] / 2, "columns": columns, "rows": rows})
                os.makedirs(os.path.join(folder, str(level)), exist_ok=True)
                for row in range(rows):
                    for column in range(columns):
                        mosaic = Image.new("RGB", (2 * TILE, 2 * TILE), (0xc9, 0xd3, 0xdd))
                        for dy in (0, 1):
                            for dx in (0, 1):
                                source = os.path.join(folder, str(level - 1), f"{2 * column + dx}_{2 * row + dy}.webp")
                                if os.path.exists(source):
                                    mosaic.paste(Image.open(source).convert("RGB"), (dx * TILE, dy * TILE))
                        mosaic.resize((TILE, TILE), Image.BOX).save(os.path.join(folder, str(level), f"{column}_{row}.webp"), quality=args.quality, method=6)
                continue
            bounds = page.evaluate(f"window.screenBounds({bearing}, {mpp})")
            columns = -(-(bounds["right"] - bounds["left"]) // TILE)
            rows = -(-(bounds["top"] - bounds["bottom"]) // TILE)
            meta["levels"].append({"level": level, "metres_per_pixel": mpp, "left": bounds["left"], "top": bounds["top"], "columns": columns, "rows": rows})
            os.makedirs(os.path.join(folder, str(level)), exist_ok=True)
            for row in range(rows):
                for column in range(columns):
                    path = os.path.join(folder, str(level), f"{column}_{row}.webp")
                    depth_path = os.path.join(folder, f"d{level}", f"{column}_{row}.png")
                    want_depth = args.depth and level <= 1
                    if os.path.exists(path) and (not want_depth or os.path.exists(depth_path)):
                        continue
                    left = bounds["left"] + column * TILE - MARGIN
                    top = bounds["top"] - row * TILE + MARGIN
                    size = TILE + 2 * MARGIN
                    for attempt in range(3):
                        try:
                            image = capture(page, left, top, size, bearing, mpp)
                            depth = capture(page, left, top, size, bearing, mpp, True) if want_depth else None
                            break
                        except Exception as error:
                            print(f"restarting browser after: {str(error)[:120]}")
                            try:
                                browser.close()
                            except Exception:
                                pass
                            browser, page = open_page(p)
                    else:
                        raise SystemExit(f"tile {level}/{column}_{row} failed three times")
                    image.crop((MARGIN, MARGIN, MARGIN + TILE, MARGIN + TILE)).save(path, quality=args.quality, method=6)
                    if depth is not None:
                        # Depth for live layers, at half resolution: enough to
                        # hide a vehicle behind a building at pixel-art scale.
                        os.makedirs(os.path.dirname(depth_path), exist_ok=True)
                        depth.crop((MARGIN, MARGIN, MARGIN + TILE, MARGIN + TILE)).resize((TILE // 2, TILE // 2), Image.NEAREST).save(depth_path, optimize=True)
                    count += 1
        with open(os.path.join(folder, "meta.json"), "w") as f:
            json.dump(meta, f, indent=1)
        print(f"bearing {bearing}: {count} tiles in {time.time() - started:.1f}s", flush=True)
        browser.close()
