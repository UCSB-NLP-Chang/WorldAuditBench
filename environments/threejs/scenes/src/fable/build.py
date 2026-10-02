#!/usr/bin/env python3
"""Build 13_beyond_fable_wilderness_constrained.html (v2) from the modified upstream source.

Steps: `vite build` (Node from /mnt/data3/jingbo/tools/node), inline the single JS bundle and the CSS
into dist/index.html, add the upstream licence note and the benchmark boundary block (copied from the
original candidate), write the single-file HTML.
Usage: build.py --out <html> [--skip-vite]
"""
import argparse
import json
import os
import pathlib
import re
import subprocess

HERE = pathlib.Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(HERE.parent / "common")); from noui import inject_noui, KEYS  # noqa: E402  (src/common/noui.py: the review site's clean view)
UP = HERE / "upstream"
NODE_BIN = "/mnt/data3/jingbo/tools/node/bin"

LICENSE_NOTE = """<!--
  Benchmark-ready standalone adaptation (v2 polish: PBR terrain/rock/bark textures, realistic player
  scale, deterministic daytime, BenchmarkWorld API).  No bug has been injected.
  Upstream: https://github.com/xikhar/beyond-fable (MIT, Copyright (c) 2026 Shikhar)
  Textures: Poly Haven (CC0).  Controls: WASD + mouse, Shift, Space/Z, F, E, R, T, ~
-->"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--skip-vite", action="store_true")
    a = ap.parse_args()
    if not a.skip_vite:
        env = dict(os.environ, PATH=NODE_BIN + os.pathsep + os.environ.get("PATH", ""))
        subprocess.run(["npm", "run", "build"], cwd=UP, env=env, check=True)
    dist = UP / "dist"
    html = (dist / "index.html").read_text(encoding="utf-8")
    js_files = sorted((dist / "assets").glob("*.js"))
    css_files = sorted((dist / "assets").glob("*.css"))
    assert len(js_files) == 1, js_files
    js = js_files[0].read_text(encoding="utf-8")
    css = "\n".join(f.read_text(encoding="utf-8") for f in css_files)
    html = re.sub(r'<script type="module" crossorigin src="[^"]+"></script>', "", html)
    html = re.sub(r'<link rel="stylesheet" crossorigin href="[^"]+">', "", html)
    html = html.replace("<title>Beyond Fable — Procedural Walking World</title>",
                        "<title>Beyond Fable Wilderness · Constrained Benchmark (v2)</title>")
    harness = (HERE.parent / "common" / "harness_page.js").read_text(encoding="utf-8")   # shared window.__env contract
    picker = (HERE.parent / "common" / "bug_picker.js").read_text(encoding="utf-8")      # review overlay
    bug_list = []
    for p in sorted((HERE.parents[4] / "environments/threejs/runtime" / "configs").glob("wl[0-9][0-9]-*.json")):
        if p.name.endswith(".answers.json"):
            continue
        c = json.loads(p.read_text(encoding="utf-8")); ans_p = p.with_name(p.name[:-5] + ".answers.json")
        ans = json.loads(ans_p.read_text(encoding="utf-8")) if ans_p.exists() else []
        bug_list.append({"id": c["name"], "name": ans[0]["name"] if ans else c.get("meta", {}).get("desc", c["name"]), "where": ans[0]["where"] if ans else "", "at": ans[0]["at"] if ans else None})
    picker_block = "<script>window.__BUG_LIST=" + json.dumps(bug_list, ensure_ascii=False).replace("</", "<\\/") + ";window.__BUG_FAMILY=\"Beyond Fable wilderness · WL bug suite\";</script>\n<script>\n" + picker + "\n</script>\n"
    html = html.replace("</head>", f"<style>\n{css}\n</style>\n<script>\n{harness}\n</script>\n<script type=\"module\">\n{js}\n</script>\n</head>")
    html = html.replace("<body>", "<body>\n" + LICENSE_NOTE, 1)
    boundary = (HERE / "boundary_block.html").read_text(encoding="utf-8")
    html = html.replace("</body>", boundary + "\n" + picker_block + "</body>")
    html = inject_noui(html, KEYS["fable"])
    out = pathlib.Path(a.out)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
