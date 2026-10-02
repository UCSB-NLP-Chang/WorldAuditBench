#!/usr/bin/env python3
"""Walk the player in the rebuilt house (run after build.py): the boundary warning must stay silent inside (walls, closed doors)
and fire only when the player pushes into one of the two shut exterior doors (the player never leaves the house).
Usage: .venv/bin/python environments/threejs/scenes/src/house/boundary_test.py [screenshot_dir]"""
import pathlib, sys
from playwright.sync_api import sync_playwright
REPO = pathlib.Path(__file__).resolve().parents[5]
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path('house_boundary_shots')
ARGS = ["--no-sandbox", "--disable-dev-shm-usage", "--enable-webgl", "--ignore-gpu-blocklist", "--use-angle=gl-egl"]
f = str(REPO / 'environments/threejs/scenes/09_sims_house_builder_constrained.html')
# (label, start x,z, yaw, expected warning?)  yaw 3.14 walks toward +z (south), 0 toward -z, 1.57 toward -x, -1.57 toward +x
cases = [("inside: along the south wall, away from the door", 4.0, 4.3, 3.14, False),
         ("inside: into the east wall", 6.4, 0.0, -1.57, False),
         ("inside: into the west wall", -6.4, 2.0, 1.57, False),
         ("inside: living room south wall", -4.0, 4.3, 3.14, False),
         ("inside: kitchen north wall, away from the glass door", 4.0, -4.4, 0.0, False),
         ("front door: pushing into the shut door", 0.0, 3.9, 3.14, True),
         ("glass door: pushing into the shut door", 0.7, -3.9, 0.0, True)]
OUT.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=ARGS); pg = b.new_page(viewport={'width': 960, 'height': 600})
    pg.on('console', lambda m: print('console:', m.type, m.text[:160]) if m.type in ('error', 'warning') else None)
    pg.on('crash', lambda: print('PAGE CRASHED'))
    print('loading', flush=True)
    pg.goto('file://' + f, wait_until='load', timeout=300000)
    for _ in range(120):
        if pg.evaluate("() => window.BenchmarkWorld && window.BenchmarkWorld.ready"): break
        pg.wait_for_timeout(500)
    try: pg.get_by_text('进入', exact=False).first.click(timeout=2000)
    except Exception: pass
    pg.mouse.click(480, 300); pg.wait_for_timeout(500)
    print('ready', flush=True)
    print("bounds:", pg.evaluate("() => JSON.stringify(window.BenchmarkBoundary.bounds)"))
    ok = True
    for label, x, z, yaw, expect in cases:
        pg.evaluate("([x,z,yaw]) => { const B=window.BenchmarkWorld; B.teleport(x,0,z); B.setView(yaw,0); document.getElementById('benchmark-boundary-warning').classList.remove('is-visible'); }", [x, z, yaw])
        pg.wait_for_timeout(300)
        pg.keyboard.down('KeyW'); seen = False
        for _ in range(20):
            pg.wait_for_timeout(100)
            seen = seen or pg.evaluate("() => document.getElementById('benchmark-boundary-warning').classList.contains('is-visible')")
        pg.keyboard.up('KeyW'); pg.wait_for_timeout(200)
        pos = pg.evaluate("() => window.BenchmarkWorld.getState().position.map(v => +v.toFixed(2))")
        pg.screenshot(path=str(OUT / f'case{cases.index((label, x, z, yaw, expect))}.png'))
        inside = abs(pos[0]) <= 6.7 and abs(pos[2]) <= 4.7
        flag = "OK " if (seen == expect and inside) else "BAD"; ok &= (seen == expect and inside)
        print(f"{flag} {label:<55} warning={seen!s:<5} end={pos}")
    b.close()
print("ALL OK" if ok else "FAILURES")
