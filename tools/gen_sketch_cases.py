#!/usr/bin/env python3
"""AF suite (Sketchbook airfield): env/configs/af00-clean.json + afXX-<slug>.json (+ .answers.json).

The airfield is a standalone page (candidate_environments/03_sketchbook_airfield_constrained.html) that implements
the harness `window.__env` contract itself (src/common/harness_page.js); the bug catalogue lives in
src/sketch/bugs.js and the answers are dumped from the page (`BenchmarkWorld.bug`).
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "env" / "configs"
PAGE = "candidate_environments/03_sketchbook_airfield_constrained.html"
CASES = [
    ("af01", "float"), ("af02", "clip"), ("af03", "scale"), ("af04", "doublespawn"), ("af05", "airwall"),
    ("af06", "hole"), ("af07", "ghost"), ("af08", "jitter"), ("af09", "magenta"), ("af10", "backcull"),
    ("af11", "xray"), ("af12", "unload"), ("af13", "statereset"), ("af14", "lodpop"), ("af15", "spawnpile"),
    ("af16", "misrotated"), ("af17", "noshadow"), ("af18", "pushcar"),
]
SPAWN = {"pos": [0.0, 15.4, -14.0], "yawDeg": 0}           # open tarmac north of the stone gate, facing north (yaw 0 = -z)
TARGETS = {"zone_far": [0.0, 14.8, -33.0]}                  # just past the invisible-wall line, north end of the audit area
# audit area: the carriers span x -15..16, z -30..34 (barrier rows, prop clusters, the hole) plus a 4-6 m margin
BOUNDS = {"minX": -20, "maxX": 20, "minZ": -36, "maxZ": 38}


def dump_answers():
    from playwright.sync_api import sync_playwright
    args = ["--no-sandbox", "--disable-dev-shm-usage", "--enable-webgl", "--ignore-gpu-blocklist", "--use-angle=gl-egl"]
    out = {}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=args)
        for cid, slug in CASES:
            pg = b.new_page(viewport={"width": 640, "height": 400})
            pg.goto(f"file://{REPO / PAGE}?bug={cid}-{slug}&benchmark=1", wait_until="load", timeout=300000)
            for _ in range(200):
                if pg.evaluate("() => !!(window.BenchmarkWorld && window.BenchmarkWorld.ready)"):
                    break
                pg.wait_for_timeout(500)
            out[cid] = pg.evaluate("() => window.BenchmarkWorld.bug")
            pg.close()
        b.close()
    return out


def main():
    answers = dump_answers() if "--no-answers" not in sys.argv else {}
    base = {"page": PAGE, "spawn": SPAWN, "targets": TARGETS, "bounds": BOUNDS}
    cfg = dict(base, name="af00-clean", bug=None, meta={"title": "af00-clean", "desc": "airfield, no bug"})
    (OUT / "af00-clean.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
    for cid, slug in CASES:
        name = f"{cid}-{slug}"
        ans = answers.get(cid)
        cfg = dict(base, name=name, bug=name, meta={"title": name, "desc": ans["where"] if ans else name})
        (OUT / f"{name}.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
        if ans:
            a = [{"name": ans["name"], "where": ans["where"], "at": [round(v, 2) for v in ans["at"]], "category": ans["category"]}]
            if ans.get("global"):
                a[0]["global"] = True
            for k in ("extent_x", "extent_z"):   # extent-aware aux loc-err for wide carriers
                if k in ans:
                    a[0][k] = ans[k]
            (OUT / f"{name}.answers.json").write_text(json.dumps(a, ensure_ascii=False, indent=1))
        print("wrote", name, "-", ans["name"] if ans else "(no answer)")


if __name__ == "__main__":
    main()
