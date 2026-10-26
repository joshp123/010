# Written by AI on 2026-10-26 by model Claude Opus 5.5.
# One candidate picture for judging the look: the test tile at deep zoom and
# at 0.3 m per pixel, beside the 2026 aerial of the same place and tiny.london
# at its closest zoom. Writes renders/candidates/<nn>-<name>.png.
# Usage: python3 tools/candidate.py NN NAME [EXTRA_QUERY]
import base64, io, math, os, sys
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

nn, name = sys.argv[1], sys.argv[2]
extra = sys.argv[3] if len(sys.argv) > 3 else ""
DATA = "/Volumes/Josh Extreme Pro USB4 4TB/010"
X, Y, BEARING = 90330, 436110, 35   # Aelbrechtskolk quay, tile x90250_y436000

def render(page, mpp, size, bearing=BEARING):
    sx, sy = page.evaluate(f"""() => {{ const m = window.miniature, p = m.worldFromRd({X}, {Y}, 3);
      const b = {bearing} * Math.PI / 180, e = m.style.elevationDegrees * Math.PI / 180;
      const right = [Math.cos(b), 0, Math.sin(b)], up = [Math.sin(b) * Math.sin(e), Math.cos(e), -Math.cos(b) * Math.sin(e)];
      return [p.x * right[0] + p.z * right[2], p.x * up[0] + p.y * up[1] + p.z * up[2]]; }}""")
    left, top = round(sx / mpp) - size // 2, round(sy / mpp) + size // 2
    data = page.evaluate(f"window.renderWindow({left}, {top}, {size}, {size}, {bearing}, {mpp})")
    return Image.open(io.BytesIO(base64.b64decode(data.split(",", 1)[1]))).convert("RGB")

def page_for(p, light):
    browser = p.chromium.launch(args=["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"])
    page = browser.new_page(viewport={"width": 1100, "height": 1100})
    page.on("pageerror", lambda e: print("pageerror:", e))
    page.goto(f"http://127.0.0.1:8790/t1.html?capture=1&area=core{light}{extra}")
    page.wait_for_function("window.captureReady === true", timeout=600000)
    return browser, page

with sync_playwright() as p:
    browser, page = page_for(p, "")
    deep = render(page, 0.075, 1024)
    overview = render(page, 0.3, 1024)
    second = render(page, 0.075, 1024, 215)
    browser.close()
    browser, page = page_for(p, "&light=night")
    night = render(page, 0.3, 1024)
    browser.close()

ortho = Image.open(f"{DATA}/scene/v1/tiles/x90250_y436000/ortho.jpg").convert("RGB")
# The same ground as the deep view, top-down, north up (2500 px = 250 m).
ox, oy = (X - 90250) * 10, (436250 - Y) * 10
aerial = ortho.crop((ox - 400, oy - 400, ox + 400, oy + 400)).resize((1024, 1024))
tiny = Image.open(f"{DATA}/renders/reference/tiny-london-day-deep.png").convert("RGB").resize((1024, 1024))
W = 1024 + 20
sheet = Image.new("RGB", (3 * W, 2 * (1024 + 40)), (28, 30, 40))
panels = [(deep, "010, 7.5 cm per pixel, bearing 35"), (overview, "010, 0.3 m per pixel"), (night, "010 at night, 0.3 m per pixel"),
          (second, "010, 7.5 cm per pixel, bearing 215"), (aerial, "2026 aerial, same place, top-down"), (tiny, "tiny.london, closest zoom (0.29 m per pixel)")]
for i, (image, label) in enumerate(panels):
    x, y = (i % 3) * W, (i // 3) * (1024 + 40) + 40
    sheet.paste(image, (x, y))
    ImageDraw.Draw(sheet).text((x + 8, y - 30), label, fill=(244, 241, 230))
os.makedirs(f"{DATA}/renders/candidates", exist_ok=True)
path = f"{DATA}/renders/candidates/{nn}-{name}.png"
sheet.save(path)
print(path)
