"""S0 smoke test (no VLM): execute every action >=20x in the env0 corridor, checking
  (1) no JS errors  (2) frames valid and non-blank  (3) blocked detection correct
  (4) interact 3-frame timing + real mechanism state changes  (5) corridor traversable
      end to end (door -> lever -> gate -> ring)

Usage: python -m harness.policies.scripted [--gpu swiftshader] [--tag s0]
Output: runs/<tag>/s0/  frames + actions.jsonl + s0_report.json + video.mp4
"""
import argparse
import io
import json
import math
import time
from pathlib import Path

from PIL import Image

from harness.bridge import Bridge
from harness.runner import _save_frame, REPO


def norm180(d):
    while d > 180: d -= 360
    while d < -180: d += 360
    return d


class S0:
    def __init__(self, br, run_dir):
        self.br, self.run_dir = br, run_dir
        self.counts = {}
        self.checks = []          # {name, ok, detail}
        self.gidx = 0
        self.free_forward_errs = []   # |moved-dist|/dist for unobstructed forward moves
        self.blocked_events = 0
        self.false_blocked = 0
        self.frame_stats = []
        self.any_teleport = self.any_respawn = False
        self.log = open(run_dir / "actions.jsonl", "w")
        self.phase = "?"

    def check(self, name, ok, detail=""):
        self.checks.append(dict(name=name, ok=bool(ok), detail=str(detail)))
        if not ok:
            print(f"  ✗ {name}: {detail}")

    def act(self, a, caption="", expect_free=None):
        res = self.br.act(a)
        self.counts[a["action"]] = self.counts.get(a["action"], 0) + 1
        self.any_teleport |= res["teleported"]
        self.any_respawn |= res["respawned"]
        files = []
        for i, f in enumerate(res["frames"]):
            name = f"f{self.gidx:04d}.jpg"
            self.gidx += 1
            _save_frame(self.run_dir, name, f,
                        [f"[{self.phase}] {json.dumps(a, ensure_ascii=False)}"
                         + (f"  frame {i + 1}/{len(res['frames'])} t={res['frameT'][i]}" if len(res["frames"]) > 1 else ""),
                         f"moved {res['moved']} | pos ({res['pos'][0]:.1f},{res['pos'][2]:.1f}) | yaw {res['yaw']} | pitch {res['pitch']}"])
            files.append(name)
            self._frame_stat(f, name)
        # blocked rule matches the harness
        if a["action"] == "forward":
            d = min(a.get("dist", 1.5), 4)
            blocked = res["moved"] < 0.3 * d
            if blocked:
                self.blocked_events += 1
            if expect_free is True:
                self.free_forward_errs.append(abs(res["moved"] - d) / d)
                if blocked:
                    self.false_blocked += 1
        self.log.write(json.dumps(dict(idx=self.gidx, phase=self.phase, action=a,
                                       moved=res["moved"], pos=res["pos"], yaw=res["yaw"],
                                       pitch=res["pitch"], frameT=res["frameT"],
                                       interacted=res["interacted"], files=files),
                                  ensure_ascii=False) + "\n")
        return res, files

    def _frame_stat(self, dataurl, name):
        import base64
        import numpy as np
        raw = base64.b64decode(dataurl.split(",", 1)[1])
        img = Image.open(io.BytesIO(raw)).convert("L")
        arr = np.asarray(img, dtype=float)
        self.frame_stats.append(dict(name=name, w=img.width, h=img.height,
                                     mean=round(arr.mean(), 1), std=round(arr.std(), 1)))

    def pixdiff(self, fa, fb):
        import numpy as np
        a = np.asarray(Image.open(self.run_dir / fa).convert("L").resize((240, 150)), dtype=float)
        b = np.asarray(Image.open(self.run_dir / fb).convert("L").resize((240, 150)), dtype=float)
        return float(abs(a - b).mean())

    # -- geometric aiming: compute turn/look from the current pose --
    def face_point(self, tx, ty, tz, do_look=True):
        st = self.br.state()
        px, py, pz = st["pos"]
        dx, dz = tx - px, tz - pz
        theta = math.degrees(math.atan2(-dx, -dz))          # desired rotation.y
        turn = norm180(st["yaw"] - theta)
        if abs(turn) > 0.5:
            self.act({"action": "turn", "deg": round(turn, 1)}, "face")
        if do_look:
            phi = math.degrees(math.atan2(ty - py, math.hypot(dx, dz)))   # + = up
            st2 = self.br.state()
            look = st2["pitch"] - phi                                     # look + = down
            if abs(look) > 0.5:
                self.act({"action": "look", "deg": round(look, 1)}, "face")

    def level_look(self):
        p = self.br.state()["pitch"]
        if abs(p) > 0.5:
            self.act({"action": "look", "deg": round(p, 1)}, "level")

    def walk_to_x(self, tx, expect_free=None, max_tries=6):
        """Walk along the current heading (should be +x) to x~tx in segments, with a bail-out. Returns arrival."""
        stall = 0
        for _ in range(max_tries):
            need = tx - self.br.state()["pos"][0]
            if need <= 0.3:
                return True
            r, _ = self.act({"action": "forward", "dist": round(min(need, 4), 2)},
                            expect_free=expect_free)
            stall = stall + 1 if r["moved"] < 0.05 else 0
            if stall >= 2:
                return False
        return tx - self.br.state()["pos"][0] <= 0.3


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gpu", default="gl-egl", choices=["vulkan", "gl-egl", "swiftshader"])
    ap.add_argument("--tag", default=None)
    args = ap.parse_args()
    tag = args.tag or time.strftime("%m%d-%H%M%S")
    run_dir = REPO / "runs" / tag / "s0"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "frames.jsonl").write_text("")

    t_start = time.time()
    with Bridge(gpu=args.gpu) as br:
        meta = br.open_env("env0-corridor", seed=1)
        print(f"[renderer] {meta['renderer']}  load {meta['load_time_s']}s")
        s = S0(br, run_dir)
        targets = br.targets()

        # frame 0
        s.phase = "init"
        s.act({"action": "wait", "ms": 300}, "init")
        st0 = br.state()
        s.check("spawn_pose", abs(st0["yaw"] - 270) < 1.5 and abs(st0["pos"][0] - 1.2) < 0.3,
                f"yaw={st0['yaw']} pos={st0['pos']}")

        # -- A. turn x21: +45deg per step, verify heading tracking --
        s.phase = "A-turn"
        yaw_errs = []
        for i in range(1, 21):
            s.act({"action": "turn", "deg": 45})
            expect = (270 - 45 * i) % 360
            got = br.state()["yaw"]
            yaw_errs.append(abs(norm180(got - expect)))
        s.act({"action": "turn", "deg": 180})
        yaw_errs.append(abs(norm180(br.state()["yaw"] - 270)))
        s.check("yaw_tracking", max(yaw_errs) < 1.5, f"max_err={max(yaw_errs):.2f}deg")

        # -- B. look x21: pitch tracking + clamps --
        s.phase = "B-look"
        pitch_errs = []
        expect_p = 0.0
        clamp_lo = clamp_hi = False
        for deg, times in [(20, 5), (-20, 10), (20, 5)]:
            for _ in range(times):
                s.act({"action": "look", "deg": deg})
                expect_p = max(-74.48, min(74.48, expect_p - deg))
                got = br.state()["pitch"]
                pitch_errs.append(abs(got - expect_p))
                clamp_lo |= abs(got + 74.48) < 1
                clamp_hi |= abs(got - 74.48) < 1
        s.level_look()
        pitch_errs.append(abs(br.state()["pitch"]))
        s.check("pitch_tracking", max(pitch_errs) < 1.5, f"max_err={max(pitch_errs):.2f}deg")
        s.check("pitch_clamps", clamp_lo and clamp_hi, f"lo={clamp_lo} hi={clamp_hi}")

        # -- C0. free forward/back pairs (warm-up + free-move accuracy) --
        s.phase = "C0-freemove"
        for _ in range(4):
            s.act({"action": "forward", "dist": 0.5}, expect_free=True)
            s.act({"action": "back", "dist": 0.5})

        # -- C. side-wall blocked test --
        s.phase = "C-wall"
        st = br.state()
        s.face_point(st["pos"][0], 1.7, st["pos"][2] - 5, do_look=False)   # face the -z south wall
        r, _ = s.act({"action": "forward", "dist": 4})     # into the south wall, should travel ~1.6m
        s.check("wall_approach", 1.2 < r["moved"] < 2.0, f"moved={r['moved']}")
        nb0 = s.blocked_events
        for _ in range(3):
            s.act({"action": "forward", "dist": 1})        # push against the wall -> blocked x3
        s.check("wall_blocked_x3", s.blocked_events - nb0 == 3, f"got {s.blocked_events - nb0}")
        st = br.state()
        s.face_point(st["pos"][0], 1.7, st["pos"][2] + 5, do_look=False)   # face +z and walk back
        back = abs(st["pos"][2])
        if back > 0.3:
            s.act({"action": "forward", "dist": round(back, 2)}, expect_free=True)

        # -- D. forward into the closed door: approach + stop --
        s.phase = "D-door-approach"
        st = br.state()
        s.face_point(st["pos"][0] + 5, 1.7, 0, do_look=False)              # face +x
        s.level_look()
        s.walk_to_x(6.2, expect_free=True)
        nb0 = s.blocked_events
        for _ in range(3):
            s.act({"action": "forward", "dist": 1})        # two steps reach the door face, third is blocked
        s.check("door_blocks_movement", s.blocked_events - nb0 >= 1,
                f"blocked +{s.blocked_events - nb0}, x={br.state()['pos'][0]:.2f}")
        s.check("door_stops_at_face", br.state()["pos"][0] < 8.0, f"x={br.state()['pos'][0]:.2f}")
        st = br.state()
        if st["pos"][0] > 6.2:
            s.act({"action": "back", "dist": round(st["pos"][0] - 6.2, 2)})

        # -- E. interact x21: open/close cycles, 3-frame timing + state toggles + visual change --
        s.phase = "E-interact-door"
        interact_ok = timing_ok = diff_ok = True
        details = []
        for k in range(21):
            pre = br.probe()["doors"]["door_mid"]["eff"]
            if pre:   # door open -> aim at the open panel (hinge at z=-1; open panel extends +x along the south wall)
                s.face_point(9.2, 1.5, -0.95)
            else:     # door closed -> face the panel
                s.face_point(8.2, 1.5, 0)
            r, files = s.act({"action": "interact"})
            post = br.probe()["doors"]["door_mid"]["eff"]
            if not r["interacted"] or post == pre:
                interact_ok = False
                details.append(f"k={k} interacted={r['interacted']} pre={pre} post={post}")
            ft = r["frameT"]
            if not (len(r["frames"]) == 3 and ft[0] < 0.3 and 0.65 <= ft[1] <= 1.2 and 2.7 <= ft[2] <= 3.4):
                timing_ok = False
                details.append(f"k={k} frameT={ft}")
            d = s.pixdiff(files[0], files[2])
            if d < 2.0:
                diff_ok = False
                details.append(f"k={k} pixdiff={d:.1f}")
        s.check("interact_toggles_door", interact_ok, "; ".join(details[:4]))
        s.check("interact_frame_timing", timing_ok, "; ".join(details[:4]))
        s.check("interact_visible_change", diff_ok, "; ".join(details[:4]))
        s.check("door_open_for_traversal", br.probe()["doors"]["door_mid"]["eff"], "")
        s.level_look()

        # -- F. back x19 (free backward accuracy) --
        s.phase = "F-back"
        st = br.state()
        s.face_point(st["pos"][0] + 5, 1.7, st["pos"][2], do_look=False)
        back_errs = []
        for _ in range(19):
            r, _ = s.act({"action": "back", "dist": 0.25})
            back_errs.append(abs(r["moved"] - 0.25))
        s.check("back_accuracy", max(back_errs) < 0.15, f"max_err={max(back_errs):.2f}m")

        # -- G. wait x20 + flag x20 --
        s.phase = "G-wait-flag"
        wait_errs = []
        for i in range(20):
            r, _ = s.act({"action": "wait", "ms": 100})
            wait_errs.append(r["simElapsed"])
        s.check("wait_sim_time", all(0.08 <= w <= 0.6 for w in wait_errs),
                f"range=[{min(wait_errs):.2f},{max(wait_errs):.2f}]s")
        for i in range(20):
            s.act({"action": "flag", "note": f"s0-{i}"})
        s.check("flags_recorded", len(br.flags()) == 20, f"got {len(br.flags())}")

        # -- H. traversal: door -> lever -> gate -> ring --
        s.phase = "H-traverse"
        st = br.state()
        s.face_point(st["pos"][0] + 5, 1.7, 0, do_look=False)
        s.level_look()
        # reach the door and pass through (door open)
        for tx in (6.2, 10.4, 12.2):
            s.walk_to_x(tx, expect_free=True)
        s.check("through_open_door", br.state()["pos"][0] > 10.0, f"x={br.state()['pos'][0]:.2f}")
        r, pre_files = s.act({"action": "wait", "ms": 150})       # baseline frame before the lever (gate in view)
        pre_gate_frame = pre_files[-1]
        # lever: aim at the base center; if missed, retry aiming at the knob
        s.face_point(12.8, 0.25, 1.7)
        r, _ = s.act({"action": "interact"})
        if not br.probe()["levers"]["lever_gate"]:
            s.face_point(13.11, 0.95, 1.7)
            r, _ = s.act({"action": "interact"})
        pr = br.probe()
        s.check("lever_pulled", pr["levers"]["lever_gate"] is True, str(pr["levers"]))
        s.check("gate_opened_by_lever", pr["doors"]["gate_end"]["eff"] is True
                and pr["doors"]["gate_end"]["t"] > 0.9, str(pr["doors"]["gate_end"]))
        s.check("lever_interacted", r["interacted"], "")
        # level the view and compare frames before/after the gate opened
        st = br.state()
        s.face_point(st["pos"][0] + 5, 1.7, 0, do_look=False)
        s.level_look()
        r, post_files = s.act({"action": "wait", "ms": 150})
        s.check("gate_visibly_open", s.pixdiff(pre_gate_frame, post_files[-1]) > 1.5,
                f"pixdiff={s.pixdiff(pre_gate_frame, post_files[-1]):.1f}")
        # through the gate to the ring
        for tx in (16.2, 18.5):
            s.walk_to_x(tx, expect_free=True)
        tgt = targets["ring_end"]
        pos = br.state()["pos"]
        dist = math.hypot(pos[0] - tgt[0], pos[2] - tgt[2])
        s.check("reached_ring", dist < 3.0, f"dist={dist:.2f}")

        # -- summary checks --
        s.phase = "Z-summary"
        for name, mn in [("forward", 20), ("back", 20), ("turn", 20), ("look", 20),
                         ("interact", 20), ("wait", 20), ("flag", 20)]:
            s.check(f"count_{name}>=", s.counts.get(name, 0) >= mn, f"{s.counts.get(name, 0)}")
        s.check("free_forward_accuracy",
                s.free_forward_errs and max(s.free_forward_errs) < 0.12,
                f"max_rel_err={max(s.free_forward_errs):.3f}" if s.free_forward_errs else "none")
        s.check("no_false_blocked", s.false_blocked == 0, f"{s.false_blocked}")
        s.check("blocked_events>=3", s.blocked_events >= 3, f"{s.blocked_events}")
        s.check("no_teleport_no_respawn", not s.any_teleport and not s.any_respawn,
                f"tp={s.any_teleport} rs={s.any_respawn}")
        # truly blank = all-black (classic missing-preserveDrawingBuffer symptom) or all-white;
        # a uniform gray from a wall filling the view is a legitimate frame
        bad_frames = [f for f in s.frame_stats
                      if f["w"] != 960 or f["h"] != 600 or f["mean"] < 6
                      or (f["std"] < 1 and f["mean"] > 249)]
        s.check("frames_nonblank", not bad_frames,
                f"{len(bad_frames)}/{len(s.frame_stats)} bad, e.g. {bad_frames[:2]}")
        errs = br.page_errors + br.console_errors()
        s.check("no_js_errors", not errs, "; ".join(errs[:3]))
        s.check("gems_untouched", br.state()["gems"] == 0, "")

        s.log.close()
        gate = all(c["ok"] for c in s.checks)
        report = dict(
            gate_pass=gate, renderer=meta["renderer"], load_time_s=meta["load_time_s"],
            wall_time_s=round(time.time() - t_start, 1),
            action_counts=s.counts, blocked_events=s.blocked_events,
            n_frames=len(s.frame_stats), checks=s.checks,
        )
        (run_dir / "s0_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print(f"\n== S0 {'ALL GREEN PASS' if gate else 'FAIL'} ==")
    for c in report["checks"]:
        print(f"  {'✓' if c['ok'] else '✗'} {c['name']}" + (f"  ({c['detail']})" if c["detail"] and not c["ok"] else ""))
    print(f"action counts: {report['action_counts']}")
    print(f"report: {run_dir}/s0_report.json")

    try:
        from eval.video import make_video
        v = make_video(run_dir, fps=3)
        print(f"video: {v}")
    except Exception as e:
        print(f"video assembly failed: {e}")
    return 0 if gate else 1


if __name__ == "__main__":
    raise SystemExit(main())
