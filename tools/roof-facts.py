# Written by AI on 2026-10-26 by model Claude Opus 5.5.
# Roof facts per building, from the 2026 aerial (RFC-001: the photo decides
# each roof's material and colour; the renderer draws it).
#
# The aerial is not a true orthophoto: a roof appears shifted from its
# footprint by an amount proportional to its height (building lean), so
# sampling it at the footprint picks up walls and street. This tool finds the
# lean per tile (roof outlines line up with strong edges in the photo when
# shifted by height x k), then per building fine-tunes the shift, samples the
# roof's colour away from edges and registered tree crowns, and names its
# material from slope and colour. Output: scene/v1/tiles/<tile>/roofs.json.
# Usage: python3 tools/roof-facts.py TILE [TILE ...]
import json, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline/buildings"))
from build import accessor, unpack_glb  # noqa: E402

DATA = Path("/Volumes/Josh Extreme Pro USB4 4TB/010")
PX = 10  # aerial pixels per metre
MATERIALS = {"pantiles": 1, "slate": 2, "tiles": 3, "bitumen": 4, "gravel": 5, "membrane": 6, "light membrane": 7, "sedum": 8}


def lab(rgb):
    c = rgb / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    xyz = c @ np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]]).T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def roof_raster(tile):
    """Per aerial pixel: which building's roof is there (index + 1), and whether it is flat."""
    document, binary = unpack_glb((DATA / f"scene/v1/tiles/{tile}/buildings.glb").read_bytes())
    features = document["extras"]["features"]
    triangles = []
    for primitive in document["meshes"][0]["primitives"]:
        local = accessor(document, binary, primitive["attributes"]["POSITION"]).reshape(-1, 3, 3).astype(float)
        ids = accessor(document, binary, primitive["attributes"]["_FEATURE_ID_0"]).reshape(-1, 3)[:, 0].astype(int)
        cross = np.cross(local[:, 1] - local[:, 0], local[:, 2] - local[:, 0])
        length = np.linalg.norm(cross, axis=1)
        normal_up = np.abs(cross[:, 1]) / np.maximum(length, 1e-12)
        for k in np.flatnonzero((normal_up > 0.55) & (length > 1e-4)):
            if features[ids[k]].get("kind") == "building":
                triangles.append((local[k, :, 1].mean(), ids[k], normal_up[k], local[k], length[k] / 2))
    triangles.sort(key=lambda t: t[0])  # higher roofs drawn last, so they win
    label = Image.new("I", (250 * PX, 250 * PX), 0)
    flat = Image.new("L", (250 * PX, 250 * PX), 0)
    draw_label, draw_flat = ImageDraw.Draw(label), ImageDraw.Draw(flat)
    roof = {}
    for height, index, up, points, area in triangles:
        polygon = [(x * PX, (250 + z) * PX) for x, _, z in points]
        draw_label.polygon(polygon, fill=int(index) + 1)
        draw_flat.polygon(polygon, fill=255 if up > 0.97 else 1)
        entry = roof.setdefault(int(index), {"top": -1e9, "area": 0.0, "flat_area": 0.0})
        entry["top"] = max(entry["top"], points[:, 1].max())
        entry["area"] += area
        entry["flat_area"] += area if up > 0.97 else 0.0
    return np.asarray(label), np.asarray(flat) == 255, roof, features


def tree_mask(tile, shape):
    x0, y0 = (int(v) for v in tile[1:].split("_y"))
    mask = Image.new("L", (shape[1], shape[0]), 0)
    draw = ImageDraw.Draw(mask)
    for dx in (-250, 0, 250):
        for dy in (-250, 0, 250):
            path = DATA / f"scene/v1/tiles/x{x0 + dx}_y{y0 + dy}/objects.json"
            if not path.exists():
                continue
            for tree in json.load(open(path)).get("trees", []):
                r = max(1.5, (tree.get("crown_m") or 0) / 2 + 0.5) * PX
                cx, cy = (tree["x"] - x0) * PX, (y0 + 250 - tree["y"]) * PX
                draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=1)
    return np.asarray(mask) > 0


