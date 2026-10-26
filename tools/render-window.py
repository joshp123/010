# Written by AI on 2026-10-26 by model Claude Opus 5.5.
# Render one window of the scene at a chosen scale, centred on an RD point,
# with the same renderer the pyramid uses. For judging the look at any zoom.
# Usage: python3 tools/render-window.py OUT.png X Y MPP [BEARING] [SIZE] [EXTRA_QUERY]
import base64, io, sys
from PIL import Image
from playwright.sync_api import sync_playwright

out, x, y, mpp = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
bearing = float(sys.argv[5]) if len(sys.argv) > 5 else 35
size = int(sys.argv[6]) if len(sys.argv) > 6 else 512
extra = sys.argv[7] if len(sys.argv) > 7 else ""
with sync_playwright() as p:
    browser = p.chromium.launch(args=["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"])
    page = browser.new_page(viewport={"width": 800, "height": 800})
    page.on("pageerror", lambda e: print("pageerror:", e))
    page.goto(f"http://127.0.0.1:8790/t1.html?capture=1&area=m1{extra}")
    page.wait_for_function("window.captureReady === true", timeout=600000)
    sx, sy = page.evaluate(f"""() => {{ const m = window.miniature, p = m.worldFromRd({x}, {y}, 3);
      const b = {bearing} * Math.PI / 180, e = m.style.elevationDegrees * Math.PI / 180;
      const right = [Math.cos(b), 0, Math.sin(b)], up = [Math.sin(b) * Math.sin(e), Math.cos(e), -Math.cos(b) * Math.sin(e)];
      return [p.x * right[0] + p.z * right[2], p.x * up[0] + p.y * up[1] + p.z * up[2]]; }}""")
    left, top = round(sx / mpp) - size // 2, round(sy / mpp) + size // 2
    data = page.evaluate(f"window.renderWindow({left}, {top}, {size}, {size}, {bearing}, {mpp})")
    Image.open(io.BytesIO(base64.b64decode(data.split(",", 1)[1]))).save(out)
    browser.close()
