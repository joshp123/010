# Written by AI on 2026-10-26 by model Claude Opus 5.5.
# Track centrelines per scene tile from the archived BGT `spoor` features
# (one feature per track; function tram, trein, sneltram, metro), clipped to
# each 250 m tile with a 2 m margin. The renderer turns them into two rails
# at standard gauge and, on ballast beds, sleepers. Only tracks at ground
# level (relatieve_hoogteligging 0) are included; viaducts and tunnels are
# drawn by their structures.
# Usage: python3 tools/build-rails.py
import glob, json
from pathlib import Path
from shapely.geometry import shape, box, mapping

DATA = Path("/Volumes/Josh Extreme Pro USB4 4TB/010")
features, seen = [], set()
for f in sorted(glob.glob(str(DATA / "sources/bgt/*/spoor/*.json"))):
    for feature in json.load(open(f))["features"]:
        p = feature["properties"]
        if p["lokaal_id"] in seen or p.get("eind_registratie"):
            continue
        seen.add(p["lokaal_id"])
        if p.get("relatieve_hoogteligging", 0) not in (0, None) or p.get("functie") not in ("tram", "trein", "sneltram", "metro"):
            continue
        features.append((shape(feature["geometry"]), p["functie"], p["lokaal_id"]))
tiles = sorted(d.name for d in (DATA / "scene/v1/tiles").iterdir() if d.is_dir())
written = 0
for name in tiles:
    x, y = (int(v[1:]) for v in name.split("_"))
    area = box(x - 2, y - 2, x + 252, y + 252)
    tracks = []
    for geometry, function, identity in features:
        if not geometry.intersects(area):
            continue
        clipped = geometry.intersection(area)
        parts = getattr(clipped, "geoms", [clipped])
        for part in parts:
            if part.geom_type == "LineString" and part.length > 0.5:
                tracks.append({"function": function, "id": identity, "points": [[round(px, 2), round(py, 2)] for px, py in part.coords]})
    if tracks:
        json.dump({"source": "BGT spoor, archived in sources/bgt/*/spoor (PDOK, CC0)", "tracks": tracks}, open(DATA / "scene/v1/tiles" / name / "rails.json", "w"))
        written += 1
print(f"{len(features)} ground-level tracks; rails.json written for {written} tiles")
