#!/usr/bin/env python3
"""Pack a harness scene family (house = HS suite, sponza = SP suite) into ONE self-contained HTML file.

The result is env/human.html + env/core.js (mesh-level BVH collision, the same code the agent runs) + the family's
assets and configs embedded as base64, served through an in-page virtual file store (fetch wrapper + three.js
URL modifier).  Open the file in Chrome; `?bug=<config name>` (or `?config=`) selects a case, the bug picker
overlay (src/common/bug_picker.js) lists them and jumps to the answer.

usage: pack_harness_page.py --family house|sponza --out candidate_environments/<name>.html
"""
import argparse, base64, gzip, json, mimetypes, pathlib, re

REPO = pathlib.Path(__file__).resolve().parents[1]
ENV = REPO / "env"
import sys
sys.path.insert(0, str(REPO / "candidate_environments/src/common")); from noui import inject_noui, KEYS  # noqa: E402  (src/common/noui.py: the review site's clean view)
VENDOR = REPO / "assets" / "vendor"
FAMILIES = {
    "house": dict(prefix="hs", assets=["assets/house/pack"], title="Family House · HS bug suite", default="hs00-clean"),
    "sponza": dict(prefix="sp", assets=["assets/sponza"], title="Sponza · SP bug suite", default="sp00-clean"),
}
IMPORT_RE = re.compile(r"""(?:from\s*|import\s*\(\s*|^\s*import\s+)(['"])([^'"]+)\1""", re.M)


def resolve(spec, from_path):
    if spec == "three": return "vendor/three/three.module.js"
    if spec.startswith("three/addons/"): return "vendor/three/addons/" + spec[len("three/addons/"):]
    if spec == "three-mesh-bvh": return "vendor/three-mesh-bvh/index.module.js"
    if spec.startswith("."):
        parts = from_path.split("/")[:-1]
        for seg in spec.split("/"):
            if seg == ".": continue
            if seg == "..": parts.pop()
            else: parts.append(seg)
        return "/".join(parts)
    return spec


def module_sources(entry_src):
    files = {"vendor/three/three.module.js": VENDOR / "three/three.module.js", "vendor/three-mesh-bvh/index.module.js": VENDOR / "three-mesh-bvh/index.module.js"}
    for p in (VENDOR / "three/addons").rglob("*.js"):
        files["vendor/three/addons/" + p.relative_to(VENDOR / "three/addons").as_posix()] = p
    for p in ["core.js", "scenes.js", "bugs.js", "house/house.js"]:
        files["env/" + p] = ENV / p
    sources = {k: p.read_text(encoding="utf-8") for k, p in files.items()}
    sources["env/entry.js"] = entry_src
    # packed page: the walkthrough has the agent's action space - no jump
    sources["env/core.js"] = sources["env/core.js"].replace("if (onFloor && keys['Space'] && !moveReq) vel.y = JUMP;", "/* packed page: no jump */")
    deps = {}
    for path, src in sources.items():
        deps[path] = [t for t in (resolve(m.group(2), path) for m in IMPORT_RE.finditer(src)) if t in sources and t != path]
    order, seen = [], set()
    def visit(path, stack=()):
        if path in seen or path in stack: return
        for d in deps[path]: visit(d, stack + (path,))
        seen.add(path); order.append(path)
    visit("env/entry.js")
    return {p: sources[p] for p in order}, order


