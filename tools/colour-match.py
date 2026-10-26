# Written by AI on 2026-10-26 by model Claude Opus 5.5.
# The image model redraws walls well but drifts colour (towards saturated red
# brick). This pass keeps its drawing and moves each wall's mean colour back to
# the photo's, in CIELAB: hue and chroma fully, lightness halfway (the photo's
# lightness carries 2018 shade). Only walls with photo evidence are matched.
# Runs after stitching and the lettering pass (walls without settled lettering wait); keeps generated-raw-before-colour.png
# and always starts from it, so a rerun gives the same result.
# Usage: python3 tools/colour-match.py TILE [--report]
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image

DATA = Path("/Volumes/Josh Extreme Pro USB4 4TB/010")
MIN_PHOTO_PIXELS = 400


def to_lab(rgb):
    c = rgb / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    xyz = c @ np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]]).T
    xyz /= np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def from_lab(lab):
    fy = (lab[..., 0] + 16) / 116
    f = np.stack([fy + lab[..., 1] / 500, fy, fy - lab[..., 2] / 200], -1)
    xyz = np.where(f ** 3 > 0.008856, f ** 3, (f - 16 / 116) / 7.787) * np.array([0.95047, 1.0, 1.08883])
    c = xyz @ np.array([[3.2406, -1.5372, -0.4986], [-0.9689, 1.8758, 0.0415], [0.0557, -0.2040, 1.0570]]).T
    c = np.where(c > 0.0031308, 1.055 * np.clip(c, 0, None) ** (1 / 2.4) - 0.055, 12.92 * c)
    return np.clip(c * 255, 0, 255).round().astype(np.uint8)


def match(d, report):
    raw, before = d / "generated-raw.png", d / "generated-raw-before-colour.png"
    source = before if before.exists() else raw
    generated = np.asarray(Image.open(source).convert("RGB")).astype(float)
    reference = np.asarray(Image.open(d / "reference.png").convert("RGB")).astype(float)
    if generated.shape != reference.shape:
        return []
    ids = np.asarray(Image.open(d / "wall-ids.png").convert("RGB")).astype(int)
    key = ids[..., 0] * 65536 + ids[..., 1] * 256 + ids[..., 2]
    photo = np.asarray(Image.open(d / "photo-mask.png").convert("L")) > 127
    generated_lab, reference_lab = to_lab(generated), to_lab(reference)
    out = generated_lab.copy()
    walls = []
    for wall in np.unique(key):
        region = key == wall
        evidence = region & photo
        if wall == 0 or evidence.sum() < MIN_PHOTO_PIXELS:
            continue
        photo_mean, model_mean = reference_lab[evidence].mean(0), generated_lab[evidence].mean(0)
        shift = (photo_mean - model_mean) * np.array([0.5, 1.0, 1.0])
        out[region] += shift
        walls.append({"wall": int(wall), "pixels": int(evidence.sum()),
                      "photo_chroma": float(np.hypot(*photo_mean[1:])), "model_chroma": float(np.hypot(*model_mean[1:])),
                      "mean_difference": float(np.linalg.norm(photo_mean - model_mean)),
                      "lightness_difference": float(model_mean[0] - photo_mean[0]),
                      "colour_difference": float(np.linalg.norm(photo_mean[1:] - model_mean[1:]))})
    if walls and not report:
        if not before.exists():
            Image.open(raw).save(before)
        Image.fromarray(from_lab(out)).save(raw)
    return walls


tile, report = sys.argv[1], "--report" in sys.argv
walls = []
inventory = json.load(open(DATA / f"assets/v1/tiles/{tile}/elevations-inventory.json"))["elevations"]
for d in sorted({Path(g["directory"]) for g in inventory}):
    if not ((d / "generated-raw.png").exists() and (d / "photo-mask.png").exists() and (d / "lettering.json").exists()):
        continue
    lettering = json.load(open(d / "lettering.json"))
    if lettering.get("applied") or all(item.get("keep") for item in lettering.get("items", [])):  # lettering settled first
        walls += match(d, report)
if not walls:
    print(f"{tile}: no walls ready to match")
    sys.exit()
pixels = np.array([w["pixels"] for w in walls], float)
weighted = lambda k: float((np.array([w[k] for w in walls]) * pixels).sum() / pixels.sum())
print(f"{len(walls)} walls: photo chroma {weighted('photo_chroma'):.1f}, model chroma {weighted('model_chroma'):.1f}, "
      f"mean difference {weighted('mean_difference'):.1f} (lightness {weighted('lightness_difference'):+.1f}, hue and chroma {weighted('colour_difference'):.1f}) (CIELAB, weighted by photo pixels)"
      + ("" if report else "; matched"))
