"""Heuristic exposure scoring for the Unreal VLA episodes (no VLM): did the explorer put the bug object in view, or trigger the bug?

Inputs: runs/<tag>/<TASK>/poses.jsonl + meta.json (harness/vla_ue.py) and the task's exploration-policy focus point (the AWS
review release's tagged target actor / authored review aim) from reports/ue-aws-profiles-<date>.json.  Same view-cone rule as
eval/vla_exposure.py for the three.js suites: per tick the target must be within the family's distance limit, inside the
horizontal cone (dot >= 0.75, about +-41 deg) and within +-32 deg of the camera pitch; static bug kinds need >= 10 such ticks
(0.5 s of simulated time), the other subcategories add what the bug needs (contact, held-W against an invisible wall, leaving
and coming back, two viewing directions, near and far views).  No occlusion test - a target behind a wall counts if the angles
and distance fit.  Distances in cm, Unreal coordinates (yaw 0 = +X, +Y to the right, pitch > 0 = looking up).

  .venv/bin/python -m eval.vla_exposure_ue --tag vla-ue-v1 [--profiles reports/ue-aws-profiles-20260918.json] [--out reports/x.md]
"""
import argparse
import json
import math
import pathlib
import collections

CODE = {'geometry.unsupported': 'G1', 'geometry.intersection': 'G2', 'geometry.scale': 'G3', 'collision.missing': 'C1',
        'collision.unexpected': 'C2', 'collision.contact_response': 'C3', 'visual.visibility': 'V1', 'visual.view_appearance': 'V2',
        'visual.illumination': 'V3', 'visual.material': 'V4', 'state.existence': 'T1', 'state.static_attributes': 'T2',
        'state.operational_state': 'T3', 'semantic.configuration': 'S2', 'semantic.historical': 'S3'}
STATIC = {'G1', 'G2', 'G3', 'S2', 'S3', 'V3', 'V4'}
DMAX = {'indoor': 700, 'subway': 900, 'urban': 1400, 'industrial': 1200, 'ancient': 1400, 'rural': 1600, 'medieval': 1400}
TRIGGER = {'indoor': 800, 'subway': 800}          # "walk away" distance for T1/T2 (outdoor default below)
TRIGGER_DEFAULT = 1200
EYE = 60.0          # camera above the pawn location (capsule centre); UE first-person eye height
VFOV_HALF = 32.0
DOT_MIN = 0.75
MIN_TICKS = 10      # 0.5 s at 50 ms per tick
NEEDS_INTERACT = {'H15'}   # the bug needs an interaction the VLA cannot issue (door swing through the box)


def load_poses(ep):
    return [json.loads(l) for l in (ep / 'poses.jsonl').read_text().splitlines() if l.strip()]


def per_tick(poses, focus, dmax):
    """For each tick: (dist2d, dot, in_cone, moving, w_held)."""
    out = []
    for p in poses:
        pos = p.get('pos_cm') or [0, 0, 0]
        dx, dy = focus[0] - pos[0], focus[1] - pos[1]
        d = math.hypot(dx, dy)
        yaw = math.radians(p.get('yaw') or 0.0)
        dot = (math.cos(yaw) * dx + math.sin(yaw) * dy) / d if d > 1e-6 else 1.0
        vert = math.degrees(math.atan2(focus[2] - (pos[2] + EYE), d))
        pitch = p.get('pitch') or 0.0
        in_cone = d <= dmax and dot >= DOT_MIN and abs(vert - pitch) <= VFOV_HALF
        moving = (p.get('moved_cm') or 0) > 0.5
        out.append((d, dot, in_cone, moving, 'KeyW' in (p.get('keys') or [])))
    return out


def runs_of(flags):
    """Contiguous True runs as (start, length)."""
    res, start = [], None
    for i, f in enumerate(flags + [False]):
        if f and start is None: start = i
        if not f and start is not None: res.append((start, i - start)); start = None
    return res


