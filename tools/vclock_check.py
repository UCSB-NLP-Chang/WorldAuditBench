#!/usr/bin/env python3
"""Check the virtual clock of the standalone pages (`?vclock=1`): a tick must advance exactly dt of simulated time,
nothing may move between ticks, and a repeated tick sequence must reproduce the same displacement.

usage: .venv/bin/python tools/vclock_check.py [--configs wt05-airwall,ct02-clip,af06-hole,wl01-float,sp04-doublespawn]
"""
import argparse, json, sys, time
sys.path.insert(0, '/home/ubuntu/game-auditing')
from harness.bridge import Bridge

def seq(br, n, act):
    p0 = br.page.evaluate("() => window.__env.state().pos"); moved = 0.0
    for _ in range(n):
        r = br.page.evaluate("(a) => window.__env.tick(a, 50)", act); moved += r['moved']
    p1 = br.page.evaluate("() => window.__env.state().pos")
    return round(moved, 3), [round(b - a, 3) for a, b in zip(p0, p1)], r

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--configs', default='wt05-airwall,ct02-clip,af06-hole,wl01-float,sp04-doublespawn'); a = ap.parse_args()
    out = {}
    with Bridge(gpu='gl-egl') as br:
        br.page.set_default_timeout(240_000)
        for cfg in a.configs.split(','):
            res = {}
            for mode in ('vclock', 'wall'):
                extra = {'vclock': 1} if mode == 'vclock' else None
                t0 = time.time(); br.open_env(cfg, seed=5, extra=extra); br.page.evaluate("() => window.__env.enable()")
                res[mode] = {'load_s': round(time.time() - t0, 1)}
                # 20 ticks x 50 ms holding W = 1.0 s of simulated walking
                m1, d1, r = seq(br, 20, {'keys': ['KeyW']}); t_sim1 = br.page.evaluate("() => window.__env.probe().simT")
                time.sleep(1.0)   # real second with no ticks: the world must stand still under the virtual clock
                p_after = br.page.evaluate("() => window.__env.state().pos"); t_sim2 = br.page.evaluate("() => window.__env.probe().simT")
                m2, d2, _ = seq(br, 20, {'keys': ['KeyW']})
                yaw0 = br.page.evaluate("() => window.__env.state().yaw"); seq(br, 10, {'mouseDx': 60}); yaw1 = br.page.evaluate("() => window.__env.state().yaw")
                res[mode].update({'walk1_m': m1, 'walk2_m': m2, 'simT_after_walk1': t_sim1, 'simT_after_real_sleep': t_sim2,
                                  'pos_drift_during_sleep': [round(b - a, 3) for a, b in zip([v for v in r['pos']], p_after)], 'yaw_change_10_ticks_dx60': round((yaw1 - yaw0 + 540) % 360 - 180, 1)})
            out[cfg] = res
            v = res['vclock']
            print(f"{cfg:18s} vclock: walk 1s = {v['walk1_m']} m then {v['walk2_m']} m | simT {v['simT_after_walk1']} -> {v['simT_after_real_sleep']} after a real 1 s sleep | drift {v['pos_drift_during_sleep']} | yaw {v['yaw_change_10_ticks_dx60']} deg"
                  f"\n{'':18s} wall  : walk 1s = {res['wall']['walk1_m']} m then {res['wall']['walk2_m']} m | simT {res['wall']['simT_after_walk1']} -> {res['wall']['simT_after_real_sleep']} | yaw {res['wall']['yaw_change_10_ticks_dx60']} deg")
    json.dump(out, open('/tmp/claude-1000/-home-ubuntu/dcc07dd4-019f-4e2a-b25b-c51dce188770/scratchpad/vclock_check.json', 'w'), indent=1)

if __name__ == '__main__':
    main()
