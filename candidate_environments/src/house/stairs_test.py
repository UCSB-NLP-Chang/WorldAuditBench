#!/usr/bin/env python3
"""Stair walks in the rebuilt house (run after build.py): the player must never change floor except by walking the
staircase. Usage: .venv/bin/python candidate_environments/src/house/stairs_test.py"""
import pathlib, sys
from playwright.sync_api import sync_playwright
REPO = pathlib.Path(__file__).resolve().parents[3]
f = str(REPO / 'candidate_environments/09_sims_house_builder_constrained.html')
ARGS = ["--no-sandbox", "--disable-dev-shm-usage", "--enable-webgl", "--ignore-gpu-blocklist", "--use-angle=gl-egl"]
# (label, start x,y,z, yaw, seconds, expected floor at the end, expected |y - expectedY| < 0.3 or None)
cases = [("laundry door -> east into the top end of the stairs", -2.0, 0, -2.0, -1.57, 2.5, 0, 0.0),
         ("hall -> north along the stair strip from the top side", -1.2, 0, -3.5, 0.0, 2.5, 0, 0.0),
         ("bottom of the stairs -> walk up", -1.25, 0, 3.2, 0.0, 6.0, 1, 3.0),
         ("landing -> walk down the stairs", -1.25, 3.0, -2.6, 3.14, 6.0, 0, 0.0),
         ("landing over the headroom slab (south end of the stair strip)", -1.25, 3.0, 2.6, 0.0, 1.5, 1, 3.0),
         ("landing east of the stairwell -> west into the balustrade", -0.3, 3.0, 0.5, 1.57, 2.0, 1, 3.0)]
with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=ARGS); pg = b.new_page(viewport={'width': 960, 'height': 600})
    pg.goto('file://' + f, wait_until='load', timeout=300000)
    for _ in range(120):
        if pg.evaluate("() => window.BenchmarkWorld && window.BenchmarkWorld.ready"): break
        pg.wait_for_timeout(500)
    pg.mouse.click(480, 300); pg.wait_for_timeout(300)
    ok = True
    for label, x, y, z, yaw, sec, floor, ey in cases:
        pg.evaluate("([x,y,z,yaw]) => { const B=window.BenchmarkWorld; B.teleport(x,y,z); B.setView(yaw,0); }", [x, y, z, yaw])
        pg.wait_for_timeout(300)
        pg.keyboard.down('KeyW'); track = []
        for _ in range(int(sec * 10)):
            pg.wait_for_timeout(100)
            st = pg.evaluate("() => { const s = window.BenchmarkWorld.getState(); return [s.floor, +s.position[1].toFixed(2)]; }")
            track.append(st)
        pg.keyboard.up('KeyW'); pg.wait_for_timeout(300)
        st = pg.evaluate("() => { const s = window.BenchmarkWorld.getState(); return { floor: s.floor, pos: s.position.map(v => +v.toFixed(2)) }; }")
        # a jump of more than one riser (0.19) between consecutive samples = teleport
        jumps = [abs(track[i][1] - track[i-1][1]) for i in range(1, len(track))]
        good = st['floor'] == floor and abs(st['pos'][1] - ey) < 0.3 and max(jumps) < 0.45
        ok &= good
        print(("OK " if good else "BAD"), f"{label:<62} floor={st['floor']} pos={st['pos']} maxStep={max(jumps):.2f}")
    b.close()
print("ALL OK" if ok else "FAILURES")
