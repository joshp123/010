# Written by AI on 2026-10-27 by model Claude Opus 5.5.
# Street lights from Rotterdam's lighting register (sources/rotterdam-lights,
# SB_Infra/LICHTPUNTEN) into scene/v1/tiles/<tile>/lights.json. The 3D lamp
# tileset the scene used before has only lamps on their own masts; the
# register also has lamps on façade brackets and span wires over the street,
# which is how most of the main streets are lit. Mounting height is the
# register's MONTAGEHOOGTE; type is the mast type (empty when there is none).
# Usage: python3 tools/build-lights.py TILE [TILE ...]
import glob, json, sys
from pathlib import Path

DATA = Path("/Volumes/Josh Extreme Pro USB4 4TB/010")
SOURCE = sorted(glob.glob(str(DATA / "sources/rotterdam-lights/*/")))[-1]
features = {}
for path in glob.glob(f"{SOURCE}/lights_*.json"):
    for f in json.load(open(path)).get("features") or []:
        features[f["attributes"]["LICHTPUNT_ID"]] = f
for tile in sys.argv[1:]:
    x0, y0 = (int(v) for v in tile[1:].split("_y"))
    lights = []
    for f in features.values():
        g, a = f.get("geometry") or {}, f["attributes"]
        if "x" not in g or not (x0 <= g["x"] < x0 + 250 and y0 <= g["y"] < y0 + 250):
            continue
        lights.append({"x": round(g["x"], 2), "y": round(g["y"], 2), "height_m": a.get("MONTAGEHOOGTE") or 6.0,
                       "type": a.get("MASTTYPE") or "", "colour": a.get("LICHTBRONKLEUR"), "kind": a.get("LICHTPUNTTYPE")})
    json.dump({"source": SOURCE, "lights": lights}, open(DATA / f"scene/v1/tiles/{tile}/lights.json", "w"))
    print(f"{tile}: {len(lights)} lights, {sum(1 for l in lights if not l['type'])} without a mast")
