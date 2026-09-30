#!/usr/bin/env python3
"""Stage a versioned, blind task catalog from a read-only audit snapshot.

Preparation writes only the supplied output directory. Apply is run offline by
our deployment script, after backing up both independent databases/configs.
"""
import argparse
import base64
import copy
import gzip
import hashlib
import json
import pathlib
import re
import sys
from urllib.parse import urlsplit, parse_qs

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bf.common import canonical, digest
from bf.exploration import ExplorationStore
from bf.evaluation import EvaluationStore

QUERY = '自由探索这个环境，寻找你认为不符合正常行为或外观的异常。使用 Flag 保存证据截图，并描述你发现的问题；如果没有发现异常，也请如实提交。'
CONTROLS = 'W / A / S / D 移动 · E 交互 · 鼠标观察 · F 截图 · Esc 释放鼠标。可从多个角度探索；截图和描述会自动保存。'


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical(data))
    path.chmod(0o600)


def bundle_page(source, destination, entries):
    """Reuse upstream simulation/assets; replace its informed-review entry entirely."""
    html = source.read_text()
    match = re.search(r'<script>window\.__PACK=(.*?);</script>', html, re.S)
    if not match: raise ValueError('Unsupported browser bundle: ' + source.name)
    pack = json.loads(match[1])
    entry = (ROOT / 'web/exploration/browser-entry.js').read_bytes()
    assert pack['entry'] == 'env/entry.js' and 'env/core.js' in pack['js']
    for version, selector in entries:
        key = 'env/configs/' + selector + '.json'
        original = pack['vfs'][key]
        cfg = json.loads(base64.b64decode(original['b64']))
        cfg.pop('meta', None)
        cfg['name'] = 'exploration'
        public = {'b64': base64.b64encode(canonical(cfg).encode()).decode(), 'type': 'application/json'}
        write(destination.parent / 'configs' / (version + '.json'), public)
    pack['vfs'] = {k: v for k, v in pack['vfs'].items() if '/configs/' not in k and 'answers' not in k.lower()}
    pack['js']['env/entry.js'] = base64.b64encode(gzip.compress(entry, mtime=0)).decode()
    core = gzip.decompress(base64.b64decode(pack['js']['env/core.js'])).decode()
    core = core.replace('window.__ctx = ctx;', '').replace('window.__env = {', 'const privateEnvironment = {')
    pack['js']['env/core.js'] = base64.b64encode(gzip.compress(core.encode(), mtime=0)).decode()
    destination.mkdir(parents=True, exist_ok=True)
    (destination / 'assets.json.gz').write_bytes(gzip.compress(canonical(pack).encode(), compresslevel=6, mtime=0))
    loader = re.search(r'<script>\s*\(async \(\) => \{.*?</script>', html, re.S)[0]
    loader = loader.replace('const P = window.__PACK;', "const P = await fetch('./assets.json').then(r=>{if(!r.ok)throw new Error('Environment unavailable');return r.json();}); P.vfs['env/configs/task.json'] = __BF_CONFIG__;")
    assert 'window.__PACK' not in loader
    styles = '\n'.join(re.findall(r'<style>.*?</style>', html, re.S))
    shell = '''<!doctype html><html><head><meta charset="utf-8"><title>探索环境</title>''' + styles + '''<script src="/static/capture-bridge.js"></script></head><body>
<div id="cross"></div><div id="hud"><div id="prompt"></div></div><div id="corner"></div><div id="keys">WASD 移动 · E 交互 · R 回到起点 · F 截图 · Esc 释放鼠标</div><div id="toast"></div><div id="fade"></div><div id="bwarn"><strong>已到达探索边界</strong><span>请返回可探索区域</span></div>
<div id="panel"><div id="card"><h1 id="title">探索环境</h1><p id="desc">正在加载场景…</p><p id="status">正在准备环境…</p><button id="enter" disabled>进入环境 / Resume</button></div></div>'''
    (destination / 'template.html').write_text(shell + loader + '</body></html>')
    assert '__BUG_LIST' not in shell + loader and '.answers.json' not in shell + loader


