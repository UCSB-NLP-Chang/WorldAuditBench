#!/usr/bin/env python3
"""Heuristic exposure scoring for VLA explorer recordings (no VLM anywhere).

For every episode under runs/<tag>/<config>-s0/ (poses.jsonl + meta.json) and its planted bug (position from
reports/eval-task-sets-2026-09-17.positions.json, kind from the config name) decide whether the bug observably
manifested in the recording, from geometry and logged events only:
  * static geometry / visual bugs (float, clip, scale, doublespawn, spawnpile, magenta, jitter, misrotated, upsidedown,
    noshadow, fishreverse, fishupside): the carrier inside the view cone (cos >= 0.75) within `dmax` for >= 10 ticks (0.5 s);
  * airwall: the walker within 2.5 m of the wall, held-W with no displacement for >= 10 ticks;
  * hole / terrainhole: the walker respawned (fell through) or stood inside the hole footprint;
  * ghost* (no collision): the walker's position inside the carrier's footprint (walked through it);
  * xray: carrier inside the view cone within 25 m for >= 10 ticks (it renders through occluders);
  * lodpop: seen from far (> 16 m) and later from near (< 8 m) - the LOD transition was crossed on camera;
  * backcull: seen from at least two sides (>= 120 deg apart around the carrier), so the culled side was among them;
  * unload / statereset: seen, then the walker went beyond the trigger radius (16 m / 12 m), then seen again;
  * pushcar: the walker held W within 2 m of the car for >= 20 ticks (pushed it);
  * timejump (global day/night flicker): any recording longer than 2 s.
Outputs per episode: exposed, first exposure tick, ticks in view, path length, visited 2 m cells, recoveries; a markdown
table per suite.  usage: .venv/bin/python -m eval.vla_exposure runs/vla-threejs --out reports/vla-threejs-exposure.md
"""
import argparse, json, math, pathlib, collections

REPO = pathlib.Path(__file__).resolve().parents[1]
STATIC = {'float', 'clip', 'scale', 'doublespawn', 'spawnpile', 'magenta', 'jitter', 'misrotated', 'upsidedown', 'noshadow', 'fishreverse', 'fishupside'}
DMAX = {'sp': 8.0, 'hs': 7.0, 'wt': 9.0, 'ct': 9.0, 'af': 14.0, 'wl': 16.0}
TRIGGER = {'unload': 16.0, 'statereset': 12.0}


def fwd(yaw_deg):   # three.js: yaw 0 = -z, positive = turning left
    r = math.radians(yaw_deg); return (-math.sin(r), -math.cos(r))


EYE = {'sp': 1.7, 'hs': 1.7, 'ct': 1.6, 'af': 1.6, 'wl': 0.0, 'wt': 0.0}   # pose y -> eye height (reef / wilderness poses are camera positions)
VFOV_HALF = 32.0   # degrees: the object must also be inside the vertical field of view (pitch matters: staring at the floor sees nothing)


def hits(poses, tgt, dmax, dot_min=0.75, eye=1.6):
    out = []
    for p in poses:
        x, y, z = p['pos']; dx, dz = tgt[0] - x, tgt[2] - z; d = math.hypot(dx, dz)
        if d < 1e-6 or d > dmax: continue
        f = fwd(p['yaw']); dot = (dx * f[0] + dz * f[1]) / d
        if dot < dot_min: continue
        vert = math.degrees(math.atan2(tgt[1] - (y + eye), d))   # elevation of the target from the eye
        if abs(vert - p.get('pitch', 0.0)) > VFOV_HALF: continue
        out.append((p['t'], d, math.degrees(math.atan2(-dx, -dz))))
    return out


