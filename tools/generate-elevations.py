# Written by AI on 2026-10-26 by model Claude Opus 5.5.
# Tier-1 façade generation driver (RFC-001 C4): ChatGPT's image tool runs only
# inside Codex, so each Codex run takes a batch of elevation groups and makes
# one image call per group with the shared prompt (pipeline/assets/prompts/
# elevation.md) and the group's rectified 2018 photo as the reference.
# Usage: python3 tools/generate-elevations.py TILE[,TILE...] MIN_M2 RUNS BATCH [--dry-run]
import json, os, subprocess, sys, time
from pathlib import Path

tiles, min_area, runs, batch = sys.argv[1].split(","), float(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
DATA = Path("/Volumes/Josh Extreme Pro USB4 4TB/010")
REPO = DATA / "repo"
CODEX = "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex"
groups = [g for tile in tiles for g in json.load(open(DATA / f"assets/v1/tiles/{tile}/elevations-inventory.json"))["elevations"]]
todo = []
# Work on the 3:2 chunks made by tools/chunk-elevations.py, largest elevations first.
for g in sorted(groups, key=lambda g: -g.get("area_m2", 0)):
    if g.get("area_m2", 0) < min_area or not (Path(g["directory"]) / "chunks").exists():
        continue
    for d in sorted((Path(g["directory"]) / "chunks").iterdir()):
        if (d / "reference.png").exists() and not (d / "generated-raw.png").exists() and not (d / ".claimed").exists():
            todo.append(str(d))
print(f"{len(todo)} groups to generate")
if "--dry-run" in sys.argv:
    sys.exit()
prompt_file = REPO / "pipeline/assets/prompts/elevation.md"
work = DATA / "builds/briefs/tier1"
work.mkdir(parents=True, exist_ok=True)
chunks = [todo[i:i + batch] for i in range(0, len(todo), batch)]
active = []
started = time.time()
while chunks or active:
    while chunks and len(active) < runs:
        items = chunks.pop(0)
        for d in items:
            (Path(d) / ".claimed").touch()  # another driver must not take it
        n = len(list(work.glob("run-*.md")))
        brief = work / f"run-{n:03d}.md"
        brief.write_text(f"""Task: 010 Rotterdam: façade images, batch {n}

For each directory below, in order, make ONE call to your built-in image generation tool:
- reference image: `<directory>/reference.png` (a straight-on rectified photo of real Rotterdam façades);
- prompt: the full text of `{prompt_file}` (read it once; use it unchanged).
Then copy the generated image, unmodified, to `<directory>/generated-raw.png`, and write `<directory>/generation.json` with: tool ("image_gen.imagegen"), started_at and ended_at (ISO UTC, around the call), prompt_source and prompt_sha256 (of the prompt file), reference and reference_sha256, output_raw, call_count 1, model null, written_by "AI, GPT-6.1 Sol via Claude's driver, <date>".
If the tool reports a rate limit, wait 60 seconds and try that item once more; if it fails again, write `<directory>/generation-error.txt` with the exact message and continue.
Do nothing else: no other files, no verification, no edits to the repository.

Directories:
""" + "\n".join(f"- {d}" for d in items) + "\n\nReply with one line per directory: ok or the error.\n")
        log = open(work / f"run-{n:03d}.jsonl", "w")
        proc = subprocess.Popen([CODEX, "exec", "--json", "--skip-git-repo-check", "-C", str(DATA / "assets/v1"), "-m", "gpt-6.1-sol",
                                 "-c", 'model_reasoning_effort="low"', "-o", str(work / f"run-{n:03d}-last.md"), "-"],
                                stdin=open(brief), stdout=log, stderr=subprocess.STDOUT)
        active.append((proc, n, items, time.time()))
    time.sleep(10)
    for entry in list(active):
        proc, n, items, t0 = entry
        if proc.poll() is not None:
            done = sum((Path(d) / "generated-raw.png").exists() for d in items)
            limited = (work / f"run-{n:03d}.jsonl").read_text().count("rate limit") + (work / f"run-{n:03d}.jsonl").read_text().count("429")
            print(f"run {n}: {done}/{len(items)} images in {time.time() - t0:.0f}s, rate-limit mentions {limited}, elapsed {time.time() - started:.0f}s", flush=True)
            active.remove(entry)
