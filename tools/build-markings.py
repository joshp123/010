# Written by AI on 2026-10-26 by model Claude Opus 5.5.
# Road markings from Rotterdam's marking register (sources/rotterdam-markings:
# lines, areas, points), drawn as paint into a 10 cm mask per tile:
# scene/v1/tiles/<tile>/markings.png (255 = paint), and the register's parking
# bays split into car slots in parking.json. The register's type names
# give each line's dash pattern and width (Lengte_1.00-1.00_B10 = 1 m dash,
# 1 m gap, 10 cm wide). Points (zebra stripes, shark teeth, arrows, letters
# such as "3" "0") carry no rotation; they take the direction of the nearest
# road in the OSM graph, and arrows and letters face traffic on the right.
# Paint the register lacks (a painted "30") is added from the aerial.
# The register states no licence (see its manifest): a decision for Josh
# before publication.
# Usage: python3 tools/build-markings.py TILE [TILE ...]
import glob, json, math, re, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from road_direction import RoadDirections

DATA = Path("/Volumes/Josh Extreme Pro USB4 4TB/010")
SOURCE = sorted(glob.glob(str(DATA / "sources/rotterdam-markings/*/")))[-1]
PX = 10

# 5 x 7 block letters, top row first.
FONT = {
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"], "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"], "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"], "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"], "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"], "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"], "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01110", "10001", "10000", "10000", "10000", "10001", "01110"], "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"], "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01111"], "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["01110", "00100", "00100", "00100", "00100", "00100", "01110"], "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"], "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"], "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"], "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"], "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"], "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"], "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"], "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
}


def features(kind):
    out = []
    for path in sorted(glob.glob(f"{SOURCE}/{kind}_*.json")):
        if path.endswith("_ids.json"):
            continue
        out += json.load(open(path)).get("features") or []
    unique = {f["attributes"]["ID"]: f for f in out}
    return list(unique.values())


def load():
    lines, areas, points = features("lines"), features("areas"), features("points")
    return lines, areas, points, RoadDirections()


