#!/usr/bin/env python3
"""CT suite (Mistwood Cottage): environments/threejs/runtime/configs/ct00-clean.json + ctXX-<slug>.json (+ .answers.json).

The cottage is a standalone page (environments/threejs/scenes/01_mistwood_cottage_constrained.html) that implements
the harness `window.__env` contract itself (src/common/harness_page.js); the bug catalogue lives in
src/cottage/app/bugs.js and the answers are dumped from the page (`BenchmarkWorld.bug`).
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "environments/threejs/runtime" / "configs"
PAGE = "environments/threejs/scenes/01_mistwood_cottage_constrained.html"
CASES = [
    ("ct01", "float"), ("ct02", "clip"), ("ct03", "scale"), ("ct04", "doublespawn"), ("ct05", "airwall"),
    ("ct06", "hole"), ("ct07", "ghost"), ("ct08", "jitter"), ("ct09", "magenta"), ("ct10", "backcull"),
    ("ct11", "xray"), ("ct12", "unload"), ("ct13", "statereset"), ("ct14", "lodpop"), ("ct15", "spawnpile"),
    ("ct17", "timejump"),
]
SPAWN = {"pos": [-0.6, 0.0, 5.0], "yawDeg": 0}          # on the front path south of the door, facing the cottage (-z)
TARGETS = {"zone_far": [-8.5, 2.5, -5.5]}               # the well on the hill to the west
# catalogue viewpoints (scripts/tools/env_bug_shots.py): camera angle around the target (deg: 0 = south of it, 180 = north) or an explicit cam
VIEWS = {
    "ct01": {"cam": [-1.4, 0, 6.4]}, "ct02": {"cam": [-3.0, 0, -3.5]}, "ct03": {"cam": [-5.9, 0, -0.2]}, "ct04": {"cam": [0.0, 0, 4.6]}, "ct05": {"cam": [-0.6, 0, 5.2]},
    "ct06": {"cam": [-0.6, 0, 5.4]}, "ct07": {"cam": [-0.4, 0, 4.6]}, "ct08": {"cam": [-1.0, 0, 3.2]}, "ct09": {"cam": [-7.0, 0, -3.6]},
    "ct10": {"deg": 180}, "ct11": {"cam": [-0.4, 0, 4.4]}, "ct12": {"deg": 180}, "ct13": {"cam": [-1.2, 0, 4.6]}, "ct14": {"cam": [-0.6, 0, 8.0]},
    "ct15": {"cam": [3.4, 0, 6.4]}, "ct17": {"cam": [-0.6, 0, 6.8]},
}
BOUNDS = {"minX": -12, "maxX": 7.5, "minZ": -10.5, "maxZ": 8.5}      # the garden, the back of the cottage and the well hill
EXCLUDE = []      # the pond is excluded by the page itself (ground below the water level is not walkable; see bugs.js installHarnessAdapter)


def dump_answers():
    from playwright.sync_api import sync_playwright
    args = ["--no-sandbox", "--disable-dev-shm-usage", "--enable-webgl", "--ignore-gpu-blocklist", "--use-angle=gl-egl"]
    out = {}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=args)
        for cid, slug in CASES:
            pg = b.new_page(viewport={"width": 640, "height": 400})
            pg.goto(f"file://{REPO / PAGE}?bug={cid}-{slug}", wait_until="load", timeout=300000)
            for _ in range(200):
                if pg.evaluate("() => !!(window.BenchmarkWorld && window.BenchmarkWorld.ready)"):
                    break
                pg.wait_for_timeout(500)
            pg.wait_for_timeout(2500)
            out[cid] = pg.evaluate("() => window.BenchmarkWorld.bug")
            err = pg.evaluate("() => window.__bugError || null")
            if err: print(cid, 'ERROR', err[:200])
            pg.close()
        b.close()
    return out


def main():
    answers = dump_answers() if "--no-answers" not in sys.argv else {}
    base = {"page": PAGE, "spawn": SPAWN, "targets": TARGETS, "bounds": BOUNDS, "exclude": EXCLUDE}
    cfg = dict(base, name="ct00-clean", bug=None, meta={"title": "ct00-clean", "desc": "cottage, no bug"})
    (OUT / "ct00-clean.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
    for cid, slug in CASES:
        name = f"{cid}-{slug}"
        ans = answers.get(cid)
        if ans is None and (OUT / f"{name}.answers.json").exists():
            ans = json.loads((OUT / f"{name}.answers.json").read_text())[0]; ans = dict(ans, id=name)
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
