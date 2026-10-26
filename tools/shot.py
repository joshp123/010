# Written by AI on 2026-10-25 by model Claude Opus 5.5.
# Screenshot a page the way a person would see it: open it at a phone or
# desktop size, wait until the map says it is ready, save a PNG.
# Usage: python3 tools/shot.py URL OUT.png [WIDTH HEIGHT [DPR]]
import sys, time
from playwright.sync_api import sync_playwright

url, out = sys.argv[1], sys.argv[2]
width, height = (int(sys.argv[3]), int(sys.argv[4])) if len(sys.argv) > 4 else (390, 844)
dpr = float(sys.argv[5]) if len(sys.argv) > 5 else 3
with sync_playwright() as p:
    browser = p.chromium.launch(args=["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"])
    page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=dpr)
    page.on("console", lambda m: print("console:", m.type, m.text) if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: print("pageerror:", e))
    started = time.time()
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_function("window.mapReady === true || window.captureReady === true", timeout=120000)
    print(f"ready after {time.time() - started:.2f}s")
    page.screenshot(path=out)
    browser.close()