def draw_tile(tile, lines, areas, points, roads):
    x0, y0 = (int(v) for v in tile[1:].split("_y"))
    image = Image.new("L", (250 * PX, 250 * PX), 0)
    draw = ImageDraw.Draw(image)
    px = lambda x, y: ((x - x0) * PX, (y0 + 250 - y) * PX)
    inside = lambda x, y, m=10: x0 - m <= x <= x0 + 250 + m and y0 - m <= y <= y0 + 250 + m

    def quad(cx, cy, ux, uy, length, width):
        """A painted rectangle centred at (cx, cy), long side along (ux, uy)."""
        vx, vy = -uy, ux
        corners = [(cx + ux * a * length / 2 + vx * b * width / 2, cy + uy * a * length / 2 + vy * b * width / 2) for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        draw.polygon([px(*c) for c in corners], fill=255)

    drawn = {"lines": 0, "areas": 0, "points": 0}
    slots = []  # parking slots from the register's bays, for parked cars
    for f in lines:
        kind = f["attributes"]["TYPE"] or ""
        paths = (f.get("geometry") or {}).get("paths") or []
        if not paths or "Blind" in kind or not any(inside(*p) for path in paths for p in path):
            continue
        width = int(re.search(r"_B(\d+)", kind).group(1)) / 100 if re.search(r"_B(\d+)", kind) else 0.10
        dash = re.search(r"(\d\.\d\d)-(\d\.\d\d)", kind)
        on, off = (float(dash.group(1)), float(dash.group(2))) if dash else (0.5, 0.5) if "Kruisvak" in kind else (None, None)
        for path in paths:
            phase = 0.0
            for (ax, ay), (bx, by) in zip(path, path[1:]):
                length = math.hypot(bx - ax, by - ay)
                if length < 1e-3:
                    continue
                ux, uy = (bx - ax) / length, (by - ay) / length
                if on is None:
                    quad((ax + bx) / 2, (ay + by) / 2, ux, uy, length + width, width)
                    continue
                s = -phase
                while s < length:
                    a, b = max(0.0, s), min(length, s + on)
                    if b > a:
                        quad(ax + ux * (a + b) / 2, ay + uy * (a + b) / 2, ux, uy, b - a, width)
                    s += on + off
                phase = (length + phase) % (on + off)
        drawn["lines"] += 1
    for f in areas:
        kind = f["attributes"]["TYPE"] or ""
        rings = (f.get("geometry") or {}).get("rings") or []
        if not rings or not any(inside(*p) for ring in rings for p in ring):
            continue
        ring = rings[0]
        # Outline 10 cm wide; parking bays also get their dividers.
        for (ax, ay), (bx, by) in zip(ring, ring[1:]):
            length = math.hypot(bx - ax, by - ay)
            if length > 1e-3:
                quad((ax + bx) / 2, (ay + by) / 2, (bx - ax) / length, (by - ay) / length, length + 0.1, 0.1)
        bays = re.search(r"_(\d+)P", kind)
        if bays and kind.startswith("Parkeervak"):
            # Slots for parked cars: the bay's long side split into its count.
            pts_ = np.array(ring[:-1])
            edges_ = [(pts_[i], pts_[(i + 1) % len(pts_)]) for i in range(len(pts_))]
            la, lb = max(edges_, key=lambda e: np.hypot(*(e[1] - e[0])))
            u_ = (lb - la) / np.hypot(*(lb - la)); v_ = np.array([-u_[1], u_[0]])
            al, ac = (pts_ - la) @ u_, (pts_ - la) @ v_
            n_ = int(bays.group(1))
            perpendicular = "haaks" in kind
            for k in range(n_):
                t = al.min() + (al.max() - al.min()) * (k + 0.5) / n_
                centre = la + u_ * t + v_ * (ac.min() + ac.max()) / 2
                if x0 <= centre[0] < x0 + 250 and y0 <= centre[1] < y0 + 250:
                    heading = math.atan2(*(v_[::-1])) if perpendicular else math.atan2(u_[1], u_[0])
                    slots.append({"x": round(float(centre[0]), 2), "y": round(float(centre[1]), 2), "heading": round(heading, 3), "kind": "perpendicular" if perpendicular else "parallel"})
        if bays and int(bays.group(1)) > 1:
            pts = np.array(ring[:-1])
            edges = [(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
            long_a, long_b = max(edges, key=lambda e: np.hypot(*(e[1] - e[0])))
            u = (long_b - long_a) / np.hypot(*(long_b - long_a))
            v = np.array([-u[1], u[0]])
            along, across = (pts - long_a) @ u, (pts - long_a) @ v
            n = int(bays.group(1))
            for k in range(1, n):
                t = along.min() + (along.max() - along.min()) * k / n
                centre = long_a + u * t + v * (across.min() + across.max()) / 2
                quad(*centre, *v, across.max() - across.min(), 0.1)
        if "Verdrijf" in kind:  # hatched area: diagonal stripes 0.3 m wide, 1.2 m apart
            mask = Image.new("L", image.size, 0)
            ImageDraw.Draw(mask).polygon([px(*p) for p in ring], fill=255)
            hatch = Image.new("L", image.size, 0)
            hd = ImageDraw.Draw(hatch)
            for c in range(-2 * 250 * PX, 2 * 250 * PX, 12):
                hd.line([(c, 0), (c + 250 * PX, 250 * PX)], fill=255, width=3)
            image.paste(255, (0, 0), Image.fromarray(np.minimum(np.asarray(mask), np.asarray(hatch))))
        drawn["areas"] += 1
    for f in points:
        kind = f["attributes"]["TYPE"] or ""
        geometry = f.get("geometry") or {}
        if "x" not in geometry or not inside(geometry["x"], geometry["y"], 3):
            continue
        x, y = geometry["x"], geometry["y"]
        road = roads.at(x, y)
        if road is None:
            continue
        ux, uy = road
        vx, vy = -uy, ux
        size = re.search(r"(\d\.\d\d)x(\d\.\d\d)", kind)
        if "Zebrastreep" in kind:
            quad(x, y, ux, uy, int(re.search(r"L(\d+)", kind).group(1)) / 100, 0.5)
        elif "Haaientand" in kind and size:
            base, height = float(size.group(1)), float(size.group(2))
            # The tooth points at the traffic that must give way.
            tip = (x - ux * height / 2, y - uy * height / 2)
            draw.polygon([px(*tip), px(x + ux * height / 2 + vx * base / 2, y + uy * height / 2 + vy * base / 2),
                          px(x + ux * height / 2 - vx * base / 2, y + uy * height / 2 - vy * base / 2)], fill=255)
        elif kind.startswith("Blok") and size:
            quad(x, y, ux, uy, float(size.group(1)), float(size.group(2)))
        elif kind.startswith("Pijl"):
            length = 2.5 if "fiets" in kind else 5.0
            quad(x - ux * length * 0.15, y - uy * length * 0.15, ux, uy, length * 0.7, 0.15 * length / 5 * 2)
            hx, hy = x + ux * length * 0.2, y + uy * length * 0.2
            draw.polygon([px(hx + ux * length * 0.3, hy + uy * length * 0.3), px(hx + vx * length * 0.12, hy + vy * length * 0.12), px(hx - vx * length * 0.12, hy - vy * length * 0.12)], fill=255)
        elif kind.startswith("Tekst_") and kind[6:].upper() in FONT:
            # Letters are long along the road, read by a driver coming towards them.
            glyph, height, width = FONT[kind[6:].upper()], 2.4, 0.9
            for r, row in enumerate(glyph):
                for c, bit in enumerate(row):
                    if bit == "1":
                        along = height / 2 - (r + 0.5) * height / 7
                        side = (c + 0.5) * width / 5 - width / 2
                        quad(x + ux * along - vx * side, y + uy * along - vy * side, ux, uy, height / 7, width / 5)
        elif kind.startswith("Symbool-Fiets"):
            scale = float(re.search(r"(\d\.\d+)", kind).group(1)) / 2
            for wheel in (-0.55, 0.55):
                cx, cy = x + ux * wheel * scale, y + uy * wheel * scale
                r = 0.35 * scale * PX
                draw.ellipse([px(cx, cy)[0] - r, px(cx, cy)[1] - r, px(cx, cy)[0] + r, px(cx, cy)[1] + r], outline=255, width=1)
            quad(x, y, ux, uy, 1.1 * scale, 0.08)
        else:
            continue
        drawn["points"] += 1
    # Paint the register lacks but the aerial shows (painted "30", worn
    # dashes): small bright neutral shapes on road surfaces, brighter than
    # the road around them. Car-sized blobs (white roofs) are left out.
    photo = np.asarray(Image.open(DATA / f"scene/v1/tiles/{tile}/ortho.jpg").convert("RGB")).astype(float)
    classes = np.asarray(Image.open(DATA / f"scene/v1/tiles/{tile}/classes.png").convert("RGB"))[..., 0]
    luma = photo @ np.array([0.299, 0.587, 0.114])
    chroma = photo.max(-1) - photo.min(-1)
    road = classes == 1  # carriageway only: parked cars and cycle-path grit gave false paint
    local = ndimage.median_filter(luma, size=21)
    paint = road & (luma - local > 45) & (chroma < 30) & (luma > 150)
    labels, count = ndimage.label(paint)
    sizes = ndimage.sum(paint, labels, range(1, count + 1))
    keep = np.zeros(count + 1, bool)
    keep[1:] = (sizes >= 10) & (sizes <= 250)  # 0.1 .. 2.5 m²
    found = keep[labels]
    image = Image.fromarray(np.maximum(np.asarray(image), found.astype(np.uint8) * 255))
    image.save(DATA / f"scene/v1/tiles/{tile}/markings.png", optimize=True)
    json.dump({"source": SOURCE, "slots": slots}, open(DATA / f"scene/v1/tiles/{tile}/parking.json", "w"))
    print(f"{tile}: {drawn['lines']} lines, {drawn['areas']} areas, {drawn['points']} points from the register; {int(found.sum())} px of paint from the aerial; {len(slots)} parking slots")


data = load()
for tile in sys.argv[1:]:
    draw_tile(tile, *data)
