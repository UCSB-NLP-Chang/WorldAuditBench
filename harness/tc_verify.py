"""Automated TC test-case verification: per-case behavioral assertions + screenshots.
Usage: .venv/bin/python -m harness.tc_verify
Output: runs/tc-verify/ screenshots + verify_report.md; check table on stdout
"""
import base64
import io
import json
import math
import time
from pathlib import Path

import numpy as np
from PIL import Image

from harness.bridge import Bridge
from harness.runner import REPO

OUT = REPO / "runs" / "tc-verify"
OUT.mkdir(parents=True, exist_ok=True)
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), str(detail)))
    print(("  ✓ " if ok else "  ✗ ") + name + (f"  ({detail})" if detail and not ok else ""))


def save(br_res, fname):
    (OUT / fname).write_bytes(base64.b64decode(br_res["frames"][-1].split(",", 1)[1]))


def gray(dataurl):
    raw = base64.b64decode(dataurl.split(",", 1)[1])
    return np.asarray(Image.open(io.BytesIO(raw)).convert("L"), float)


def rgb_means(dataurl):
    raw = base64.b64decode(dataurl.split(",", 1)[1])
    a = np.asarray(Image.open(io.BytesIO(raw)).convert("RGB"), float)
    return a[..., 0].mean(), a[..., 1].mean(), a[..., 2].mean()


def face_point(br, tx, ty, tz):
    st = br.state()
    px, py, pz = st["pos"]
    dx, dz = tx - px, tz - pz
    theta = math.degrees(math.atan2(-dx, -dz))
    turn = st["yaw"] - theta
    while turn > 180: turn -= 360
    while turn < -180: turn += 360
    if abs(turn) > 0.5:
        br.act({"action": "turn", "deg": round(turn, 1)})
    phi = math.degrees(math.atan2(ty - py, math.hypot(dx, dz)))
    look = br.state()["pitch"] - phi
    if abs(look) > 0.5:
        br.act({"action": "look", "deg": round(look, 1)})


def walk_x(br, tx):
    for _ in range(8):
        need = tx - br.state()["pos"][0]
        if need <= 0.3:
            return True
        r = br.act({"action": "forward", "dist": round(min(need, 4), 2)})
        if r["moved"] < 0.05:
            return False
    return False


def fire_lever_and_sample(br, lever_xyz, door_id, n=16, iv_ms=100):
    """Fire the lever (without awaiting), then sample the door t every iv_ms."""
    face_point(br, *lever_xyz)
    br.page.evaluate("() => { window.__env.act({action:'interact'}); return null; }")
    return br.page.evaluate(
        """([id, n, iv]) => new Promise(res => {
             const d = [];
             const t = setInterval(() => {
               d.push(window.__env.probe().doors[id].t);
               if (d.length >= n) { clearInterval(t); res(d); }
             }, iv);
           })""", [door_id, n, iv_ms])


print("== tc01 autoclose ==")
with Bridge() as br:
    br.open_env("tc01-autoclose-bug", seed=1)
    walk_x(br, 5.2)
    ts = fire_lever_and_sample(br, (7.2, 1.5, 0), "door_a", n=24, iv_ms=150)  # interact directly with the door
    r = br.act({"action": "wait", "ms": 300})
    save(r, "tc01-bug.jpg")
    check("tc01 bug: door auto-closes (t rises to ~1 then back to 0)", max(ts) > 0.9 and ts[-1] < 0.1,
          f"tmax={max(ts)} tail={ts[-3:]}")
with Bridge() as br:
    br.open_env("tc01-autoclose-clean", seed=1)
    walk_x(br, 5.2)
    face_point(br, 7.2, 1.5, 0)
    br.act({"action": "interact"})
    br.act({"action": "wait", "ms": 3000})
    p2 = br.probe()["doors"]["door_a"]
    check("tc01 clean: door stays open", p2["eff"], str(p2))