def score(task, code, poses, family):
    focus = task['policy'].get('focus')
    if not focus:
        return {'exposed': None, 'reason': 'no focus point'}
    dmax = DMAX.get(family, 1200)
    tk = per_tick(poses, focus, dmax)
    seen = [t[2] for t in tk]
    n_seen = sum(seen)
    first_seen = next((i for i, s in enumerate(seen) if s), None)
    res = {'code': code, 'seen_ticks': n_seen, 'first_seen': first_seen, 'min_dist_cm': round(min(t[0] for t in tk), 1)}
    yaws = [(p.get('yaw') or 0.0) for p in poses]

    def n_hits(flags):
        return sum(flags)

    if task['task']['id'] in NEEDS_INTERACT:
        res.update(exposed=False, reason='needs an interaction the VLA cannot issue', seen=n_seen >= MIN_TICKS); return res
    if code in STATIC or code not in {'C1', 'C2', 'C3', 'T1', 'T2', 'T3', 'V1', 'V2'}:
        res.update(exposed=n_seen >= MIN_TICKS, reason=f'in view {n_seen} ticks (need {MIN_TICKS})'); return res
    if code == 'C1':   # walked into / through the object
        touched = [i for i, t in enumerate(tk) if t[0] <= 120 and t[3]]
        res.update(exposed=bool(touched), first_touch=touched[0] if touched else None, reason=f'moved within 1.2 m of the object {len(touched)} ticks'); return res
    if code == 'C2':   # held W near the wall without moving
        blocked = [t[0] <= 250 and t[4] and not t[3] for t in tk]
        n = n_hits(blocked); res.update(exposed=n >= MIN_TICKS, blocked_ticks=n, reason=f'held W without moving within 2.5 m {n} ticks (need {MIN_TICKS})'); return res
    if code == 'C3':   # contact, then watched it
        touched = [i for i, t in enumerate(tk) if t[0] <= 120 and t[3]]
        after = sum(seen[touched[0]:]) if touched else 0
        res.update(exposed=bool(touched) and after >= MIN_TICKS, first_touch=touched[0] if touched else None, reason=f'touched={bool(touched)}, in view after contact {after} ticks'); return res
    trigger = TRIGGER.get(family, TRIGGER_DEFAULT)
    if code in {'T1', 'T2', 'T3'}:   # seen, then away (far or out of view for 1 s), then seen again
        first = first_seen
        ok = False; away_at = None; back = 0
        if first is not None:
            away_run = 0
            for i in range(first, len(tk)):
                away = tk[i][0] > trigger or not seen[i]
                if away_at is None:
                    away_run = away_run + 1 if away else 0
                    if away_run >= 20: away_at = i
                elif seen[i]:
                    back += 1
            ok = back >= MIN_TICKS
        if code == 'T3' and not ok:   # sustained observation also counts (fan / door / day-night)
            ok = n_seen >= 40
        res.update(exposed=ok, away_at=away_at, back_ticks=back, reason=f'seen {n_seen}, away_at={away_at}, back in view {back} ticks'); return res
    if code == 'V1':   # two viewing directions >= 90 deg apart, or centred view
        dirs = [math.degrees(math.atan2(focus[1] - (p.get('pos_cm') or [0, 0])[1], focus[0] - (p.get('pos_cm') or [0, 0])[0])) for p in poses]
        bins = collections.Counter(int(((dirs[i] % 360) // 30)) for i in range(len(tk)) if seen[i])
        good = [b for b, n in bins.items() if n >= MIN_TICKS]
        spread = max((min(abs(a - b) * 30, 360 - abs(a - b) * 30) for a in good for b in good), default=0)
        centred = sum(1 for i, t in enumerate(tk) if seen[i] and t[1] >= 0.97)
        res.update(exposed=spread >= 90 or centred >= MIN_TICKS, dir_spread_deg=spread, centred_ticks=centred, reason=f'view directions spread {spread} deg, centred {centred} ticks'); return res
    if code == 'V2':   # near and far views
        near = sum(1 for i, t in enumerate(tk) if seen[i] and t[0] <= 600)
        far_tk = per_tick(poses, focus, 2500)
        far = sum(1 for t in far_tk if t[2] and t[0] >= 1000)
        res.update(exposed=near >= MIN_TICKS and far >= MIN_TICKS, near_ticks=near, far_ticks=far, reason=f'near {near}, far {far} ticks'); return res
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tag', default='vla-ue-v1')
    ap.add_argument('--profiles', default='reports/ue-aws-profiles-20260918.json')
    ap.add_argument('--out', default=None)
    a = ap.parse_args()
    prof = json.load(open(a.profiles))['tasks']
    base = pathlib.Path('runs') / a.tag
    rows = []
    for ep in sorted(p for p in base.iterdir() if p.is_dir() and (p / 'meta.json').exists()):
        tid = ep.name; task = prof.get(tid)
        if not task: print('no profile for', tid); continue
        poses = load_poses(ep); family = task['family']
        raw = task['task'].get('subcategory') or ''
        code = CODE.get(raw, raw if len(raw) == 2 else raw[:2].upper())
        r = score(task, code, poses, family)
        pts = [p.get('pos_cm') for p in poses if p.get('pos_cm')]
        path = sum(math.dist(pts[i][:2], pts[i - 1][:2]) for i in range(1, len(pts)))
        cells = len({(int(p[0] // 200), int(p[1] // 200)) for p in pts})
        oob = sum(1 for p in poses if 'out_of_bounds' in str(p.get('result')))
        r.update(task=tid, family=family, subcategory=raw, ticks=len(poses), path_m=round(path / 100, 1), cells_2m=cells,
                 w_held=round(sum('KeyW' in (p.get('keys') or []) for p in poses) / max(1, len(poses)), 2), oob_results=oob)
        rows.append(r)
    (base / 'exposure.json').write_text(json.dumps(rows, indent=1))
    n = len(rows); ex = sum(1 for r in rows if r.get('exposed'))
    lines = [f'# VLA exposure (heuristic) - {a.tag}', '', f'{ex}/{n} episodes exposed the target.', '',
             '| code | exposed | n |', '|---|---|---|']
    byc = collections.defaultdict(lambda: [0, 0])
    for r in rows: byc[r['code']][1] += 1; byc[r['code']][0] += bool(r.get('exposed'))
    for c in sorted(byc): lines.append(f'| {c} | {byc[c][0]} | {byc[c][1]} |')
    byf = collections.defaultdict(lambda: [0, 0])
    for r in rows: byf[r['family']][1] += 1; byf[r['family']][0] += bool(r.get('exposed'))
    lines += ['', '| family | exposed | n |', '|---|---|---|'] + [f'| {f} | {byf[f][0]} | {byf[f][1]} |' for f in sorted(byf)]
    lines += ['', '| task | code | exposed | seen ticks | first seen | min dist m | path m | cells 2m | W held | note |', '|---|---|---|---|---|---|---|---|---|---|']
    for r in rows:
        lines.append(f"| {r['task']} | {r['code']} | {'yes' if r.get('exposed') else 'no'} | {r.get('seen_ticks')} | {r.get('first_seen')} | "
                     f"{(r.get('min_dist_cm') or 0) / 100:.1f} | {r['path_m']} | {r['cells_2m']} | {r['w_held']} | {r.get('reason', '')} |")
    md = '\n'.join(lines) + '\n'
    if a.out: pathlib.Path(a.out).write_text(md)
    print(md if n <= 40 else '\n'.join(lines[:12 + len(byf) + 6]))
    print(f'wrote {base / "exposure.json"}' + (f' and {a.out}' if a.out else ''))


if __name__ == '__main__':
    main()
