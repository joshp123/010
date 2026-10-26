# Written by AI on 2026-10-26 by model Claude Opus 5.5.
# One candidate picture for judging the look: the test tile at deep zoom and
# at 0.3 m per pixel, beside the 2026 aerial of the same place and tiny.london
# at its closest zoom. Writes renders/candidates/<nn>-<name>.png.
# Usage: python3 tools/candidate.py NN NAME [EXTRA_QUERY]
import subprocess, base64, io, math, os, sys
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

nn, name = sys.argv[1], sys.argv[2]
extra = sys.argv[3] if len(sys.argv) > 3 else ""
DATA = "/Volumes/Josh Extreme Pro USB4 4TB/010"
X, Y, BEARING = 90330, 436110, 35   # Aelbrechtskolk quay, tile x90250_y436000

def render(page, mpp, size, bearing=BEARING, classes=False):
    sx, sy = page.evaluate(f"""() => {{ const m = window.miniature, p = m.worldFromRd({X}, {Y}, 3);
      const b = {bearing} * Math.PI / 180, e = m.style.elevationDegrees * Math.PI / 180;
      const right = [Math.cos(b), 0, Math.sin(b)], up = [Math.sin(b) * Math.sin(e), Math.cos(e), -Math.cos(b) * Math.sin(e)];
      return [p.x * right[0] + p.z * right[2], p.x * up[0] + p.y * up[1] + p.z * up[2]]; }}""")
    left, top = round(sx / mpp) - size // 2, round(sy / mpp) + size // 2
    data = page.evaluate(f"window.renderWindow({left}, {top}, {size}, {size}, {bearing}, {mpp}, false, false, {'true' if classes else 'false'})")
    return Image.open(io.BytesIO(base64.b64decode(data.split(",", 1)[1]))).convert("RGB")

if "assets=./assets" in extra:
    # Render from a settled copy: the asset pipeline may be rewriting tiles.
    subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshot-assets.py")], check=True)
    extra = extra.replace("assets=./assets", "assets=./assets-snapshot")


def page_for(p, light):
    browser = p.chromium.launch(args=["--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"])
    page = browser.new_page(viewport={"width": 1100, "height": 1100})
    page.on("pageerror", lambda e: print("pageerror:", e))
    page.on("console", lambda m: print("warning:", m.text) if m.type == "warning" and m.text.startswith("tile ") else None)
    page.goto(f"http://127.0.0.1:8790/t1.html?capture=1&area=core&traffic=1&tram={X},{Y}{light}{extra}")
    page.wait_for_function("window.captureReady === true", timeout=600000)
    return browser, page

with sync_playwright() as p:
    browser, page = page_for(p, "")
    deep = render(page, 0.075, 1024)
    overview = render(page, 0.3, 1024)
    second = render(page, 0.075, 1024, 215)
    deep_classes = render(page, 0.075, 1024, classes=True)
    overview_classes = render(page, 0.3, 1024, classes=True)
    browser.close()
    browser, page = page_for(p, "&light=night")
    night = render(page, 0.3, 1024)
    browser.close()
    provenance = None
    if "assets=" in extra and os.path.exists(f"{DATA}/assets/v1/tiles/x90250_y436000/buildings-provenance.glb"):
        browser, page = page_for(p, "&assetFile=buildings-provenance.glb&provenance=1")
        provenance = render(page, 0.075, 1024)
        browser.close()

ortho = Image.open(f"{DATA}/scene/v1/tiles/x90250_y436000/ortho.jpg").convert("RGB")
# The same ground as the deep view, top-down, north up (2500 px = 250 m).
ox, oy = (X - 90250) * 10, (436250 - Y) * 10
aerial = ortho.crop((ox - 400, oy - 400, ox + 400, oy + 400)).resize((1024, 1024))
tiny = Image.open(f"{DATA}/renders/reference/tiny-london-day-deep.png").convert("RGB").resize((1024, 1024))
W = 1024 + 20
rows = 3 if provenance is not None else 2
sheet = Image.new("RGB", (3 * W, rows * (1024 + 40)), (28, 30, 40))
panels = [(deep, "010, 7.5 cm per pixel, bearing 35"), (overview, "010, 0.3 m per pixel"), (night, "010 at night, 0.3 m per pixel"),
          (second, "010, 7.5 cm per pixel, bearing 215"), (aerial, "2026 aerial, same place, top-down"), (tiny, "tiny.london, closest zoom (0.29 m per pixel)")]
if provenance is not None:
    panels.append((provenance, "010, 7.5 cm, magenta = interpreted (no photo evidence)"))
for i, (image, label) in enumerate(panels):
    x, y = (i % 3) * W, (i // 3) * (1024 + 40) + 40
    sheet.paste(image, (x, y))
    ImageDraw.Draw(sheet).text((x + 8, y - 30), label, fill=(244, 241, 230))
os.makedirs(f"{DATA}/renders/candidates", exist_ok=True)
path = f"{DATA}/renders/candidates/{nn}-{name}.png"
sheet.save(path)
print(path)

# Per-class numbers for this sheet beside tiny.london's (tools/measure-classes.py).
import json, subprocess
here = os.path.dirname(os.path.abspath(__file__))
work = f"{DATA}/renders/candidates/{nn}-{name}"
os.makedirs(work, exist_ok=True)
numbers = {}
for label, image, classes in [("deep", deep, deep_classes), ("overview", overview, overview_classes)]:
    image.save(f"{work}/{label}.png"); classes.save(f"{work}/{label}-classes.png")
    out = subprocess.run([sys.executable, f"{here}/measure-classes.py", f"{work}/{label}.png", "--codes", f"{work}/{label}-classes.png"], capture_output=True, text=True)
    numbers[label] = json.loads(out.stdout)
numbers["tiny.london"] = json.load(open(f"{DATA}/renders/reference/tiny-london-classes.json"))
assembly = f"{DATA}/assets/v1/tiles/x90250_y436000/buildings.assembly.json"
if "assets=" in extra and os.path.exists(assembly):
    out = subprocess.run([sys.executable, f"{here}/tile-numbers.py", "x90250_y436000"], capture_output=True, text=True, check=True)
    numbers["assets"] = json.loads(out.stdout)
    print(json.dumps(numbers["assets"], indent=1))
json.dump(numbers, open(f"{work}/numbers.json", "w"), indent=1)
classes_order = ["roof", "wall", "asphalt", "paving", "grass", "tree", "water"]
print("class      " + "".join(f"{k:>18}" for k in numbers if k != "assets"))
for c in classes_order + ["edge_step", "L_median_all"]:
    row = []
    for k in [k for k in numbers if k != "assets"]:
        v = numbers[k].get(c)
        row.append(f"{'-':>18}" if v is None else (f"{v:>18}" if not isinstance(v, dict) else f"{'L%.2f C%.3f' % (v['L'], v['C']):>18}"))
    print(f"{c:<11}" + "".join(row))