def native_page(source, destination, entries):
    """Preserve each upstream native game while removing its informed-review UI."""
    html = source.read_text()
    # These scripts contain only the answer list/review overlay, never gameplay.
    html = re.sub(r'<script[^>]*>.*?</script>', lambda m: '' if 'window.__BUG_LIST' in m[0] else m[0], html, flags=re.S)
    def patch_code(code):
        code = re.sub(r'(?:window\.)?location\.search', 'window.__BF_QUERY', code)
        code = code.replace('const reviewOn = !harnessOn;', 'const reviewOn = false;')
        code = code.replace('window.BenchmarkWorld.bug = bugAnswer;', '')
        code = code.replace('window.BenchmarkWorld.bugCatalog = Object.keys(CATALOG);', '')
        code = code.replace('window.BenchmarkWorld.bugRuntime = ctx;', '')
        code = code.replace('bug: bugAnswer,', 'bug: null,').replace('bugCatalog: Object.keys(CATALOG),', 'bugCatalog: [],')
        return code
    match = re.search(r'<script>window\.__PACK=(.*?);</script>', html, re.S)
    if match:
        pack = json.loads(match[1])
        for key, value in pack['js'].items():
            code = gzip.decompress(base64.b64decode(value)).decode()
            changed = patch_code(code)
            if code != changed: pack['js'][key] = base64.b64encode(gzip.compress(changed.encode(), mtime=0)).decode()
        html = html[:match.start()] + '<script>window.__PACK=' + canonical(pack) + ';</script>' + html[match.end():]
    html = patch_code(html)
    html = html.replace('Reef dive · realistic shallow water · no bug', 'Reef dive · Explore the environment')
    html = re.sub(r'<title>.*?</title>', '<title>探索环境</title>', html, flags=re.S)
    injection = '<script>window.__BF_QUERY=__BF_QUERY_VALUE__;</script><script src="/static/browser-native.js"></script><script src="/static/capture-bridge.js"></script>'
    html = html.replace('<head>', '<head>'+injection, 1)
    assert injection in html and 'window.__BUG_LIST' not in html
    destination.mkdir(parents=True, exist_ok=True)
    (destination/'native.html.gz').write_bytes(gzip.compress(html.encode(), compresslevel=6, mtime=0))
    for version, selector in entries:
        write(destination.parent/'configs'/(version+'.json'), '?bug='+selector+'&noui=1&seed=5')


