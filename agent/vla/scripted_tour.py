"""Setting 3: oracle-routed exposure. A scripted walker executes a per-case route that
deterministically triggers/exposes the planted bug (the perfected version of "give the
explorer a navigation instruction that leads through the bug" - the P2P VLA cannot follow
instructions, per the 3-arm ablation, so the route is executed by script). Recordings are
short and noise-free; the same VQA auditor + judge then measure the audit channel's ceiling:
exposure is ~100% by construction, so I|E is isolated.

Usage: .venv/bin/python -m agent.vla.scripted_tour --tag tour-v1
Output format identical to vla_explore episodes (frames/poses/meta/video), so
judge/vqa_audit.py works unchanged.
"""
import argparse
import base64
import json
import math
from pathlib import Path

from PIL import Image

from agent.vla.bridge import Bridge
from agent.vla.runner import REPO

DT_MS = 50
REC_EVERY = 10
PX_PER_DEG = 600 * math.pi / 180 / 1  # mouse px per radian is 600; per degree:
PX_PER_DEG = 600 * math.pi / 180


def wrap(a):
    while a > 180: a -= 360
    while a < -180: a += 360
    return a


class Tour:
    """Executes route ops over the continuous tick API and records like vla_explore."""

    def __init__(self, br, out_dir):
        self.br, self.out = br, out_dir
        self.t = 0
        self.poses, self.frames = [], []

    def tick(self, keys=(), dx=0, dy=0):
        r = self.br.page.evaluate("(a) => window.__env.tick(a.act, a.dt)",
                                  {"act": {"keys": list(keys), "mouseDx": dx, "mouseDy": dy},
                                   "dt": DT_MS})
        self.poses.append({"t": self.t, "pos": r["pos"], "yaw": r["yaw"], "pitch": r["pitch"],
                           "moved": r["moved"], "respawned": r["respawned"],
                           "keys": list(keys), "dx": dx, "dy": dy, "recovery": False})
        if self.t % REC_EVERY == 0:
            fn = f"f{self.t:05d}.jpg"
            (self.out / fn).write_bytes(base64.b64decode(r["frame"].split(",", 1)[1]))
            self.frames.append(fn)
        self.t += 1
        return r

    def _steer(self, tx, tz, ty=None):
        """One-tick mouse deltas toward facing (tx,tz) [and pitch toward ty]."""
        p = self.poses[-1] if self.poses else None
        if p is None:
            st = self.br.state()
            pos, yaw, pitch = st["pos"], st["yaw"], st["pitch"]
        else:
            pos, yaw, pitch = p["pos"], p["yaw"], p["pitch"]
        dxw, dzw = tx - pos[0], tz - pos[2]
        theta = math.degrees(math.atan2(-dxw, -dzw))
        err = wrap(yaw - theta)
        mdx = max(-150, min(150, err * PX_PER_DEG))
        mdy = 0
        if ty is not None:
            phi = math.degrees(math.atan2(ty - pos[1], math.hypot(dxw, dzw)))
            perr = pitch - phi
            mdy = max(-100, min(100, perr * PX_PER_DEG))
        return mdx, mdy, abs(err)

    # ---- ops ----
    def face(self, tx, ty, tz, ticks=14):
        for _ in range(ticks):
            mdx, mdy, err = self._steer(tx, tz, ty)
            self.tick((), mdx, mdy)
            if err < 1.5 and abs(mdy) < 3:
                break

    def goto(self, tx, tz, tol=0.45, timeout_s=14):
        for _ in range(int(timeout_s * 1000 / DT_MS)):
            p = self.poses[-1]["pos"] if self.poses else self.br.state()["pos"]
            if math.hypot(tx - p[0], tz - p[2]) < tol:
                return True
            mdx, _, err = self._steer(tx, tz)
            self.tick(("KeyW",) if err < 30 else (), mdx, 0)
        return False

    def push(self, tx, tz, sec):
        """Hold W toward a point regardless of progress (demonstrates blockage)."""
        for _ in range(int(sec * 1000 / DT_MS)):
            mdx, _, _ = self._steer(tx, tz)
            self.tick(("KeyW",), mdx, 0)

    def dwell(self, sec, tx=None, ty=None, tz=None):
        for _ in range(int(sec * 1000 / DT_MS)):
            if tx is not None:
                mdx, mdy, _ = self._steer(tx, tz, ty)
                self.tick((), mdx, mdy)
            else:
                self.tick(())

    def spin(self, deg):
        n = max(1, int(abs(deg) / 13))
        px = deg * PX_PER_DEG / n
        for _ in range(n):
            self.tick((), max(-150, min(150, px)), 0)