def facts(tile):
    label, flat, roofs, features = roof_raster(tile)
    photo = np.asarray(Image.open(DATA / f"scene/v1/tiles/{tile}/ortho.jpg").convert("RGB")).astype(float)
    luma = photo @ np.array([0.299, 0.587, 0.114])
    edges = np.hypot(ndimage.sobel(luma, 0), ndimage.sobel(luma, 1))
    trees = tree_mask(tile, label.shape)
    ground = {}  # building base height per feature, from its lowest vertex is not stored; use height_m
    objects = ndimage.find_objects(label)

    def edge_score(index, dx, dy):
        sl = objects[index]
        mask = label[sl] == index + 1
        rim = mask & ~ndimage.binary_erosion(mask)
        ys, xs = np.nonzero(rim)
        ys, xs = ys + sl[0].start + dy, xs + sl[1].start + dx
        ok = (ys >= 0) & (xs >= 0) & (ys < label.shape[0]) & (xs < label.shape[1])
        return edges[ys[ok], xs[ok]].mean() if ok.sum() > 20 else 0.0

    # Lean per metre of height for this tile: the shift that best lines up the
    # outlines of the larger roofs, as a multiple of each roof's height.
    candidates = [i for i, r in roofs.items() if r["area"] > 40 and objects[i] is not None and features[i].get("height_m")]
    best = (0.0, 0.0, -1.0)
    for kx in np.arange(-0.25, 0.2501, 0.025):
        for ky in np.arange(-0.25, 0.2501, 0.025):
            score = np.mean([edge_score(i, int(round(kx * features[i]["height_m"] * PX)), int(round(ky * features[i]["height_m"] * PX))) for i in candidates[:80]]) if candidates else 0
            if score > best[2]:
                best = (kx, ky, score)
    kx, ky = best[0], best[1]
    out = {}
    for index, roof in roofs.items():
        if objects[index] is None:
            continue
        height = features[index].get("height_m") or 0
        dx, dy = int(round(kx * height * PX)), int(round(ky * height * PX))
        if roof["area"] > 15:
            # The aerial is a mosaic, so lean varies: search up to a quarter of
            # the roof's height around the tile's lean, coarse then fine.
            reach = max(10, int(0.25 * height * PX))
            dx, dy = max(((dx + a, dy + b) for a in range(-reach, reach + 1, 3) for b in range(-reach, reach + 1, 3)), key=lambda s: edge_score(index, *s))
            dx, dy = max(((dx + a, dy + b) for a in range(-2, 3) for b in range(-2, 3)), key=lambda s: edge_score(index, *s))
        sl = objects[index]
        mask = ndimage.binary_erosion(label[sl] == index + 1, iterations=3)
        ys, xs = np.nonzero(mask)
        ys, xs = ys + sl[0].start, xs + sl[1].start
        flat_here = flat[ys, xs]
        ys, xs = ys + dy, xs + dx
        ok = (ys >= 0) & (xs >= 0) & (ys < label.shape[0]) & (xs < label.shape[1])
        ys, xs = ys[ok], xs[ok]
        clear = ~trees[ys, xs]
        if clear.sum() < 30:
            out[index] = {"material": None, "evidence_pixels": int(clear.sum()), "reason": "roof hidden by trees or outside the aerial"}
            continue
        pixels = lab(photo[ys[clear], xs[clear]])
        lightness = pixels[:, 0]
        lo, hi = np.percentile(lightness, [25, 85])
        core = pixels[(lightness >= lo) & (lightness <= hi)]  # drop shadows and glints
        L, a, b = np.median(core, axis=0)
        chroma = float(np.hypot(a, b))
        is_flat = roof["flat_area"] > 0.6 * roof["area"]
        if is_flat:
            material = ("sedum" if a < -5 else "bitumen" if L < 38 and chroma < 10 else "light membrane" if L > 72
                        else "gravel" if np.std(lightness) > 9 else "membrane")
        else:
            material = "pantiles" if a > 12 and b > 8 else "slate" if L < 48 and chroma < 10 else "tiles"
        rgb = np.median(photo[ys[clear], xs[clear]][(lightness >= lo) & (lightness <= hi)], axis=0)
        solar = float(np.mean((pixels[:, 2] < -4) & (pixels[:, 0] < 40)))
        out[index] = {"bag_id": features[index].get("bag_id"), "material": material, "flat": bool(is_flat),
                      "colour": [int(v) for v in rgb], "lab": [round(float(v), 1) for v in (L, a, b)],
                      "shift_m": [dx / PX, -dy / PX], "evidence_pixels": int(clear.sum()), "solar_share": round(solar, 3)}
    result = {"written_by": "AI, Claude Opus 5.5 (tools/roof-facts.py), " + datetime.now(timezone.utc).date().isoformat(),
              "method": "roof outlines from the scene mesh; lean = height x k fitted to aerial edges, refined per roof; median colour of the inner roof away from registered tree crowns; material from slope and colour",
              "source": str(DATA / f"scene/v1/tiles/{tile}/ortho.jpg"), "lean_per_metre": [round(kx, 3), round(-ky, 3)],
              "material_codes": MATERIALS, "roofs": {str(k): v for k, v in sorted(out.items())}}
    json.dump(result, open(DATA / f"scene/v1/tiles/{tile}/roofs.json", "w"), indent=1)
    known = [v for v in out.values() if v.get("material")]
    counts = {m: sum(1 for v in known if v["material"] == m) for m in MATERIALS}
    print(f"{tile}: lean {kx:+.3f},{ky:+.3f} m/m; {len(known)}/{len(out)} roofs measured; " + ", ".join(f"{m} {n}" for m, n in counts.items() if n))


for tile in sys.argv[1:]:
    facts(tile)
