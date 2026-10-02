#!/usr/bin/env python3
"""Re-inject the runtime layers into the existing single-file builds (the upstream assets / packs are not on this
machine, so a full rebuild is impossible; the builds embed the layer sources verbatim, so replacing them yields exactly
what the build scripts would produce from the edited sources).

  water   : pack module app/bugs.js (gzip+base64 in window.__PACK) + window.__BUG_LIST
  cottage : pack module app/bugs.js + window.__BUG_LIST
  sketch  : plain <script> blocks bugs.js / enhance.js (matched against the git HEAD sources) + window.__BUG_LIST

usage: relayer.py <family> [--in file] [--out file]
"""
import base64, gzip, json, pathlib, re, subprocess, sys

REPO = pathlib.Path('/home/ubuntu/game-auditing')
CE = REPO / 'environments/threejs/scenes'
sys.path.insert(0, str(CE / 'src/common')); from noui import inject_noui, KEYS  # noqa: E402  (the review site's clean view)
FAM = {
    'water': dict(html='10_beautiful_water_clean_constrained.html', prefix='wt', family='Reef dive · WT bug suite', modules={'app/bugs.js': CE / 'src/water/app/bugs.js', 'app/fish.js': CE / 'src/water/app/fish.js'}),
    'cottage': dict(html='01_mistwood_cottage_constrained.html', prefix='ct', family='Mistwood Cottage · CT bug suite', modules={'app/bugs.js': CE / 'src/cottage/app/bugs.js'}),
    'sketch': dict(html='03_sketchbook_airfield_constrained.html', prefix='af', family='Sketchbook airfield · AF bug suite'),
}


def bug_list(prefix):
    out = []
    for p in sorted((REPO / 'environments/threejs/runtime' / 'configs').glob(f'{prefix}[0-9][0-9]-*.json')):
        if p.name.endswith('.answers.json'):
            continue
        c = json.loads(p.read_text(encoding='utf-8')); ans_p = p.with_name(p.name[:-5] + '.answers.json')
        ans = json.loads(ans_p.read_text(encoding='utf-8')) if ans_p.exists() else []
        out.append({'id': c['name'], 'name': ans[0]['name'] if ans else c.get('meta', {}).get('desc', c['name']), 'where': ans[0]['where'] if ans else '', 'at': ans[0]['at'] if ans else None})
    return out


def replace_bug_list(html, prefix, family):
    new = 'window.__BUG_LIST=' + json.dumps(bug_list(prefix), ensure_ascii=False).replace('</', '<\\/') + ';window.__BUG_FAMILY=' + json.dumps(family) + ';'
    m = re.search(r'window\.__BUG_LIST=\[.*?\];window\.__BUG_FAMILY="[^"]*";', html, re.S)
    assert m, 'BUG_LIST block not found'
    assert html.count('window.__BUG_LIST=') == 1
    return html[:m.start()] + new + html[m.end():]


def relayer_pack(html, modules):
    key = 'window.__PACK='
    i = html.find(key); assert i >= 0
    pack, end = json.JSONDecoder().raw_decode(html, i + len(key))
    for module, src in modules.items():
        assert module in pack['js'], module
        pack['js'][module] = base64.b64encode(gzip.compress(src.read_text(encoding='utf-8').encode('utf-8'), 9)).decode('ascii')
    payload = (key + json.dumps(pack, separators=(',', ':')) + ';').replace('</', '<\\/')
    # the original payload ends with ';' right after the JSON object
    assert html[end] == ';', repr(html[end:end + 5])
    return html[:i] + payload + html[end + 1:]


def relayer_sketch(html):
    for name in ('bugs.js', 'enhance.js'):
        old = subprocess.check_output(['git', 'show', f'HEAD:environments/threejs/scenes/src/sketch/{name}'], cwd=REPO, text=True)
        new = (CE / 'src/sketch' / name).read_text(encoding='utf-8')
        if html.count(new) == 1:
            continue   # already injected (second pass only refreshes the catalogue list)
        assert html.count(old) == 1, f'{name}: old block found {html.count(old)} times'
        html = html.replace(old, new)
    return html


def main():
    fam = sys.argv[1]; spec = FAM[fam]
    src = pathlib.Path(sys.argv[sys.argv.index('--in') + 1]) if '--in' in sys.argv else CE / spec['html']
    dst = pathlib.Path(sys.argv[sys.argv.index('--out') + 1]) if '--out' in sys.argv else CE / spec['html']
    html = src.read_text(encoding='utf-8')
    if fam == 'sketch':
        html = relayer_sketch(html)
    else:
        html = relayer_pack(html, spec['modules'])
    html = replace_bug_list(html, spec['prefix'], spec['family'])
    html = inject_noui(html, KEYS[fam])   # ?noui=1: hide every page overlay, swallow keys outside the agent's action space
    dst.write_text(html, encoding='utf-8')
    print(f'wrote {dst} ({dst.stat().st_size / 1e6:.1f} MB)')


if __name__ == '__main__':
    main()
