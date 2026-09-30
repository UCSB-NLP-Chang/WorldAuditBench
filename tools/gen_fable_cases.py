#!/usr/bin/env python3
"""WL suite (Beyond Fable wilderness): env/configs/wl00-clean.json + wlXX-<slug>.json (+ .answers.json).

Standalone page (candidate_environments/13_beyond_fable_wilderness_constrained.html) with the shared harness contract;
the bug catalogue is src/fable/upstream/src/benchmark/bugs.ts.  The configs fix the world seed (worldSeed 7 - the
carriers are placed for that world); the runner's episode seed does not change the world.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "env" / "configs"
PAGE = "candidate_environments/13_beyond_fable_wilderness_constrained.html"
WORLD_SEED = 7
CASES = [
    ("wl01", "float"), ("wl02", "clip"), ("wl03", "scale"), ("wl05", "airwall"),
    ("wl06", "hole"), ("wl07", "ghost"), ("wl08", "jitter"), ("wl09", "magenta"), ("wl10", "backcull"),
    ("wl11", "xray"), ("wl12", "unload"), ("wl14", "lodpop"), ("wl15", "spawnpile"),
    ("wl16", "terrainhole"), ("wl17", "upsidedown"),
]
SPAWN = {"pos": [0.0, 0.0, 0.0], "yawDeg": 0}      # the world's own spawn for seed 7 (teleport keeps the ground height)
TARGETS = {"zone_far": [0.0, 0.0, -17.0]}          # north end of the audit area (past the air-wall line)
# audit area: the carriers span x -18..23, z -15..9 (boulders, pine, bushes, tree, seam, grass) plus a 5-6 m margin
BOUNDS = {"minX": -24, "maxX": 28, "minZ": -20, "maxZ": 15}
# catalogue viewpoints (tools/env_bug_shots.py): explicit camera spots for the cases whose default 6 m view misses the point
VIEWS = {
    "wl01": {"cam": [-4.0, 0, 9.0]},     # low and 9 m off: the air gap under the boulder
    "wl03": {"cam": [3.5, 0, -3.5]},     # from outside the tile: giant blades ending along the tile edge
    "wl16": {"cam": [9.0, 0, 13.0]},
    "wl17": {"cam": [-6.0, 0, -2.0]},    # 15 m off: the whole flipped tree, crown down, trunk up
    "wl15": {"cam": [-1.0, 0, 4.0]},
}


def dump_answers():
    from playwright.sync_api import sync_playwright
    args = ["--no-sandbox", "--disable-dev-shm-usage", "--enable-webgl", "--ignore-gpu-blocklist", "--use-angle=gl-egl"]
    out = {}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=args)
        for cid, slug in CASES:
            pg = b.new_page(viewport={"width": 640, "height": 400})
            pg.goto(f"file://{REPO / PAGE}?bug={cid}-{slug}&seed={WORLD_SEED}&benchmark=1", wait_until="load", timeout=300000)
            for _ in range(240):
                if pg.evaluate("() => !!(window.BenchmarkWorld && window.BenchmarkWorld.ready)"):
                    break
                pg.wait_for_timeout(500)
            pg.wait_for_timeout(4000)   # let the spawn chunks and the watchers settle
            out[cid] = pg.evaluate("() => window.BenchmarkWorld.bug")
            pg.close()
        b.close()
    return out


def main():
    answers = dump_answers() if "--no-answers" not in sys.argv else {}
    base = {"page": PAGE, "worldSeed": WORLD_SEED, "spawn": SPAWN, "targets": TARGETS, "bounds": BOUNDS}
    cfg = dict(base, name="wl00-clean", bug=None, meta={"title": "wl00-clean", "desc": "wilderness, no bug"})
    (OUT / "wl00-clean.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
    for cid, slug in CASES:
        name = f"{cid}-{slug}"
        ans = answers.get(cid)
        cfg = dict(base, name=name, bug=name, meta={"title": name, "desc": ans["where"] if ans else name}, view=VIEWS.get(cid))
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
