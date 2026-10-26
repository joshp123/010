# Written by AI on 2026-10-27 by model Claude Opus 5.5.
# Bike racks and lockers from Rotterdam's street-furniture register
# (sources/rotterdam-bike-parking) into scene/v1/tiles/<tile>/bikes.json:
# position, hoop count and places per rack, with the street direction (a row
# of hoops runs along the street; points carry no rotation). How many bikes
# stand in them is not recorded: the renderer fills them as an interpretation.
# Usage: python3 tools/build-bike-parking.py TILE [TILE ...]
import glob, json, sys
from pathlib import Path
from road_direction import RoadDirections

DATA = Path("/Volumes/Josh Extreme Pro USB4 4TB/010")
SOURCE = sorted(glob.glob(str(DATA / "sources/rotterdam-bike-parking/*/")))[-1]
features = {}
for path in glob.glob(f"{SOURCE}/*.json"):
    if path.endswith("manifest.json"):
        continue
    for f in json.load(open(path)).get("features") or []:
        features[(Path(path).name.split("_")[0], f["attributes"]["ID"])] = f
roads = RoadDirections()
for tile in sys.argv[1:]:
    x0, y0 = (int(v) for v in tile[1:].split("_y"))
    racks, lockers = [], []
    for (layer, _), f in features.items():
        g = f.get("geometry") or {}
        if "x" not in g or not (x0 <= g["x"] < x0 + 250 and y0 <= g["y"] < y0 + 250):
            continue
        direction = roads.at(g["x"], g["y"], reach=30) or (1.0, 0.0)
        a = f["attributes"]
        if layer == "FietsTrommel":
            lockers.append({"x": g["x"], "y": g["y"], "along": direction})
        else:
            racks.append({"x": g["x"], "y": g["y"], "along": direction, "type": a.get("TYPE"),
                          "hoops": int(a.get("GETAL1") or 1), "places": int(a.get("GETAL2") or 2)})
    json.dump({"source": SOURCE, "racks": racks, "lockers": lockers}, open(DATA / f"scene/v1/tiles/{tile}/bikes.json", "w"), indent=1)
    print(f"{tile}: {len(racks)} racks ({sum(r['places'] for r in racks)} places), {len(lockers)} lockers")
