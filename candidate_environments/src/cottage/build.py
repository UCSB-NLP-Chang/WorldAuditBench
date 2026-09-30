#!/usr/bin/env python3
"""Assemble the single-file Mistwood Cottage environment.

usage: build.py --vendor <dir> --static <dir> --out <html>

* JS modules: three.js r177 build + addons, the upstream ES modules (with `.glsl` files converted
  to string modules and `#include ../x.glsl` resolved), shims for gsap / rapier / lil-gui / stats-gl.
  Embedded as gzip+base64; the bootstrap in template.html turns them into blob-URL modules.
* Assets: every file under --static that the app loads (models, textures, sounds, draco decoder,
  cursor icons) embedded as base64 and served through `window.__resolveAsset(path)` + a fetch
  override (for the DRACO decoder files).
"""
import argparse
import base64
import gzip
import json
import mimetypes
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(HERE.parent / "common")); from noui import inject_noui, KEYS  # noqa: E402  (src/common/noui.py: the review site's clean view)
IMPORT_RE = re.compile(r"""(?:from\s*|import\s*\(\s*|^\s*import\s+)(['"])([^'"]+)\1""", re.M)
GLSL_INCLUDE_RE = re.compile(r"^[ \t]*#include[ \t]+([^<\s;]+)[ \t]*;?[ \t]*$", re.M)

ALIASES = {
    "three": "vendor/three.module.js",
    "@dimforge/rapier3d": "app/shims/rapier3d.js",
    "gsap": "app/shims/gsap.js",
    "lil-gui": "app/shims/lil-gui.js",
    "stats-gl": "app/shims/stats-gl.js",
}
VENDOR_FILES = {
    "vendor/three.core.js": "three.core.js",
    "vendor/three.module.js": "three.module.js",
    "vendor/rapier.es.js": "rapier.es.js",
    "vendor/addons/loaders/GLTFLoader.js": "GLTFLoader.js",
    "vendor/addons/loaders/DRACOLoader.js": "DRACOLoader.js",
    "vendor/addons/loaders/EXRLoader.js": "EXRLoader.js",
    "vendor/addons/loaders/RGBELoader.js": "RGBELoader.js",
    "vendor/addons/libs/fflate.module.js": "fflate.module.js",
    "vendor/addons/utils/BufferGeometryUtils.js": "BufferGeometryUtils.js",
    "vendor/addons/utils/SkeletonUtils.js": "SkeletonUtils.js",
    "vendor/addons/postprocessing/EffectComposer.js": "EffectComposer.js",
    "vendor/addons/postprocessing/RenderPass.js": "RenderPass.js",
    "vendor/addons/postprocessing/Pass.js": "Pass.js",
    "vendor/addons/postprocessing/MaskPass.js": "MaskPass.js",
    "vendor/addons/postprocessing/ShaderPass.js": "ShaderPass.js",
    "vendor/addons/postprocessing/UnrealBloomPass.js": "UnrealBloomPass.js",
    "vendor/addons/shaders/CopyShader.js": "CopyShader.js",
    "vendor/addons/shaders/LuminosityHighPassShader.js": "LuminosityHighPassShader.js",
    "vendor/addons/objects/Reflector.js": "Reflector.js",
    "vendor/addons/objects/Refractor.js": "Refractor.js",
}
# static files to embed (relative to --static); draco encoder / exr env map / share image are skipped
EMBED_DIRS = ["models", "textures", "sounds", "icons"]
EMBED_EXTRA = ["draco/gltf/draco_wasm_wrapper.js", "draco/gltf/draco_decoder.wasm"]
SKIP_SUFFIXES = (".exr", "draco_encoder.js")


def resolve(spec, from_path, known):
    if spec in ALIASES:
        return ALIASES[spec]
    if spec.startswith("three/examples/jsm/"):
        return "vendor/addons/" + spec[len("three/examples/jsm/"):]
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
        path = "/".join(parts)
        for cand in (path, path + ".js", path + "/index.js"):
            if cand in known:
                return cand
        return path
    return spec


def glsl_module(path: pathlib.Path, depth=0):
    src = path.read_text(encoding="utf-8")

    def sub(m):
        inc = (path.parent / m.group(1)).resolve()
        if depth > 8 or not inc.exists():
            return m.group(0)
        return glsl_source(inc, depth + 1)
    return GLSL_INCLUDE_RE.sub(sub, src)


