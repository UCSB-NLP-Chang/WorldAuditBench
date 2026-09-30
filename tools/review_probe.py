#!/usr/bin/env python3
"""Behaviour probes through the harness contract (window.__env) of a standalone page or a core.js config.
usage: probe.py --config <name> --steps '<json list>' --out <dir> [--gpu vulkan]
steps: {"teleport":[x,y|null,z]} | {"face":[tx,tz]} | {"act":{...}} | {"shot":"name"} | {"eval":"js"} | {"sleep":s} | {"state":1}
"""
import argparse, base64, json, math, pathlib, sys, time
sys.path.insert(0, '/home/ubuntu/game-auditing')
from harness.bridge import Bridge

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--config', required=True); ap.add_argument('--steps', required=True)
    ap.add_argument('--out', required=True); ap.add_argument('--gpu', default='vulkan'); ap.add_argument('--seed', type=int, default=5)
    a = ap.parse_args(); out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    log = []
    with Bridge(gpu=a.gpu) as br:
        br.page.set_default_timeout(180_000)
        meta = br.open_env(a.config, seed=a.seed); log.append({'meta': meta}); time.sleep(1.0)
        for i, st in enumerate(json.loads(a.steps)):
            if 'teleport' in st:
                x, y, z = st['teleport']
                br.page.evaluate("([x,y,z]) => window.BenchmarkWorld.teleport(x, y, z)", [x, y, z]); time.sleep(0.5)
            if 'face' in st:
                s = br.state(); tx, tz = st['face']; px, pz = s['pos'][0], s['pos'][2]
                want = math.degrees(math.atan2(-(tx - px), -(tz - pz))) % 360; cur = s['yaw'] % 360
                d = (cur - want + 180) % 360 - 180   # turn right by d
                br.act({'action': 'turn', 'deg': d}); log.append({'face': [want, cur, d]})
            if 'act' in st:
                r = br.act(st['act']); fr = r.pop('frames', []); r.pop('film', None)
                if fr: (out / f"step{i}_final.jpg").write_bytes(base64.b64decode(fr[-1].split(',', 1)[1]))
                log.append({'act': st['act'], 'result': r}); print(i, st['act'], {k: r.get(k) for k in ('moved', 'respawned', 'pos', 'yaw', 'simElapsed')})
            if 'shot' in st: br.page.screenshot(path=str(out / f"{st['shot']}.png"))
            if 'eval' in st: v = br.page.evaluate(st['eval']); log.append({'eval': v}); print(i, 'eval', json.dumps(v)[:300])
            if 'sleep' in st: time.sleep(st['sleep'])
            if 'state' in st: s = br.state(); log.append({'state': s}); print(i, 'state', s)
    (out / 'log.json').write_text(json.dumps(log, indent=1))

if __name__ == '__main__':
    main()