# ---- per-case oracle routes (spawn: west end (-8.5,-0.3) facing east) ----
def r_approach_dwell(t, x, z, y=0.6, dwell=3.0, standoff=2.6):
    """Walk to a mid-distance viewpoint and dwell: the carrier AND its neighboring siblings
    stay in frame (internal-consistency context); extreme close-ups distort perception."""
    vz = z + (standoff if z < -0.3 else -standoff)
    t.goto(x, vz, tol=0.5)
    t.face(x, y, z)
    t.dwell(dwell, x, y, z)

ROUTES = {
    "sp01-float":   lambda t: r_approach_dwell(t, 0.95, 1.23, y=0.9),
    "sp02-clip":    lambda t: r_approach_dwell(t, 6.67, 1.23, y=0.2),
    "sp03-scale":   lambda t: r_approach_dwell(t, 0.96, -1.78, y=0.8),
    "sp04-doublespawn": lambda t: (r_approach_dwell(t, 6.67, -1.78, y=0.5, standoff=2.2),
                                   t.goto(5.6, -1.2, tol=0.4), t.face(6.67, 0.3, -1.78),
                                   t.dwell(2.0, 6.67, 0.3, -1.78)),
    "sp05-airwall": lambda t: (t.goto(0.5, -0.3), t.face(9.5, 1.6, -0.3),
                               t.push(9.5, -0.3, 4.0), t.spin(30), t.spin(-30),
                               t.push(9.5, -0.3, 2.5)),
    "sp06-hole":    lambda t: (t.face(9.5, 1.6, -0.3), t.push(9.5, -0.3, 6.0),
                               t.face(9.5, 1.6, -0.3), t.push(9.5, -0.3, 6.0)),
    "sp07-ghostdrape": lambda t: (t.goto(2.44, -0.6), t.face(2.44, 1.0, 1.56),
                                  t.push(2.44, 2.6, 3.5), t.spin(180),
                                  t.dwell(2.0, 2.44, 1.0, 1.56), t.push(2.44, -0.6, 3.5)),
    "sp08-jitter":  lambda t: r_approach_dwell(t, -1.95, 1.22, y=0.5, dwell=6.0),
    "sp09-magenta": lambda t: r_approach_dwell(t, -1.95, -1.8, y=0.3),   # v3: magenta pot
    "sp10-backcull": lambda t: (t.goto(7.6, -0.3), t.goto(7.6, 2.8), t.goto(0.6, 2.8),
                                t.goto(-0.4, 2.9, tol=0.6), t.face(-0.49, 1.1, 1.61),
                                t.dwell(3.0, -0.49, 1.1, 1.61),
                                t.face(-3.47, 1.1, 1.56), t.dwell(1.5, -3.47, 1.1, 1.56),
                                t.face(-0.49, 1.1, 1.61), t.dwell(1.5, -0.49, 1.1, 1.61)),
    "sp11-xray":    lambda t: (t.goto(-5.2, -0.3), t.face(-1.95, 0.4, -1.8),
                               t.dwell(2.0, -1.95, 0.4, -1.8), t.goto(-3.6, -0.6),
                               t.face(-1.95, 0.4, -1.8), t.dwell(2.5, -1.95, 0.4, -1.8)),
    "sp12-unload":  lambda t: (r_approach_dwell(t, 0.95, 1.23, y=0.5, dwell=1.5),
                               t.goto(-8.4, -0.3), t.spin(180),         # leave the cell (>9m)
                               t.goto(-1.2, -0.4), t.face(0.95, 0.5, 1.23),
                               t.dwell(2.5, 0.95, 0.5, 1.23)),
    "sp13-statereset": lambda t: (r_approach_dwell(t, 6.67, 1.23, y=0.5, dwell=1.5),
                                  t.goto(-3.5, -0.3), t.spin(180),      # leave (>9m), come back
                                  t.goto(4.4, 0.2), t.face(6.67, 0.5, 1.23),
                                  t.dwell(2.0, 6.67, 0.5, 1.23),
                                  t.face(6.67, 0.5, -1.17), t.dwell(1.5, 6.67, 0.5, -1.17)),
    "sp14-lodpop":  lambda t: (t.goto(-4.6, -0.35), t.face(2.44, 1.1, 1.56),
                               t.dwell(2.0, 2.44, 1.1, 1.56),           # blocky from ~7m
                               t.goto(0.8, 0.2), t.face(2.44, 1.1, 1.56),
                               t.dwell(1.5, 2.44, 1.1, 1.56),           # popped sharp at ~2m
                               t.goto(-4.6, -0.35), t.face(2.44, 1.1, 1.56),
                               t.dwell(1.5, 2.44, 1.1, 1.56)),          # blocky again
    "sp15-spawnpile": lambda t: (t.goto(7.6, -0.3), t.goto(7.6, 2.6, tol=0.5),   # v4: into the north-east aisle corner
                                  t.face(7.9, 0.5, 4.0), t.dwell(2.0, 7.9, 0.5, 4.0),
                                  t.goto(6.4, 3.4, tol=0.5), t.face(7.9, 0.5, 4.0), t.dwell(2.5, 7.9, 0.5, 4.0)),
}
# clean control: 4 matched routes on the untouched hall (same footage statistics)
CLEAN_ROUTES = [ROUTES["sp01-float"], ROUTES["sp06-hole"],
                ROUTES["sp10-backcull"], ROUTES["sp14-lodpop"]]