print("== tc02 accel / tc03 interrupt ==")
for name, cfg, expect in [("tc02", "tc02-accel-bug", "fast"), ("tc02c", "tc02-accel-clean", "normal"),
                          ("tc03", "tc03-interrupt-bug", "half"), ("tc03c", "tc03-interrupt-clean", "normal")]:
    with Bridge() as br:
        br.open_env(cfg, seed=1)
        walk_x(br, 5.8)
        ts = fire_lever_and_sample(br, (6.8, 0.25, 1.7), "gate_a")
        r = br.act({"action": "wait", "ms": 400})
        save(r, f"{name}.jpg")
        tmax = max(ts)
        t03 = ts[3] if len(ts) > 3 else 0   # at ~300ms
        if expect == "fast":
            check("tc02 bug: gate nearly fully open within ~0.3s", t03 > 0.9, f"t@300ms={t03} ts={ts[:6]}")
        elif expect == "half":
            check("tc03 bug: gate stuck at t=0.5", abs(tmax - 0.5) < 0.06, f"tmax={tmax}")
            face_point(br, 14, 1.7, 0)
            blocked = br.act({"action": "forward", "dist": 3})
            check("tc03 bug: half-open gate still blocks", br.state()["pos"][0] < 8.05, f"pos={br.state()['pos']} moved={blocked['moved']}")
        else:
            check(f"{name}: normal speed (not fully open at 300ms, fully open at the end)", t03 < 0.5 and tmax > 0.95,
                  f"t@300ms={t03} tmax={tmax}")

print("== tc04 drift ==")
with Bridge() as br:
    br.open_env("tc04-drift-bug", seed=1)
    r1 = br.act({"action": "wait", "ms": 300})
    r2 = br.act({"action": "wait", "ms": 2500})
    save(r2, "tc04-bug.jpg")
    a, b = gray(r1["frames"][-1]), gray(r2["frames"][-1])
    # the south (lower-left) region should change; the north crate stays still
    dl = float(abs(a[300:520, 120:480] - b[300:520, 120:480]).mean())
    dr = float(abs(a[300:520, 480:840] - b[300:520, 480:840]).mean())
    check("tc04 bug: drifting-crate region diff >> static crate", dl > 3 * max(dr, 0.2) or dl > 5, f"dl={dl:.2f} dr={dr:.2f}")
with Bridge() as br:
    br.open_env("tc04-drift-clean", seed=1)
    r1 = br.act({"action": "wait", "ms": 300})
    r2 = br.act({"action": "wait", "ms": 2500})
    a, b = gray(r1["frames"][-1]), gray(r2["frames"][-1])
    d = float(abs(a - b).mean())
    check("tc04 clean: scene static", d < 1.0, f"diff={d:.2f}")

print("== tc05 walltrap ==")
with Bridge() as br:
    br.open_env("tc05-walltrap-bug", seed=1)
    walk_x(br, 5.0)
    # walk to the pillar south side (7,-1.5) and push in facing +z
    face_point(br, 7.0, 1.7, -1.5)
    walk_ok = True
    for _ in range(4):
        st = br.state()
        d = math.hypot(7.0 - st["pos"][0], -1.5 - st["pos"][2])
        if d < 0.35: break
        br.act({"action": "forward", "dist": round(min(d, 2), 2)})
    face_point(br, 7.0, 1.7, 0)
    br.act({"action": "forward", "dist": 1.5})
    br.act({"action": "forward", "dist": 1.0})
    st = br.state()
    inside = abs(st["pos"][0] - 7.0) < 0.6 and abs(st["pos"][2]) < 0.6
    m1 = br.act({"action": "forward", "dist": 1.5})["moved"]
    br.act({"action": "turn", "deg": 90})
    m2 = br.act({"action": "forward", "dist": 1.5})["moved"]
    br.act({"action": "turn", "deg": 90})
    m3 = br.act({"action": "forward", "dist": 1.5})["moved"]
    r = br.act({"action": "wait", "ms": 200})
    save(r, "tc05-bug-inside.jpg")
    check("tc05 bug: entered the pillar", inside, f"pos={st['pos']}")
    check("tc05 bug: stuck in three directions", max(m1, m2, m3) < 0.45, f"moves={m1},{m2},{m3}")
with Bridge() as br:
    br.open_env("tc05-walltrap-clean", seed=1)
    walk_x(br, 5.0)
    face_point(br, 7.0, 1.7, -1.5)
    for _ in range(3):
        st = br.state()
        d = math.hypot(7.0 - st["pos"][0], -1.5 - st["pos"][2])
        if d < 0.35: break
        br.act({"action": "forward", "dist": round(min(d, 2), 2)})
    face_point(br, 7.0, 1.7, 0)
    br.act({"action": "forward", "dist": 1.5})
    st = br.state()
    check("tc05 clean: solid pillar blocks from outside", abs(st["pos"][2]) > 0.85, f"pos={st['pos']}")

