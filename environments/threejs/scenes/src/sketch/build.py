#!/usr/bin/env python3
"""Build 03_sketchbook_airfield_constrained.html (v2) from the original single-file build.

The upstream Sketchbook bundle (webpack, three r113 + cannon.js) cannot be rebuilt here (no node), so
the polish layer is applied at runtime:
  1. the minified bundle is patched at three unique anchors to expose `window.THREE`, `window.CANNON`
     and `window.__SB_GLTFLoader` (the exact same class instances the game uses);
  2. `pack.json` (Poly Haven PBR texture sets + quantized JPEG-textured prop GLBs, see manifest.json)
     is embedded as `window.__SKETCH_PACK__`;
  3. `enhance.js` runs once the world has loaded (lighting/colour, PBR materials, props with cannon
     colliders, camera/HUD helpers and the BenchmarkWorld API).

Usage: build.py --orig <orig_v1 .bak> --pack <pack.json> --out <html>
"""
import argparse
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(HERE.parent / "common")); from noui import inject_noui, KEYS  # noqa: E402  (src/common/noui.py: the review site's clean view)

PATCHES = [
    # (anchor, replacement) — each anchor must occur exactly once in the bundle
    ('n.r(e),n.d(e,"ACESFilmicToneMapping"', 'n.r(e),window.THREE=e,n.d(e,"ACESFilmicToneMapping"'),
    ('this.gltfLoader=new i.GLTFLoader,', 'this.gltfLoader=new i.GLTFLoader,window.__SB_GLTFLoader=i.GLTFLoader,'),
    ('e.setupMeshProperties=function(t){if(t.castShadow=!0', 'window.CANNON=r,e.setupMeshProperties=function(t){if(t.castShadow=!0'),
    # benchmark build: no jump key (the agent's action space is move / turn / look) - unbind it and drop it from the controls list
    ('jump:new l.KeyBinding("Space")', 'jump:new l.KeyBinding("F24")'),
    ('{keys:["Space"],desc:"Jump"},', ''),
    # no entering vehicles either (parked cars are static props in the benchmark; review 2026-09-12)
    ('enter:new l.KeyBinding("KeyF")', 'enter:new l.KeyBinding("F23")'),
]
# applied to every occurrence (character + each vehicle class): Shift+C free camera is a flying debug camera,
# outside the agent's action space, so the key does nothing and the controls lists no longer mention it
GLOBAL_PATCHES = [
    ('"KeyC"===e&&!0===n&&!0===t.shiftKey', '"KeyC"===e&&!1'),
    (',{keys:["Shift","+","C"],desc:"Free camera"}', ''),
]


def bug_list_json(cfg_dir, prefix, family):
    """window.__BUG_LIST for the review overlay: every <prefix>NN-*.json config with its answer (name / where / at)."""
    out = []
    for p in sorted(cfg_dir.glob(f"{prefix}[0-9][0-9]-*.json")):
        if p.name.endswith(".answers.json"):
            continue
        c = json.loads(p.read_text(encoding="utf-8"))
        ans_p = p.with_name(p.name[:-5] + ".answers.json")
        ans = json.loads(ans_p.read_text(encoding="utf-8")) if ans_p.exists() else []
        out.append({"id": c["name"], "name": ans[0]["name"] if ans else c.get("meta", {}).get("desc", c["name"]), "where": ans[0]["where"] if ans else "", "at": ans[0]["at"] if ans else None})
    return "window.__BUG_LIST=" + json.dumps(out, ensure_ascii=False).replace("</", "<\\/") + ";window.__BUG_FAMILY=" + json.dumps(family) + ";"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig", default=str(HERE / "orig_v1_03_sketchbook_airfield_constrained.html.bak"))
    ap.add_argument("--pack", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    html = pathlib.Path(a.orig).read_text(encoding="utf-8")
    for anchor, repl in PATCHES:
        n = html.count(anchor)
        if n != 1:
            raise SystemExit(f"anchor found {n} times (expected 1): {anchor[:60]}")
        html = html.replace(anchor, repl)
    for anchor, repl in GLOBAL_PATCHES:
        n = html.count(anchor)
        if n == 0:
            raise SystemExit(f"global anchor not found: {anchor[:60]}")
        html = html.replace(anchor, repl)
        print(f"global patch x{n}: {anchor[:50]}")

    pack = pathlib.Path(a.pack).read_text(encoding="utf-8")
    enhance = (HERE / "enhance.js").read_text(encoding="utf-8")
    harness = (HERE.parent / "common" / "harness_page.js").read_text(encoding="utf-8")   # shared window.__env contract
    bugs = (HERE / "bugs.js").read_text(encoding="utf-8")                                # AF bug catalogue (?bug=afXX-slug)
    picker = (HERE.parent / "common" / "bug_picker.js").read_text(encoding="utf-8")      # review overlay
    bug_list = bug_list_json(HERE.parents[4] / "environments/threejs/runtime" / "configs", "af", "Sketchbook airfield · AF bug suite")
    props = (HERE / "props.json").read_text(encoding="utf-8")
    inject = (
        "  <script>\n  window.__SKETCH_PACK__ = " + pack + ";\n"
        "  window.__SKETCH_PROPS__ = " + props + ";\n  </script>\n"
        "  <script>\n" + harness + "\n  </script>\n"
        "  <script>\n" + bugs + "\n  </script>\n"
        "  <script>\n" + enhance + "\n  </script>\n"
        "  <script>\n" + bug_list + "\n" + picker + "\n  </script>\n"
    )
    marker = "<!-- CONSTRAINED_BENCHMARK_BEGIN -->"
    if html.count(marker) != 1:
        raise SystemExit("boundary marker not found")
    html = html.replace(marker, inject + marker)
    # the sunken park (x ±165, z ±106) is walled on all sides: let the boundary cover it instead of ±90 m
    bound_old = '"halfX":90,"halfZ":90,"center":null'
    if html.count(bound_old) != 1:
        raise SystemExit("boundary config anchor not found")
    html = html.replace(bound_old, '"halfX":163,"halfZ":104,"center":[0,15,0]')
    # the boundary notice stays up 1.5 s (was 5 s): long enough for a 2 fps film frame, short enough not to hide the view
    if html.count('"warningMs":5000') != 1:
        raise SystemExit("warningMs anchor not found")
    html = html.replace('"warningMs":5000', '"warningMs":1500')
    html = html.replace("<title>Sketchbook Airfield · Constrained Benchmark</title>",
                        "<title>Sketchbook Airfield · Constrained Benchmark (v2 polish)</title>")
    out = pathlib.Path(a.out)
    html = inject_noui(html, KEYS["sketch"])
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size/1e6:.1f} MB; pack {len(pack)/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
