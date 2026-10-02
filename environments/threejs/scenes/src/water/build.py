#!/usr/bin/env python3
"""Assemble the single-file water environment.

usage: build.py --pack <pack.json> --vendor <dir with three.core.js etc> --out <html>

JS modules (three.js r185 builds/addons, the upstream app sources and app/*) are embedded as
gzip+base64 text; the bootstrap in template.html turns them into blob: URL ES modules, rewriting
bare/relative import specifiers, in the dependency order computed here.
"""
import argparse
import base64
import gzip
import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(HERE.parent / "common")); from noui import inject_noui, KEYS  # noqa: E402  (src/common/noui.py: the review site's clean view)
IMPORT_RE = re.compile(r"""(?:from\s*|import\s*\(\s*|^\s*import\s+)(['"])([^'"]+)\1""", re.M)


def resolve(spec, from_path):
    if spec == "three":
        return "vendor/three.module.js"
    if spec.startswith("three/addons/"):
        return "vendor/addons/" + spec[len("three/addons/"):]
    if spec.startswith("."):
        parts = from_path.split("/")[:-1]
        for seg in spec.split("/"):
            if seg == ".":
                continue
            if seg == "..":
                parts.pop()
            else:
                parts.append(seg)
        return "/".join(parts)
    return spec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", required=True)
    ap.add_argument("--vendor", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    vendor = pathlib.Path(a.vendor)

    files = {
        "vendor/three.core.js": vendor / "three.core.js",
        "vendor/three.module.js": vendor / "three.module.js",
        "vendor/addons/controls/OrbitControls.js": vendor / "OrbitControls.js",
        "vendor/addons/objects/Reflector.js": vendor / "Reflector.js",
        "vendor/addons/objects/Refractor.js": vendor / "Refractor.js",
        "vendor/addons/loaders/GLTFLoader.js": vendor / "GLTFLoader.js",
        "vendor/addons/utils/BufferGeometryUtils.js": vendor / "BufferGeometryUtils.js",
        "vendor/addons/utils/SkeletonUtils.js": vendor / "SkeletonUtils.js",
    }
    for sub in ("upstream", "app"):
        for p in (HERE / sub).rglob("*.js"):
            files[f"{sub}/{p.relative_to(HERE / sub).as_posix()}"] = p

    sources = {k: p.read_text(encoding="utf-8") for k, p in files.items()}
    deps = {}
    for path, src in sources.items():
        deps[path] = []
        for m in IMPORT_RE.finditer(src):
            target = resolve(m.group(2), path)
            if target in sources and target != path:
                deps[path].append(target)

    order, seen = [], set()

    def visit(path, stack=()):
        if path in seen:
            return
        if path in stack:
            return  # cycle (three.core <-> module is not one); ignore
        for d in deps[path]:
            visit(d, stack + (path,))
        seen.add(path)
        order.append(path)

    visit("app/main.js")
    pack = json.load(open(a.pack))
    pack["js"] = {p: base64.b64encode(gzip.compress(sources[p].encode("utf-8"), 9)).decode("ascii") for p in order}
    pack["order"] = order
    pack["entry"] = "app/main.js"
    payload = ("window.__PACK=" + json.dumps(pack, separators=(",", ":")) + ";").replace("</", "<\\/")

    css = (HERE / "upstream/style.css").read_text(encoding="utf-8") + "\n" + (HERE / "app/dive.css").read_text(encoding="utf-8")
    picker = (HERE.parent / "common" / "bug_picker.js").read_text(encoding="utf-8")      # review overlay
    bug_list = []
    for p in sorted((HERE.parents[4] / "environments/threejs/runtime" / "configs").glob("wt[0-9][0-9]-*.json")):
        if p.name.endswith(".answers.json"):
            continue
        c = json.loads(p.read_text(encoding="utf-8")); ans_p = p.with_name(p.name[:-5] + ".answers.json")
        ans = json.loads(ans_p.read_text(encoding="utf-8")) if ans_p.exists() else []
        bug_list.append({"id": c["name"], "name": ans[0]["name"] if ans else c.get("meta", {}).get("desc", c["name"]), "where": ans[0]["where"] if ans else "", "at": ans[0]["at"] if ans else None})
    picker_block = "window.__BUG_LIST=" + json.dumps(bug_list, ensure_ascii=False).replace("</", "<\\/") + ";window.__BUG_FAMILY=\"Reef dive · WT bug suite\";\n" + picker
    html = (HERE / "template.html").read_text(encoding="utf-8").replace("/*__PACK__*/", payload).replace("/*__CSS__*/", css).replace("/*__PICKER__*/", picker_block)
    html = inject_noui(html, KEYS["water"])
    out = pathlib.Path(a.out)
    out.write_text(html, encoding="utf-8")
    js_mb = sum(len(v) for v in pack["js"].values()) / 1e6
    print(f"wrote {out} ({out.stat().st_size/1e6:.1f} MB; models {sum(len(m['glb']) for m in pack['models'].values())/1e6:.1f} MB, "
          f"textures {sum(sum(len(x) for x in t.values()) for t in pack['textures'].values())/1e6:.1f} MB, js {js_mb:.1f} MB, {len(order)} modules)")


if __name__ == "__main__":
    main()