def prepare(root, audit, site, output):
    ex = json.loads((root / 'config/exploration.json').read_text())
    ev = json.loads((root / 'config/evaluation.json').read_text())
    runtime = json.loads((root / 'config/runtime.json').read_text())
    source_bytes = (audit / 'tasks.json').read_bytes()
    sources = json.loads(source_bytes)['tasks']
    old_runtime = json.loads((audit / 'runtime.json').read_text())
    tasks, references, profiles, mappings, groups, manifest = [], [], {}, {}, {}, []
    versions = []
    existing_tasks = {t['id']: t for t in ex.get('tasks', [ex['task']])}
    existing_refs = {t['id']: t for t in ev['references']}
    for src in sources:
        rubric = src.get('rubrics') or canonical(src['rubrics_i18n'])
        version = digest(canonical({'case': src['id'], 'revision': src['revision'], 'map_sha256': src['sha256'], 'build_sha256': src['build_sha256'], 'rubric': rubric, 'query': QUERY}).encode())[:32]
        browser = src.get('runtime_kind') == 'browser'
        # Only environment identity is public: never source title, category, baseline or bug id.
        title = src['environment'].split('/')[0].strip() + ' · 自由探索'
        task = {'id': version, 'title': title, 'query': QUERY, 'controls': CONTROLS, 'case_key': src['id']}
        reference = {'id': version, 'query': QUERY, 'case_id': src['id'], 'case_revision': src['revision'], 'map_sha256': src['sha256'], 'build_sha256': src['build_sha256'], 'rubric': rubric, 'rubric_sha256': digest(rubric.encode())}
        tasks.append(existing_tasks.get(version, task))
        references.append(existing_refs.get(version, reference))
        versions.append({'id': version, 'case_key': src['id'], 'title': title, 'engine': 'browser' if browser else 'unreal'})
        if browser:
            url = urlsplit(src['map']); filename = pathlib.PurePosixPath(url.path).name
            assert url.path == '/threejs/' + filename and filename.endswith('.html')
            query = parse_qs(url.query); selector = query.get('bug', query.get('config'))[0]
            group = hashlib.sha256(filename.encode()).hexdigest()[:16]
            mappings[version] = {'kind': 'browser', 'bundle': group, 'config_id': version}
            groups.setdefault(filename, {'id': group, 'entries': []})['entries'].append((version, selector))
        else:
            profile = copy.deepcopy(old_runtime['launch_profiles'][src['map']])
            assert pathlib.Path(profile['binary']).is_file() and profile['build_sha256'] == src['build_sha256']
            profile['key_filter'] = profile.get('key_filter', '') + ',F'
            profiles[src['map']] = profile
            mappings[version] = {'map': src['map']}
            manifest.append({k: src[k] for k in ('id', 'map', 'build_sha256')})
    # Retain immutable historical versions and their runtime mappings for existing attempts.
    current_ids = {t['id'] for t in tasks}
    for tid, task in existing_tasks.items():
        if tid not in current_ids:
            tasks.append(task); references.append(existing_refs[tid]); mappings[tid] = ex['runtime']['tasks'][tid]
            old_map = mappings[tid].get('map')
            if old_map:
                prior = runtime['launch_profiles'][old_map]
                if old_map in profiles and prior['build_sha256'] != profiles[old_map]['build_sha256']:
                    raise ValueError('Historical runtime version requires a distinct map key')
                profiles[old_map] = prior
                manifest.append({'id': tid, 'map': old_map, 'build_sha256': prior['build_sha256']})
    assert len(current_ids) == len(sources) == len({s['id'] for s in sources})
    browser_root = output / 'browser-assets'
    for filename, group in groups.items():
        print('Preparing browser environment', filename, flush=True)
        source = site / filename
        if filename.startswith(('00_', '09_')):
            bundle_page(source, browser_root / group['id'], group['entries'])
        else:
            native_page(source, browser_root / group['id'], group['entries'])
    ex['tasks'] = tasks
    ex['runtime']['tasks'] = mappings
    ex['runtime']['browser_root'] = str(browser_root)
    ev['references'] = references
    runtime['launch_profiles'] = profiles
    # Manifest remains at stable config path used by supervisor.
    write(output / 'config/exploration.json', ex)
    write(output / 'config/evaluation.json', ev)
    write(output / 'config/runtime.json', runtime)
    write(output / 'config/runtime-manifest.json', {'tasks': manifest})
    write(output / 'catalog.json', {'tasks': versions, 'source_sha256': digest(source_bytes), 'total': len(sources), 'unreal': sum(v['engine']=='unreal' for v in versions), 'browser': sum(v['engine']=='browser' for v in versions)})
    print('Prepared', len(sources), 'tasks', flush=True)


def apply(root, stage):
    plan = json.loads((root / 'config/access-plan.json').read_text())
    catalog = json.loads((stage / 'catalog.json').read_text())
    exconfig = json.loads((stage / 'config/exploration.json').read_text())
    evconfig = json.loads((stage / 'config/evaluation.json').read_text())
    ex, ev = ExplorationStore(root / 'exploration-state'), EvaluationStore(root / 'evaluation-state')
    try:
        for task in exconfig['tasks']: ex.register_task(task)
        for ref in evconfig['references']: ev.register_reference(ref)
        for store in (ex, ev):
            for task in catalog['tasks']:
                with store.transaction() as db:
                    db.execute('UPDATE task_catalog SET title=?,case_key=? WHERE id=?', (task['title'], task['case_key'], task['id']))
                for name, role in plan['roles'].items(): store.grant_task(name, task['id'], role)
        assert [tuple(x) for x in ex.db.execute('SELECT lower(u.name),task_id,role FROM task_access a JOIN users u ON u.id=a.user_id ORDER BY 1,2')] == [tuple(x) for x in ev.db.execute('SELECT lower(u.name),task_id,role FROM task_access a JOIN users u ON u.id=a.user_id ORDER BY 1,2')]
        plan['tasks'] = catalog['tasks']
        write(root / 'config/access-plan.json', plan)
    finally:
        ex.db.close();ev.db.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser();p.add_argument('mode', choices=['prepare','apply']);p.add_argument('--root', type=pathlib.Path, required=True);p.add_argument('--stage', type=pathlib.Path, required=True)
    p.add_argument('--audit', type=pathlib.Path, default=pathlib.Path('/home/ubuntu/unreal-auditor/review-service/state'))
    p.add_argument('--site', type=pathlib.Path, default=pathlib.Path('/home/ubuntu/unreal-auditor/threejs/releases/envs-2026-09-12/site'))
    a=p.parse_args()
    if a.mode=='prepare': prepare(a.root,a.audit,a.site,a.stage)
    else: apply(a.root,a.stage)
