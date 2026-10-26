# Written by AI on 2026-10-26 by model Claude Opus 5.5.
# The numbers Josh asks first, for one tile's building assets: how much wall
# and roof area is checked against a photo versus interpreted, and what the
# assets cost in image calls and time per building.
# Usage: python3 tools/tile-numbers.py TILE   (prints JSON)
import glob, json, sys
from pathlib import Path

DATA = Path("/Volumes/Josh Extreme Pro USB4 4TB/010")


def tile_numbers(tile):
    assembly = json.load(open(DATA / f"assets/v1/tiles/{tile}/buildings.assembly.json"))
    buildings = len(json.load(open(DATA / f"assets/v1/tiles/{tile}/buildings.feature-provenance.json")).get("features", [])) or None
    walls, roofs = assembly["wall_area_fractions"], assembly["building_roof_area_fractions"]
    wall_calls = len(glob.glob(str(DATA / f"assets/v1/elevations/{tile}-elevation-*/chunks/*/generated-raw.png")))
    roof_calls = len(glob.glob(str(DATA / f"assets/v1/roofs/{tile}/*/generated-raw.png")))
    calls = wall_calls + roof_calls
    rate = json.load(open(DATA / "assets/v1/rate-test.json")) if (DATA / "assets/v1/rate-test.json").exists() else None
    numbers = {
        "tile": tile,
        "walls": {"area_m2": round(walls["area_m2"]), "photo_verified": round(walls["verified"], 4), "interpreted": round(walls["interpreted"], 4),
                  # How each wall was made: redrawn from its photo, composed from
                  # parts with measured colour and openings, or plain material.
                  "share_by_route": {route: round(area / walls["area_m2"], 4) for route, area in assembly["wall_route_areas_m2"].items()}},
        "roofs": {"area_m2": round(roofs["area_m2"]), "photo_verified": round(roofs["verified"], 4), "interpreted": round(roofs["interpreted"], 4)},
        "buildings": buildings,
        "image_calls": {"walls": wall_calls, "roofs": roof_calls, "per_building": round(calls / buildings, 2) if buildings else None},
    }
    if rate and buildings:
        seconds_per_call = 3600 / rate["calls_per_hour"]
        numbers["seconds_per_building_at_measured_rate"] = round(calls / buildings * seconds_per_call, 1)
        numbers["measured_rate"] = rate
    return numbers


if __name__ == "__main__":
    print(json.dumps(tile_numbers(sys.argv[1]), indent=1))