def glsl_source(path, depth=0):
    return glsl_module(path, depth)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vendor", required=True)
    ap.add_argument("--static", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    vendor, static = pathlib.Path(a.vendor), pathlib.Path(a.static)

    sources = {}
    for key, name in VENDOR_FILES.items():
        sources[key] = (vendor / name).read_text(encoding="utf-8")
    for sub in ("upstream", "app"):
        for p in (HERE / sub).rglob("*"):
            if not p.is_file():
                continue
            rel = f"{sub}/{p.relative_to(HERE / sub).as_posix()}"
            if p.suffix == ".js":
                sources[rel] = p.read_text(encoding="utf-8")
            elif p.suffix == ".glsl":
                sources[rel] = "export default " + json.dumps(glsl_source(p)) + ";\n"
    known = set(sources)
    deps = {}
    for path, src in sources.items():
        deps[path] = []
        for m in IMPORT_RE.finditer(src):
            target = resolve(m.group(2), path, known)
            if target in known and target != path:
                deps[path].append(target)
    order, seen = [], set()

    def visit(path, stack=()):
        if path in seen or path in stack:
            return
        for d in deps[path]:
            visit(d, stack + (path,))
        seen.add(path)
        order.append(path)
    visit("app/main.js")

    pack = {
        "js": {p: base64.b64encode(gzip.compress(sources[p].encode("utf-8"), 9)).decode("ascii") for p in order},
        "order": order,
        "entry": "app/main.js",
        "aliases": ALIASES,
        "assets": {},
    }
    files = []
    for d in EMBED_DIRS:
        files += [p for p in (static / d).rglob("*") if p.is_file()]
    files += [static / e for e in EMBED_EXTRA]
    total = 0
    for p in files:
        rel = p.relative_to(static).as_posix()
        if rel.endswith(SKIP_SUFFIXES):
            continue
        data = p.read_bytes()
        total += len(data)
        mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        if p.suffix == ".webp":
            mime = "image/webp"
        if p.suffix == ".wasm":
            mime = "application/wasm"
        pack["assets"][rel] = {"t": mime, "d": base64.b64encode(data).decode("ascii")}
    payload = ("window.__PACK=" + json.dumps(pack, separators=(",", ":")) + ";").replace("</", "<\\/")

    css = (HERE / "app/style.css").read_text(encoding="utf-8")
    body = (HERE / "app/body.html").read_text(encoding="utf-8")
    html = (HERE / "template.html").read_text(encoding="utf-8")
    gsap = (vendor / "gsap.js").read_text(encoding="utf-8").replace("</", "<\\/")
    harness = (HERE.parent / "common" / "harness_page.js").read_text(encoding="utf-8")   # shared window.__env contract
    picker = (HERE.parent / "common" / "bug_picker.js").read_text(encoding="utf-8")      # review overlay
    bug_list = []
    for p in sorted((HERE.parents[2] / "env" / "configs").glob("ct[0-9][0-9]-*.json")):
        if p.name.endswith(".answers.json"):
            continue
        c = json.loads(p.read_text(encoding="utf-8")); ans_p = p.with_name(p.name[:-5] + ".answers.json")
        ans = json.loads(ans_p.read_text(encoding="utf-8")) if ans_p.exists() else []
        bug_list.append({"id": c["name"], "name": ans[0]["name"] if ans else c.get("meta", {}).get("desc", c["name"]), "where": ans[0]["where"] if ans else "", "at": ans[0]["at"] if ans else None})
    picker_block = "window.__BUG_LIST=" + json.dumps(bug_list, ensure_ascii=False).replace("</", "<\\/") + ";window.__BUG_FAMILY=\"Mistwood Cottage · CT bug suite\";\n" + picker
    html = html.replace("/*__CSS__*/", css).replace("<!--__BODY__-->", body).replace("/*__PACK__*/", payload).replace("/*__GSAP__*/", gsap).replace("/*__HARNESS__*/", harness).replace("/*__PICKER__*/", picker_block)
    html = inject_noui(html, KEYS["cottage"])
    out = pathlib.Path(a.out)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size/1e6:.1f} MB; assets {total/1e6:.1f} MB raw in {len(pack['assets'])} files; "
          f"js {sum(len(v) for v in pack['js'].values())/1e6:.1f} MB in {len(order)} modules)")


if __name__ == "__main__":
    main()
