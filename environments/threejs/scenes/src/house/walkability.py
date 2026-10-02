#!/usr/bin/env python3
"""Walkability check of the standalone house build: per room, the share of free floor cells
reachable from the spawn for a player of radius r (AABB colliders as in the game), plus the
isolated pockets. usage: walkability.py <html> [--out map.png] [--radius 0.22 0.27]
"""
import argparse
import json
import pathlib
from collections import deque

import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("html")
ap.add_argument("--out", default=None)
ap.add_argument("--radius", type=float, nargs="+", default=[0.22, 0.27])
a = ap.parse_args()
from playwright.sync_api import sync_playwright
ARGS = ["--no-sandbox", "--disable-dev-shm-usage", "--enable-webgl", "--ignore-gpu-blocklist", "--use-angle=gl-egl"]
with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=ARGS)
    pg = b.new_page(viewport={"width": 640, "height": 400})
    pg.goto("file://" + str(pathlib.Path(a.html).resolve()), wait_until="load", timeout=240000)
    pg.wait_for_function("window.BenchmarkWorld && window.BenchmarkWorld.ready===true", timeout=180000)
    data = pg.evaluate("""() => { const w=window.BenchmarkWorld; return { colliders: w.colliders.map(c=>({min:[c.box.min.x,c.box.min.z], max:[c.box.max.x,c.box.max.z], floor:c.floor})), rooms: w.rooms }; }""")
    b.close()
step = 0.05
xs = np.arange(-6.55, 6.55, step); zs = np.arange(-4.55, 4.55, step)


def free_map(floor, r):
    X, Z = np.meshgrid(xs, zs); free = np.ones_like(X, dtype=bool)
    for c in data["colliders"]:
        if c["floor"] != 2 and c["floor"] != floor:
            continue
        (x0, z0), (x1, z1) = c["min"], c["max"]
        free &= ~((X + r > x0) & (X - r < x1) & (Z + r > z0) & (Z - r < z1))
    return free


def components(free):
    lab = -np.ones(free.shape, int); n = 0; sizes = []
    for j in range(free.shape[0]):
        for i in range(free.shape[1]):
            if free[j, i] and lab[j, i] < 0:
                q = deque([(j, i)]); lab[j, i] = n; cnt = 0
                while q:
                    y, x = q.popleft(); cnt += 1
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        Y, Xx = y + dy, x + dx
                        if 0 <= Y < free.shape[0] and 0 <= Xx < free.shape[1] and free[Y, Xx] and lab[Y, Xx] < 0:
                            lab[Y, Xx] = n; q.append((Y, Xx))
                sizes.append(cnt); n += 1
    return lab, sizes


rows = []
figs = []
for floor in (0, 1):
    for r in a.radius:
        free = free_map(floor, r); lab, sizes = components(free); main = int(np.argmax(sizes))
        figs.append((floor, r, free, lab, main))
        for rm in data["rooms"]:
            if rm["level"] != floor:
                continue
            i0, i1 = int((rm["x0"] - xs[0]) / step), int((rm["x1"] - xs[0]) / step)
            j0, j1 = int((rm["z0"] - zs[0]) / step), int((rm["z1"] - zs[0]) / step)
            sub = lab[max(j0, 0):j1, max(i0, 0):i1]; fr = free[max(j0, 0):j1, max(i0, 0):i1]
            nfree, nmain = fr.sum(), (sub == main).sum()
            pockets = sorted([sizes[k] * step * step for k in set(sub[(sub >= 0) & (sub != main)].tolist())], reverse=True)[:3]
            rows.append((floor, r, rm["id"], nmain / max(nfree, 1) * 100, [round(v, 2) for v in pockets]))
            print(f"floor {floor} r={r} {rm['id']:9s} reachable {nmain / max(nfree, 1) * 100:5.0f}% of free  pockets(m2) {[round(v, 2) for v in pockets]}")
if a.out:
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, len(a.radius), figsize=(10 * len(a.radius), 14), squeeze=False)
    for k, (floor, r, free, lab, main) in enumerate(figs):
        ax = axes[floor][k % len(a.radius)]
        show = np.where(lab == main, 1.0, np.where(free, 0.5, 0.0))
        ax.imshow(show, origin="lower", extent=[xs[0], xs[-1], zs[0], zs[-1]], cmap="gray", interpolation="nearest", vmin=0, vmax=1)
        for rm in data["rooms"]:
            if rm["level"] != floor:
                continue
            ax.add_patch(plt.Rectangle((rm["x0"], rm["z0"]), rm["x1"] - rm["x0"], rm["z1"] - rm["z0"], fill=False, ec="tab:blue", lw=0.8))
            ax.text(rm["x0"] + 0.1, rm["z1"] - 0.35, rm["id"], color="tab:blue", fontsize=9)
        ax.set_title(f"floor {floor} r={r}: white = reachable, grey = isolated pocket"); ax.grid(True, alpha=.3)
    plt.savefig(a.out, dpi=55, bbox_inches="tight")
    print("map:", a.out)