def run_episode(br, config, route, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    br.open_env(config, seed=5)
    br.page.evaluate("() => window.__env.enable()")
    t = Tour(br, out_dir)
    t.tick(())
    route(t)
    probe = br.probe()
    (out_dir / "poses.jsonl").write_text("\n".join(json.dumps(p) for p in t.poses))
    meta = dict(task=f"tour_{config}", config=config, seed=5, kind="scripted_tour",
                model="scripted-oracle-route", ticks=t.t, dt_ms=DT_MS, record_every=REC_EVERY,
                text=None, bug_events=probe.get("bugEvents", []),
                sim_seconds=round(t.t * DT_MS / 1000, 1), frames=t.frames)
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=1))
    try:
        import imageio.v2 as imageio
        import numpy as np
        w = imageio.get_writer(out_dir / "video.mp4", fps=4, codec="libx264",
                               quality=7, macro_block_size=None)
        for fn in t.frames:
            w.append_data(np.asarray(Image.open(out_dir / fn)))
        w.close()
    except Exception as e:
        print("video assembly failed:", e)
    print(f"{out_dir.name}: {t.t} ticks ({t.t * DT_MS / 1000:.0f}s sim), "
          f"{len(t.frames)} frames, {len(meta['bug_events'])} events")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="tour-v1")
    ap.add_argument("--suite", default="sp", choices=["sp", "house"],
                    help="sp: Sponza routes above; house: HS suite routes (agent/vla/house_routes.py)")
    ap.add_argument("--only", default=None, help="comma-separated config names to run (debug)")
    args = ap.parse_args()
    routes, clean_routes, clean_cfg = ROUTES, CLEAN_ROUTES, "sp00-clean"
    if args.suite == "house":
        from agent.vla import house_routes
        routes, clean_routes, clean_cfg = house_routes.ROUTES, house_routes.CLEAN_ROUTES, house_routes.CLEAN_CONFIG
    only = set(args.only.split(",")) if args.only else None
    with Bridge() as br:
        for config, route in routes.items():
            if only and config not in only:
                continue
            run_episode(br, config, route, REPO / "runs" / args.tag / f"{config}-s0")
        if only and clean_cfg not in only:
            return
        for i, route in enumerate(clean_routes):
            run_episode(br, clean_cfg, route, REPO / "runs" / args.tag / f"{clean_cfg}-s{i}")


if __name__ == "__main__":
    main()