BOOT = r"""
<script>/*__PACK__*/</script>
<script>
(async () => {
  'use strict';
  const P = window.__PACK;
  const bytes = s => fetch('data:application/octet-stream;base64,' + s).then(r => r.arrayBuffer());
  const gunzip = buf => new Response(new Blob([buf]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer();
  const text = async s => new TextDecoder().decode(await gunzip(await bytes(s)));
  // ---- virtual file store: repo-relative keys; requests are matched by their /assets/... or /configs/... tail
  const blobUrls = {};
  const vfsKey = (url) => {
    if (!url || /^(blob:|data:)/.test(url)) return null;
    let path; try { path = new URL(url, location.href).pathname; } catch (e) { path = String(url); }
    path = decodeURIComponent(path);
    const i = path.indexOf('/assets/'); if (i >= 0) return path.slice(i + 1);
    const j = path.lastIndexOf('/configs/'); if (j >= 0) return 'env/configs/' + path.slice(j + 9);
    return null;
  };
  window.__vfsUrl = (url) => {
    const k = vfsKey(url); if (!k || !P.vfs[k]) return null;
    if (!blobUrls[k]) { const b = atob(P.vfs[k].b64); const arr = new Uint8Array(b.length); for (let i = 0; i < b.length; i++) arr[i] = b.charCodeAt(i); blobUrls[k] = URL.createObjectURL(new Blob([arr], { type: P.vfs[k].type })); }
    return blobUrls[k];
  };
  const realFetch = window.fetch.bind(window);
  window.fetch = (input, init) => { const u = typeof input === 'string' ? input : (input && input.url); const v = window.__vfsUrl(u); return realFetch(v || input, init); };
  // ---- modules -> blob URLs (imports rewritten in dependency order)
  const urls = {};
  const resolve = (spec, fromPath) => {
    if (spec === 'three') return 'vendor/three/three.module.js';
    if (spec.startsWith('three/addons/')) return 'vendor/three/addons/' + spec.slice(13);
    if (spec === 'three-mesh-bvh') return 'vendor/three-mesh-bvh/index.module.js';
    if (spec.startsWith('.')) { const parts = fromPath.split('/'); parts.pop(); for (const seg of spec.split('/')) { if (seg === '.') continue; if (seg === '..') parts.pop(); else parts.push(seg); } return parts.join('/'); }
    return spec;
  };
  const RE = /(from\s*|import\s*\(\s*|^\s*import\s+)(['"])([^'"]+)\2/gm;
  try {
    for (const path of P.order) {
      const src = (await text(P.js[path])).replace(RE, (m, pre, q, spec) => { const t = resolve(spec, path); return urls[t] ? pre + q + urls[t] + q : m; });
      urls[path] = URL.createObjectURL(new Blob([src], { type: 'text/javascript' }));
    }
    await import(urls[P.entry]);
  } catch (err) { console.error(err); window.__initError = String(err && err.stack || err); const st = document.getElementById('status'); if (st) st.textContent = 'Failed: ' + err; }
})();
</script>
"""

