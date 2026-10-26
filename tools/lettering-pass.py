# Written by AI on 2026-10-26 by model Claude Opus 5.5.
# Lettering pass (RFC-001 C3/C4): a model lists every piece of lettering in
# each generated elevation and says whether the same letters are legible in
# the 2018 photo; code then blanks every sign whose text is not backed by the
# photo to a plain board in the sign's own background colour. Invented text
# is the clearest tell of model imagery. Decisions go to lettering.json.
# Usage: python3 tools/lettering-pass.py TILE detect RUNS | apply
import json, subprocess, sys, time
from pathlib import Path
import numpy as np
from PIL import Image

DATA = Path("/Volumes/Josh Extreme Pro USB4 4TB/010")
CODEX = "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex"
tile, mode = sys.argv[1], sys.argv[2]
dirs = sorted(p for p in (DATA / "assets/v1/elevations").glob(f"{tile}-elevation-*") if (p / "generated-raw.png").exists())
dirs += [DATA / "assets/v1/elevations/aelbrechtskolk-quay-first-v1"] if tile == "x90250_y436000" else []

if mode == "detect":
    runs = int(sys.argv[3])
    todo = [d for d in dirs if not (d / "lettering.json").exists()]
    work = DATA / "builds/briefs/lettering"; work.mkdir(parents=True, exist_ok=True)
    chunks = [todo[i:i + 8] for i in range(0, len(todo), 8)]
    active = []
    while chunks or active:
        while chunks and len(active) < runs:
            items = chunks.pop(0); n = len(list(work.glob("run-*.md")))
            brief = work / f"run-{n:03d}.md"
            brief.write_text("""Task: 010 Rotterdam: check lettering on generated façades

For each directory below, look at two images with your image viewer: `generated-raw.png` (a drawn façade made by an image model) and `reference.png` (the real 2018 photo of the same façade, same framing, grey where no photo exists). Find EVERY piece of lettering, logo or number in generated-raw.png (shop signs, fascia boards, house numbers, banners). For each, decide from reference.png whether the same text is actually legible there at the same place.
Write `<directory>/lettering.json` as {"image_size": [w, h] of generated-raw.png, "items": [{"box": [left, top, right, bottom] in generated-raw.png pixels covering the whole sign board, "text": "what the drawing says", "photo_text": "what the photo legibly shows there, or null", "keep": true only if photo_text is legible and matches}]}. Write {"image_size": [...], "items": []} when there is no lettering. Do nothing else.

Directories:
""" + "\n".join(f"- {d}" for d in items) + "\n")
            proc = subprocess.Popen([CODEX, "exec", "--json", "--skip-git-repo-check", "-C", str(DATA / "assets/v1"), "-m", "gpt-6.1-sol",
                                     "-c", 'model_reasoning_effort="low"', "-o", str(work / f"run-{n:03d}-last.md"), "-"],
                                    stdin=open(brief), stdout=open(work / f"run-{n:03d}.jsonl", "w"), stderr=subprocess.STDOUT)
            active.append((proc, items))
        time.sleep(10)
        for entry in list(active):
            if entry[0].poll() is not None:
                active.remove(entry)
                print(f"{sum((d / 'lettering.json').exists() for d in entry[1])}/{len(entry[1])} checked", flush=True)
else:
    kept = blanked = 0
    for d in dirs:
        f = d / "lettering.json"
        if not f.exists():
            continue
        decisions = json.load(open(f))
        if not any(not item.get("keep") for item in decisions.get("items", [])):
            kept += len(decisions.get("items", []))
            continue
        original = d / "generated-raw-before-lettering.png"
        if not original.exists():
            (d / "generated-raw.png").rename(original)
        image = Image.open(original).convert("RGB")
        w, h = decisions.get("image_size") or image.size
        sx, sy = image.width / w, image.height / h
        pixels = np.asarray(image).copy()
        for item in decisions["items"]:
            if item.get("keep"):
                kept += 1; continue
            l, t, r, b = item["box"]
            l, r = max(0, int(l * sx)), min(image.width, int(r * sx) + 1)
            t, b = max(0, int(t * sy)), min(image.height, int(b * sy) + 1)
            if r - l < 2 or b - t < 2:
                continue
            board = pixels[t:b, l:r].reshape(-1, 3)
            # The board's own background: the most common colour bucket in the box.
            buckets = (board // 24).astype(int)
            keys, counts = np.unique(buckets[:, 0] * 10000 + buckets[:, 1] * 100 + buckets[:, 2], return_counts=True)
            top = keys[counts.argmax()]
            mask = buckets[:, 0] * 10000 + buckets[:, 1] * 100 + buckets[:, 2] == top
            pixels[t:b, l:r] = np.median(board[mask], axis=0).astype(np.uint8)
            item["blanked"] = True; blanked += 1
        Image.fromarray(pixels).save(d / "generated-raw.png")
        decisions["applied"] = "unbacked lettering blanked to a plain board by tools/lettering-pass.py"
        json.dump(decisions, open(f, "w"), indent=1)
    print(f"lettering kept {kept}, blanked {blanked}")