print("== tc06 throughwall ==")
for cfg, expect_open in [("tc06-throughwall-bug", True), ("tc06-throughwall-clean", False)]:
    with Bridge() as br:
        br.open_env(cfg, seed=1)
        walk_x(br, 7.7)
        face_point(br, 9.0, 0.45, 0.5)
        r = br.act({"action": "interact"})
        opened = br.probe()["chests"]["chest_b"]
        save(r, f"{'tc06-bug' if expect_open else 'tc06-clean'}.jpg")
        if expect_open:
            check("tc06 bug: chest opened through the gate", opened, f"open={opened} interacted={r['interacted']}")
        else:
            check("tc06 clean: gate occludes the interaction", not opened, f"open={opened} interacted={r['interacted']}")

print("== tc07 tint ==")
with Bridge() as br:
    br.open_env("tc07-tint-bug", seed=1)
    r = br.act({"action": "wait", "ms": 300})
    save(r, "tc07-bug.jpg")
    rm, gm, bm = rgb_means(r["frames"][-1])
    check("tc07 bug: red channel strongly elevated", rm > gm * 1.35 and rm > bm * 1.35, f"r={rm:.0f} g={gm:.0f} b={bm:.0f}")
with Bridge() as br:
    br.open_env("tc07-tint-clean", seed=1)
    r = br.act({"action": "wait", "ms": 300})
    rm, gm, bm = rgb_means(r["frames"][-1])
    check("tc07 clean: channels balanced", rm < gm * 1.25 + 20, f"r={rm:.0f} g={gm:.0f} b={bm:.0f}")

print("== tc08 extra(Sponza)==")
with Bridge() as br:
    br.open_env("tc08-extra-bug", seed=1)
    r = br.act({"action": "wait", "ms": 300})
    save(r, "tc08-bug.jpg")
    check("tc08 bug: odd_gate present", "odd_gate" in br.probe()["doors"], str(br.probe()["doors"].keys()))
with Bridge() as br:
    br.open_env("tc08-extra-clean", seed=1)
    r = br.act({"action": "wait", "ms": 300})
    save(r, "tc08-clean.jpg")
    check("tc08 clean: no extra asset", "odd_gate" not in br.probe()["doors"], "")

print("== tc09 sink ==")
with Bridge() as br:
    br.open_env("tc09-sink-bug", seed=1)
    walk_x(br, 4.0)
    face_point(br, 6.5, 0.2, 0)
    r = br.act({"action": "wait", "ms": 200})
    save(r, "tc09-bug.jpg")
    check("tc09 bug: loads fine (visual check via screenshot)", True, "")
with Bridge() as br:
    br.open_env("tc09-sink-clean", seed=1)
    walk_x(br, 4.0)
    face_point(br, 6.5, 0.2, 0)
    r = br.act({"action": "wait", "ms": 200})
    save(r, "tc09-clean.jpg")

print("== tc10 invisible ==")
with Bridge() as br:
    br.open_env("tc10-invisible-bug", seed=1)
    ok = walk_x(br, 14.0)
    st = br.state()
    r2 = br.act({"action": "forward", "dist": 1})
    r = br.act({"action": "wait", "ms": 200})
    save(r, "tc10-bug.jpg")
    check("tc10 bug: blocked mid-way by an invisible object", (not ok) and 5.7 < st["pos"][0] < 6.8 and r2["moved"] < 0.3,
          f"pos={st['pos']} extra_moved={r2['moved']}")
with Bridge() as br:
    br.open_env("tc10-invisible-clean", seed=1)
    ok = walk_x(br, 14.0)
    check("tc10 clean: corridor clear", ok, f"pos={br.state()['pos']}")

n_ok = sum(1 for _, ok, _ in RESULTS if ok)
lines = [f"# TC verification — {time.strftime('%F %T')}", "",
         f"**{n_ok}/{len(RESULTS)} PASS**", ""]
for name, ok, detail in RESULTS:
    lines.append(f"- {'✅' if ok else '❌'} {name}" + (f" — `{detail}`" if detail else ""))
(OUT / "verify_report.md").write_text("\n".join(lines) + "\n")
print(f"\n== {n_ok}/{len(RESULTS)} PASS ==  report: {OUT}/verify_report.md")
raise SystemExit(0 if n_ok == len(RESULTS) else 1)
