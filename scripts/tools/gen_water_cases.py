#!/usr/bin/env python3
"""WT suite (reef dive): environments/threejs/runtime/configs/wt00-clean.json + wtXX-<slug>.json (+ .answers.json).

The reef is a standalone page (environments/threejs/scenes/10_beautiful_water_clean_constrained.html) that
implements the harness `window.__env` contract itself; the bug catalogue lives in
environments/threejs/scenes/src/water/app/bugs.js and the answers are dumped from the page
(`BenchmarkWorld.bug`) so the judge ground truth has a single source.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "environments/threejs/runtime" / "configs"
PAGE = "environments/threejs/scenes/10_beautiful_water_clean_constrained.html"
CASES = [  # id -> slug (config name = wtXX-slug)
    ("wt01", "float"), ("wt02", "clip"), ("wt05", "airwall"),
    ("wt07", "ghostrock"), ("wt08", "jitter"), ("wt09", "magenta"),
    ("wt11", "xray"), ("wt12", "unload"), ("wt14", "lodpop"), ("wt15", "spawnpile"),
    ("wt16", "fishreverse"), ("wt17", "fishupside"),
]
SPAWN = {"pos": [0.0, -4.4, 11.5], "yawDeg": 0}          # sandy lane south of the reef, facing north
TARGETS = {"zone_far": [9.5, -4.0, -8.5]}                  # the north-east ridge (patrol end point, distance only)


def dump_answers():
    """Load the page once per bug and read BenchmarkWorld.bug (name / where / at / category)."""
    from playwright.sync_api import sync_playwright
    args = ["--no-sandbox", "--disable-dev-shm-usage", "--enable-webgl", "--ignore-gpu-blocklist", "--use-angle=gl-egl"]
    out = {}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=args)
        for cid, slug in CASES:
            pg = b.new_page(viewport={"width": 640, "height": 400})
            pg.goto(f"file://{REPO / PAGE}?bug={cid}-{slug}", wait_until="load", timeout=300000)
            for _ in range(80):
                if pg.evaluate("() => window.BenchmarkWorld && window.BenchmarkWorld.ready"):
                    break
                pg.wait_for_timeout(500)
            out[cid] = pg.evaluate("() => window.BenchmarkWorld.bug")
            pg.close()
        b.close()
    return out


def main():
    answers = dump_answers() if "--no-answers" not in sys.argv else {}
    base = {"page": PAGE, "spawn": SPAWN, "targets": TARGETS, "bounds": {"minX": -27, "maxX": 27, "minZ": -27, "maxZ": 27}}
    cfg = dict(base, name="wt00-clean", bug=None, meta={"title": "wt00-clean", "desc": "reef dive, no bug"})
    (OUT / "wt00-clean.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
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