def score(config, poses, meta, answers):
    kind = config.split('-', 1)[1]; suite = config[:2]
    tgt = answers[0]['position']; dmax = DMAX[suite]
    res = {'config': config, 'kind': kind, 'exposed': False, 'first_tick': None, 'ticks_in_view': 0}
    path = sum(p.get('moved', 0) for p in poses); cells = {(int(p['pos'][0] // 2), int(p['pos'][2] // 2)) for p in poses}
    res.update(path_m=round(path, 1), cells=len(cells), recoveries=meta.get('n_recoveries', 0), ticks=len(poses))
    eye = EYE[suite]
    h = hits(poses, tgt, dmax, eye=eye); res['ticks_in_view'] = len(h)
    near = [p for p in poses if math.hypot(p['pos'][0] - tgt[0], p['pos'][2] - tgt[2]) <= 2.5]
    def ok(cond, tick):
        if cond: res['exposed'] = True; res['first_tick'] = tick
    if kind in STATIC:
        ok(len(h) >= 10, h[9][0] if len(h) >= 10 else None)
    elif kind == 'airwall':
        blocked = [p for p in near if 'KeyW' in p['keys'] and p.get('moved', 1) < 0.02]
        ok(len(blocked) >= 10, blocked[9]['t'] if len(blocked) >= 10 else None)
    elif kind in ('hole', 'terrainhole'):
        fell = [p for p in poses if p.get('respawned')]
        inside = [p for p in poses if math.hypot(p['pos'][0] - tgt[0], p['pos'][2] - tgt[2]) <= 1.2]
        ok(bool(fell) or bool(inside), (fell or inside)[0]['t'] if (fell or inside) else None)
    elif kind.startswith('ghost'):
        r = max(0.6, 0.5 * max(answers[0].get('extent_x', 1.2), answers[0].get('extent_z', 1.2)))
        inside = [p for p in poses if math.hypot(p['pos'][0] - tgt[0], p['pos'][2] - tgt[2]) <= r]
        ok(bool(inside), inside[0]['t'] if inside else None)
    elif kind == 'xray':
        h2 = hits(poses, tgt, 25.0, 0.7, eye=eye); ok(len(h2) >= 10, h2[9][0] if len(h2) >= 10 else None)
    elif kind == 'lodpop':
        far = [t for t, d, _ in hits(poses, tgt, 40.0, 0.7, eye=eye) if d > 16]; nearv = [t for t, d, _ in h if d < 8]
        ok(bool(far) and bool(nearv), max(min(far), min(nearv)) if far and nearv else None)
    elif kind == 'backcull':
        angs = [a for _, _, a in h]
        spread = max((abs((a - b + 180) % 360 - 180) for a in angs for b in angs), default=0)
        ok(len(h) >= 10 and spread >= 120, h[-1][0] if len(h) >= 10 and spread >= 120 else None)
    elif kind in TRIGGER:
        R = TRIGGER[kind]; seen1 = [t for t, _, _ in h]
        if seen1:
            t1 = seen1[0]; away = [p['t'] for p in poses if p['t'] > t1 and math.hypot(p['pos'][0] - tgt[0], p['pos'][2] - tgt[2]) > R]
            if away:
                back = [t for t in seen1 if t > away[0]]
                ok(len(back) >= 10, back[9] if len(back) >= 10 else None)
    elif kind == 'pushcar':
        push = [p for p in poses if 'KeyW' in p['keys'] and math.hypot(p['pos'][0] - tgt[0], p['pos'][2] - tgt[2]) <= 2.0]
        ok(len(push) >= 20, push[19]['t'] if len(push) >= 20 else None)
    elif kind == 'timejump':
        ok(len(poses) >= 40, 40)
    else:
        res['note'] = 'no rule for kind ' + kind
    return res


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('run_base'); ap.add_argument('--out', default=None); ap.add_argument('--positions', default=str(REPO / 'reports/eval-task-sets-2026-09-17.positions.json'))
    a = ap.parse_args()
    positions = json.loads(pathlib.Path(a.positions).read_text())
    rows = []
    for ep in sorted(pathlib.Path(a.run_base).glob('*-s*')):
        if not (ep / 'meta.json').exists(): continue
        meta = json.loads((ep / 'meta.json').read_text()); config = meta['config']
        if config not in positions: continue
        poses = [json.loads(l) for l in (ep / 'poses.jsonl').read_text().splitlines()]
        rows.append(score(config, poses, meta, positions[config]))
    by = collections.defaultdict(list)
    for r in rows: by[r['config'][:2]].append(r)
    lines = ['# VLA explorer exposure (heuristic)', '', f'{a.run_base}: {len(rows)} episodes', '']
    for suite, rs in sorted(by.items()):
        n = sum(r['exposed'] for r in rs)
        lines += [f'## {suite.upper()}: exposed {n}/{len(rs)}', '', '| case | kind | exposed | first tick | ticks in view | path m | cells | recoveries |', '|---|---|---|---|---|---|---|---|']
        for r in rs: lines.append(f"| {r['config']} | {r['kind']} | {'yes' if r['exposed'] else 'no'} | {r['first_tick'] if r['first_tick'] is not None else '-'} | {r['ticks_in_view']} | {r['path_m']} | {r['cells']} | {r['recoveries']} |")
        lines.append('')
    tot = sum(r['exposed'] for r in rows); lines.append(f'**Total exposed: {tot}/{len(rows)}**')
    text = '\n'.join(lines); print(text)
    if a.out: pathlib.Path(a.out).write_text(text + '\n')
    (pathlib.Path(a.run_base) / 'exposure.json').write_text(json.dumps(rows, indent=1))


if __name__ == '__main__':
    main()
