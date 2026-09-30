"""Verify the S1-ladder L3 near-spawn configs (spXX-*-near).

For every entry in LADDER_NEAR: open the -near config, and assert
  1. the agent stands at the intended spawn point (x/z within 0.35 m; snap only moves y),
  2. the bug anchor lies inside the inspection zone (dist <= r),
  3. the agent faces the bug (heading error < 3 deg).
Saves one first-person screenshot per case for visual review.

Usage: .venv/bin/python -m harness.near_verify [outdir]
"""
import base64
import math
import sys
from pathlib import Path

from harness.bridge import Bridge
from harness.tasks import LADDER_NEAR


def main():
    outdir = Path(sys.argv[1] if len(sys.argv) > 1 else "runs/near-verify")
    outdir.mkdir(parents=True, exist_ok=True)
    bad = 0
    with Bridge() as br:
        for slug, nd in LADDER_NEAR.items():
            (sx, sz), (bx, bz), r = nd["spawn"], nd["bug"], nd["r"]
            br.open_env(f"{slug}-near", seed=0)
            res = br.act({"action": "wait", "ms": 300})
            px, _, pz = res["pos"]
            yaw = res["yaw"]
            want_yaw = math.degrees(math.atan2(-(bx - sx), -(bz - sz)))
            yaw_err = abs((yaw - want_yaw + 180) % 360 - 180)
            spawn_err = math.hypot(px - sx, pz - sz)
            bug_d = math.hypot(px - bx, pz - bz)
            ok = spawn_err < 0.35 and bug_d <= r and yaw_err < 3
            bad += not ok
            print(f"{slug:20s} spawn_err {spawn_err:.2f}m  bug_dist {bug_d:.2f}m (r={r})  "
                  f"yaw {yaw:.0f} (want {want_yaw:.0f}, err {yaw_err:.1f})  "
                  f"{'OK' if ok else 'FAIL'}")
            frame = res["frames"][-1]
            (outdir / f"{slug}-near.jpg").write_bytes(
                base64.b64decode(frame.split(",", 1)[1]))
    print(f"{'ALL OK' if not bad else f'{bad} FAILURES'} - screenshots in {outdir}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