GOTO_HOOKS = """  window.__bugGoto = (at) => {
    const t = ctx.resolvePos(at);   // answers' at-specs: [x, y, z] or {scene, spawnOffset, snap}
    const tgt = t.isVector3 ? t : new THREE.Vector3(...at);
    let best = null;
    for (const ang of [200, 160, 240, 120, 280, 20, 90, 320]) {   // a spot 2.6 m away with floor under it
      const r = ang * Math.PI / 180, x = tgt.x + Math.sin(r) * 2.6, z = tgt.z + Math.cos(r) * 2.6;
      const rc = new THREE.Raycaster(new THREE.Vector3(x, tgt.y + 1.6, z), new THREE.Vector3(0, -1, 0), 0, 6);
      const hit = rc.intersectObjects(ctx.worldMeshes, false)[0];
      if (hit && Math.abs(hit.point.y - (tgt.y - 0.5)) < 2.2) { best = { x, z, y: hit.point.y }; break; }
    }
    if (!best) best = { x: tgt.x + 2.0, z: tgt.z + 2.0, y: Math.max(0, tgt.y - 1) };
    ctx.teleportTo(best.x, best.y, best.z, Math.atan2(-(tgt.x - best.x), -(tgt.z - best.z)));
    fx.toast('at the bug');
  };
  window.__bugBeacon = () => { buildHelpers(); beacons.visible = !beacons.visible; helpers.visible = beacons.visible; return beacons.visible; };
  // used by eval/score_flags.py: resolve answers' at-specs into world coordinates (human entry only)"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--family", required=True, choices=FAMILIES)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    fam = FAMILIES[a.family]
    html = (ENV / "human.html").read_text(encoding="utf-8")
    m = re.search(r'<script type="module">\n(.*?)\n</script>', html, re.S)
    entry = m.group(1)
    for old, new in [
        ("const name = q.get('config') || 'env3-buggy-world';", f"const name = q.get('config') || q.get('bug') || '{fam['default']}';"),
        ("import { initEnv } from './core.js';", "import { initEnv } from './core.js';\n// virtual file store: every asset / config fetch is answered from the embedded data\nTHREE.DefaultLoadingManager.setURLModifier((u) => window.__vfsUrl(u) || u);"),
        ("  // used by eval/score_flags.py: resolve answers' at-specs into world coordinates (human entry only)", GOTO_HOOKS),
        ("  if (e.code === 'KeyF') { flyOn = !flyOn; ctx.setFlying(flyOn); fx.toast(flyOn ? 'Flying (no collision)' : 'Walking'); }\n", ""),
    ]:
        assert entry.count(old) == 1, old[:60]
        entry = entry.replace(old, new)
    sources, order = module_sources(entry)
    js = {p: base64.b64encode(gzip.compress(sources[p].encode("utf-8"), 9)).decode("ascii") for p in order}
    vfs = {}
    for rel in fam["assets"]:
        for p in sorted((REPO / rel).rglob("*")):
            if p.is_file():
                vfs[p.relative_to(REPO).as_posix()] = {"b64": base64.b64encode(p.read_bytes()).decode("ascii"), "type": mimetypes.guess_type(p.name)[0] or "application/octet-stream"}
    cfgs = sorted((ENV / "configs").glob(f"{fam['prefix']}[0-9][0-9]-*.json"))
    for p in cfgs:
        vfs["env/configs/" + p.name] = {"b64": base64.b64encode(p.read_bytes()).decode("ascii"), "type": "application/json"}
    bug_list = []
    for p in cfgs:
        if p.name.endswith(".answers.json") or p.name.endswith("-near.json"): continue   # L3 near-spawn variants duplicate the base cases
        c = json.loads(p.read_text()); ans_p = p.with_name(p.name[:-5] + ".answers.json")
        ans = json.loads(ans_p.read_text()) if ans_p.exists() else []
        bug_list.append({"id": c["name"], "name": ans[0]["name"] if ans else (c.get("meta", {}).get("desc") or c["name"]), "where": ans[0]["where"] if ans else "", "at": ans[0]["at"] if ans else None})
    picker = (REPO / "candidate_environments/src/common/bug_picker.js").read_text(encoding="utf-8")
    pack = json.dumps({"js": js, "order": order, "entry": "env/entry.js", "vfs": vfs}, separators=(",", ":")).replace("</", "<\\/")
    html = re.sub(r'<script type="importmap">.*?</script>\n', "", html, flags=re.S)
    inject = BOOT.replace("/*__PACK__*/", "window.__PACK=" + pack + ";") + f"<script>window.__BUG_LIST={json.dumps(bug_list, ensure_ascii=False)};window.__BUG_FAMILY={json.dumps(fam['title'])};</script>\n<script>\n{picker}\n</script>"
    html = html.replace(m.group(0), inject)
    html = inject_noui(html, KEYS["packed"])   # the review site's clean view (?noui=1)
    html = html.replace("<kbd>WASD</kbd> move · <kbd>Shift</kbd> run · <kbd>Space</kbd> jump · <kbd>E</kbd> interact ·", "<kbd>WASD</kbd> move · <kbd>Shift</kbd> run · <kbd>E</kbd> interact ·")
    html = html.replace("<kbd>F</kbd> fly · <kbd>R</kbd> respawn · <kbd>V</kbd> show invisible colliders · <kbd>Esc</kbd> menu", "<kbd>R</kbd> respawn · <kbd>V</kbd> invisible colliders + answer beacons · <kbd>Esc</kbd> menu")
    html = re.sub(r"<title>.*?</title>", f"<title>{fam['title']}</title>", html, count=1)
    out = pathlib.Path(a.out); out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size/1e6:.1f} MB; {len(vfs)} files in the store, {len(order)} modules, {len(bug_list)} cases)")


if __name__ == "__main__":
    main()
