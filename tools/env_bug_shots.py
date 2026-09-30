#!/usr/bin/env python3
"""Catalogue sheet for a standalone-page bug suite: load every case with `?bug=<id>`, put the camera a few metres from
the judge answer's `at` looking at it, screenshot, and stitch a labelled sheet.  Also writes per-case PNGs.

usage: env_bug_shots.py <env: sketch|fable|cottage> <out_dir> [--extra "&seed=7"]
"""
import argparse, json, math, pathlib, sys
from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw

REPO = pathlib.Path(__file__).resolve().parents[1]
ENVS = {
    "sketch": dict(page="candidate_environments/03_sketchbook_airfield_constrained.html", prefix="af", eye=1.65, dist=4.5,
                   ready="() => !!(window.BenchmarkWorld && window.BenchmarkWorld.ready)"),
    "fable": dict(page="candidate_environments/13_beyond_fable_wilderness_constrained.html", prefix="wl", eye=1.9, dist=6.0,
                  ready="() => !!(window.BenchmarkWorld && window.BenchmarkWorld.ready)"),
    "cottage": dict(page="candidate_environments/01_mistwood_cottage_constrained.html", prefix="ct", eye=1.1, dist=2.6,
                    ready="() => !!(window.BenchmarkWorld && window.BenchmarkWorld.ready && window.BenchmarkWorld.bugRuntime)"),
}
ARGS = ["--no-sandbox", "--disable-dev-shm-usage", "--enable-webgl", "--ignore-gpu-blocklist", "--use-angle=gl-egl"]
# per-env view setter: camera at `cam` looking at `at` (uses the page's benchmark API)
VIEW_JS = {
    "sketch": """([cx, cy, cz, ax, ay, az]) => { const B = window.BenchmarkWorld; B.dismissModal(); B.setHud(false); B.setFirstPerson(true);
        B.teleport(cx, cy, cz); const dx = ax - cx, dz = az - cz; const theta = Math.atan2(-dx, -dz) * 180 / Math.PI;
        const phi = -Math.atan2(ay - (cy + 1.05), Math.hypot(dx, dz)) * 180 / Math.PI; B.setView(theta, Math.max(-80, Math.min(80, phi))); return B.getState().position; }""",
    "fable": """([cx, cy, cz, ax, ay, az]) => { const B = window.BenchmarkWorld; B.dismissOverlay(); B.setHud(false); B.setHeadless(true);
        B.teleport(cx, null, cz); const p = B.camera.position; const dx = ax - p.x, dz = az - p.z; const yaw = Math.atan2(-dx, -dz);
        const pitch = Math.atan2(ay - p.y, Math.hypot(dx, dz)); B.setView(yaw, Math.max(-1.4, Math.min(1.4, pitch))); return p.toArray(); }""",
    "cottage": """([cx, cy, cz, ax, ay, az]) => { const B = window.BenchmarkWorld; B.setFirstPerson(true); B.teleport(cx, null, cz);
        const p = B.camera.position; const dx = ax - p.x, dz = az - p.z; const theta = Math.atan2(-dx, -dz);   // forward = (-sin t, -cos t)
        const phi = Math.PI / 2 + Math.atan2(ay - p.y, Math.hypot(dx, dz)); B.setView(theta, Math.max(0.35, Math.min(2.6, phi))); return p.toArray(); }""",
}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("env"); ap.add_argument("out"); ap.add_argument("--extra", default=""); ap.add_argument("--cases", default="")
    ap.add_argument("--w", type=int, default=800); ap.add_argument("--h", type=int, default=500); ap.add_argument("--wait", type=int, default=2500)
    a = ap.parse_args(); E = ENVS[a.env]; out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    cfgs = sorted((REPO / "env" / "configs").glob(f"{E['prefix']}[0-9][0-9]-*.answers.json"))
    if a.cases:
        keep = set(a.cases.split(",")); cfgs = [c for c in cfgs if c.name.split("-")[0] in keep]
    tiles = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=ARGS)
        for c in cfgs:
            name = c.name.replace(".answers.json", ""); ans = json.loads(c.read_text())[0]
            view = json.loads(c.with_suffix("").with_suffix(".json").read_text()).get("view")   # optional {cam:[x,y,z]} override in the config
            pg = b.new_page(viewport={"width": a.w, "height": a.h})
            pg.goto(f"file://{REPO / E['page']}?bug={name}&benchmark=1{a.extra}", wait_until="load", timeout=300000)
            for _ in range(240):
                if pg.evaluate(E["ready"]): break
                pg.wait_for_timeout(500)
            pg.wait_for_timeout(a.wait)
            ax, ay, az = ans["at"]
            if view and view.get("cam"):
                cx, cy, cz = view["cam"]
            else:
                ang = math.radians(view.get("deg", 200)) if view else math.radians(200)   # default: from the south-west
                cx, cz = ax + math.sin(ang) * E["dist"], az + math.cos(ang) * E["dist"]; cy = ay - 0.3 + E["eye"]
            try:
                pos = pg.evaluate(VIEW_JS[a.env], [cx, cy, cz, ax, ay, az])
            except Exception as e:
                print(name, "view error", str(e)[:120]); pos = None
            pg.wait_for_timeout(1200)
            png = out / f"{name}.png"; pg.screenshot(path=str(png)); pg.close()
            print("shot", name, "cam", [round(v, 1) for v in pos] if pos else None, "at", ans["at"])
            tiles.append((name, ans["name"], png))
        b.close()
    cols = 4; tw, th = 480, 300
    sheet = Image.new("RGB", (cols * tw, math.ceil(len(tiles) / cols) * th), (20, 20, 20)); d = ImageDraw.Draw(sheet)
    for i, (name, label, png) in enumerate(tiles):
        im = Image.open(png).convert("RGB").resize((tw, th)); x, y = (i % cols) * tw, (i // cols) * th; sheet.paste(im, (x, y))
        d.rectangle([x, y, x + tw, y + 22], fill=(0, 0, 0)); d.text((x + 6, y + 5), f"{name}: {label}", fill=(255, 255, 255))
    sheet.save(out / "catalog.jpg", quality=88); print("sheet", out / "catalog.jpg", len(tiles), "tiles")


if __name__ == "__main__":
    main()
