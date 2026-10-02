#!/usr/bin/env python3
"""Screenshot / probe tool for the three.js bug cases.

usage: viewcase.py --html <file under candidate_environments> --cases id1,id2 --out <dir> [--seed 5] [--gpu vulkan]
                   [--angles 200,80,320] [--radius R] [--extra-wait S] [--steps '<json>']

For every case: load `<html>?bug=<id>&noui=1&seed=<seed>` (the review site's URL shape), wait for the page,
shoot the spawn view, then stand at `radius` around the answer position at each angle looking at it and shoot.
`--steps` runs an extra JSON list of steps after the orbit: {"eval": js} | {"shot": name} | {"sleep": s} |
{"keys": [codes], "ms": n} | {"look": [x, z]} (stand at x,z looking at the answer).
"""
import argparse, json, math, pathlib, sys, time
sys.path.insert(0, '/home/ubuntu/game-auditing')
from agent.vla.bridge import Bridge

REPO = pathlib.Path('/home/ubuntu/game-auditing')

FAMILY = {
    '00_sponza_constrained.html': 'packed', '09_sims_house_builder_constrained.html': 'packed',
    '10_beautiful_water_clean_constrained.html': 'water', '03_sketchbook_airfield_constrained.html': 'sketch',
    '01_mistwood_cottage_constrained.html': 'cottage', '13_beyond_fable_wilderness_constrained.html': 'fable',
}
READY = {
    'packed': "window.__env && window.__env.ready === true",
    'water': "window.BenchmarkWorld && window.BenchmarkWorld.ready === true && window.BenchmarkWorld.bug !== undefined",
    'sketch': "window.BenchmarkWorld && window.BenchmarkWorld.ready === true && window.BenchmarkWorld.bug !== undefined",
    'cottage': "window.BenchmarkWorld && window.BenchmarkWorld.ready === true && window.BenchmarkWorld.bug !== undefined",
    'fable': "window.BenchmarkWorld && window.BenchmarkWorld.ready === true && window.BenchmarkWorld.bug !== undefined",
}
# stand at (x, z) looking at (tx, ty, tz); returns the camera position
LOOK = {
    'packed': """([x, z, tx, ty, tz]) => {
        const c = window.__ctx, T = window.__THREE;
        let y = ty - 0.5;
        const rc = new T.Raycaster(new T.Vector3(x, ty + 1.6, z), new T.Vector3(0, -1, 0), 0, 8);
        const hit = rc.intersectObjects(c.worldMeshes, false)[0]; if (hit) y = hit.point.y;
        const yaw = Math.atan2(-(tx - x), -(tz - z));
        c.teleportTo(x, y, z, yaw);
        const eye = y + 1.7; c.camera.rotation.x = Math.atan2(ty - eye, Math.hypot(tx - x, tz - z));
        return [x, eye, z];
    }""",
    'water': """([x, z, tx, ty, tz]) => {
        const bw = window.BenchmarkWorld; const y = Math.max(-6.2, ty + 0.5);
        bw.teleport(x, y, z);
        const dx = tx - x, dz = tz - z; bw.setView(Math.atan2(-dx, -dz), Math.max(-1.3, Math.min(1.3, Math.atan2(ty - y, Math.hypot(dx, dz)))));
        return [x, y, z];
    }""",
    'sketch': """([x, z, tx, ty, tz]) => {
        const bw = window.BenchmarkWorld; bw.dismissModal(); bw.setFirstPerson(true); bw.teleport(x, null, z);
        const p = bw.getState().position; const eye = p[1] + 1.05;
        const dx = tx - x, dz = tz - z;
        bw.setView(Math.atan2(-dx, -dz) * 180 / Math.PI, Math.max(-80, Math.min(80, -Math.atan2(ty - eye, Math.hypot(dx, dz)) * 180 / Math.PI)));
        return [x, eye, z];
    }""",
    'cottage': """([x, z, tx, ty, tz]) => {
        const bw = window.BenchmarkWorld; bw.setFirstPerson(true); bw.teleport(x, null, z);
        const p = bw.camera.position; const dx = tx - p.x, dz = tz - p.z;
        bw.setView(Math.atan2(-dx, -dz), Math.max(0.35, Math.min(2.6, Math.PI / 2 + Math.atan2(ty - p.y, Math.hypot(dx, dz)))));
        return [p.x, p.y, p.z];
    }""",
    'fable': """([x, z, tx, ty, tz]) => {
        const bw = window.BenchmarkWorld; bw.dismissOverlay(); bw.setHeadless(true); bw.teleport(x, null, z);
        const p = bw.camera.position; const dx = tx - p.x, dz = tz - p.z;
        bw.setView(Math.atan2(-dx, -dz), Math.max(-1.4, Math.min(1.4, Math.atan2(ty - p.y, Math.hypot(dx, dz)))));
        return [p.x, p.y, p.z];
    }""",
}
STATE = {
    'packed': "() => window.__env.state()",
    'water': "() => { const s = window.BenchmarkWorld.getState(); return { pos: s.position, yaw: s.rotation && s.rotation.yaw }; }",
    'sketch': "() => window.BenchmarkWorld.getState()",
    'cottage': "() => window.BenchmarkWorld.getState()",
    'fable': "() => { const s = window.BenchmarkWorld.getState ? window.BenchmarkWorld.getState() : {}; return Object.assign({ seed: window.BenchmarkWorld.seed, bug: window.BenchmarkWorld.bug && window.BenchmarkWorld.bug.id }, s); }",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--html', required=True); ap.add_argument('--cases', required=True); ap.add_argument('--out', required=True)
    ap.add_argument('--seed', default='5'); ap.add_argument('--gpu', default='vulkan')
    ap.add_argument('--angles', default='200,80,320'); ap.add_argument('--radius', type=float, default=None)
    ap.add_argument('--extra-wait', type=float, default=2.0); ap.add_argument('--steps', default=None)
    ap.add_argument('--size', default='960x600')
    a = ap.parse_args()
    fam = FAMILY[a.html]
    w, h = map(int, a.size.split('x'))
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    radius = a.radius or {'packed': 2.8, 'water': 3.2, 'sketch': 4.5, 'cottage': 3.2, 'fable': 6.0}[fam]
    steps = json.loads(a.steps) if a.steps else []
    report = {}
    with Bridge(gpu=a.gpu, size=(w, h)) as br:
        br.page.set_default_timeout(180_000)
        for cid in a.cases.split(','):
            case_dir = out / cid; case_dir.mkdir(exist_ok=True)
            url = f"http://127.0.0.1:{br.port}/environments/threejs/scenes/{a.html}?bug={cid}&noui=1"
            if a.seed not in ('', 'none'): url += f"&seed={a.seed}"
            t0 = time.time(); br.console.clear(); br.page_errors.clear()
            br.page.goto(url)
            try:
                br.page.wait_for_function(READY[fam], timeout=240_000)
            except Exception as e:
                report[cid] = {'error': f'not ready: {e}'}; print(cid, 'NOT READY', e); continue
            time.sleep(a.extra_wait)
            if fam == 'fable': br.page.evaluate("() => { window.BenchmarkWorld.dismissOverlay(); window.BenchmarkWorld.setHeadless(true); }")
            if fam == 'sketch': br.page.evaluate("() => { window.BenchmarkWorld.dismissModal(); window.BenchmarkWorld.setFirstPerson(true); }")
            if fam == 'packed': br.page.evaluate("() => { const p = document.getElementById('panel'); if (p) { p.classList.add('hidden'); p.style.display = 'none'; } }")
            time.sleep(0.6)
            br.page.screenshot(path=str(case_dir / 'spawn.png'))
            entry = br.page.evaluate("(id) => (window.__BUG_LIST || []).find(b => b.id === id) || null", cid)
            bug = br.page.evaluate("() => window.BenchmarkWorld ? (window.BenchmarkWorld.bug || null) : null")
            info = {'load_s': round(time.time() - t0, 1), 'entry': entry, 'bug': bug, 'state0': br.page.evaluate(STATE[fam]),
                    'errors': br.page_errors[:5], 'console_err': [t for ty, t in br.console if ty == 'error'][:8]}
            at = None
            if bug and bug.get('at') and isinstance(bug['at'], list): at = bug['at']
            elif entry and isinstance(entry.get('at'), list): at = entry['at']
            elif entry and isinstance(entry.get('at'), dict) and fam == 'packed':
                at = br.page.evaluate("(spec) => { const v = window.__ctx.resolvePos(spec); return [v.x, v.y, v.z]; }", entry['at'])
            info['at'] = at
            if at:
                for ang in [float(v) for v in a.angles.split(',') if v != '']:
                    r = math.radians(ang); x = at[0] + math.sin(r) * radius; z = at[2] + math.cos(r) * radius
                    cam = br.page.evaluate(LOOK[fam], [x, z, at[0], at[1], at[2]])
                    time.sleep(0.9)
                    br.page.screenshot(path=str(case_dir / f'ang{int(ang)}.png'))
                    info[f'cam{int(ang)}'] = [round(v, 2) for v in cam]
            cfgp = REPO / 'environments/threejs/runtime' / 'configs' / f'{cid}.json'
            try:
                view = json.loads(cfgp.read_text()).get('view') if cfgp.exists() else None
            except Exception:
                view = None
            if at and view and isinstance(view, dict) and view.get('cam'):
                cam = br.page.evaluate(LOOK[fam], [view['cam'][0], view['cam'][2], at[0], at[1], at[2]]); time.sleep(0.9)
                br.page.screenshot(path=str(case_dir / 'cfgview.png')); info['cfgview_cam'] = [round(v, 2) for v in cam]
            for i, st in enumerate(steps):
                if 'eval' in st: info[f'step{i}'] = br.page.evaluate(st['eval'])
                if 'sleep' in st: time.sleep(st['sleep'])
                if 'look' in st and at:
                    cam = br.page.evaluate(LOOK[fam], [st['look'][0], st['look'][1], at[0], at[1], at[2]]); time.sleep(0.9); info[f'step{i}_cam'] = cam
                if 'keys' in st:
                    for k in st['keys']: br.page.keyboard.down(k)
                    time.sleep(st.get('ms', 500) / 1000)
                    for k in st['keys']: br.page.keyboard.up(k)
                    time.sleep(0.3)
                if 'shot' in st: br.page.screenshot(path=str(case_dir / f"{st['shot']}.png"))
                if 'state' in st: info[f'step{i}_state'] = br.page.evaluate(STATE[fam])
            report[cid] = info
            print(cid, json.dumps({k: v for k, v in info.items() if k not in ('entry',)}, ensure_ascii=False)[:600])
    rp = out / 'report.json'; old = json.loads(rp.read_text()) if rp.exists() else {}; old.update(report)
    rp.write_text(json.dumps(old, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
