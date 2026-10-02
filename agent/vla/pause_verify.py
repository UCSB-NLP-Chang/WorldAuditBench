"""Verify the turn-based sim clock: the world must be frozen while the policy deliberates
and advance only inside action-execution windows.
Usage: .venv/bin/python -m agent.vla.pause_verify
"""
import time

from agent.vla.bridge import Bridge


def main():
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(("  PASS " if cond else "  FAIL ") + name + (f"  ({detail})" if detail else ""))

    with Bridge() as br:
        br.open_env("tc04-drift-bug", seed=5)
        br.page.evaluate("() => window.__env.enable()")

        t0 = br.probe()["simT"]
        time.sleep(3)                        # policy "thinking" - wall clock only
        t1 = br.probe()["simT"]
        check("simT frozen during idle", t1 == t0, f"{t0} -> {t1}")

        r = br.act({"action": "wait", "ms": 1000})
        t2 = br.probe()["simT"]
        check("wait 1000ms advances ~1.0s", 0.95 <= t2 - t1 <= 1.15, f"+{t2 - t1:.3f}")
        check("simElapsed reported", 0.95 <= r["simElapsed"] <= 1.15, r["simElapsed"])

        # world-freeze check via full mesh-position snapshots (no name lookup needed)
        snap_js = ("() => { const out = []; window.__ctx.scene.traverse(o => {"
                   " if (o.isMesh) out.push([+o.position.x.toFixed(4), +o.position.z.toFixed(4)]); });"
                   " return JSON.stringify(out); }")
        s0 = br.page.evaluate(snap_js)
        time.sleep(2)
        s1 = br.page.evaluate(snap_js)
        check("all meshes frozen during idle", s0 == s1)
        br.act({"action": "wait", "ms": 2000})
        s2 = br.page.evaluate(snap_js)
        check("drifting crate moves during wait", s1 != s2)

        t3 = br.probe()["simT"]
        br.act({"action": "turn", "deg": 60})
        t4 = br.probe()["simT"]
        check("turn 60deg advances ~0.5s", 0.4 <= t4 - t3 <= 0.65, f"+{t4 - t3:.3f}")

        t5 = br.probe()["simT"]
        r = br.act({"action": "forward", "dist": 2.0})
        t6 = br.probe()["simT"]
        check("forward advances sim time naturally", 0.3 <= t6 - t5 <= 3.0, f"+{t6 - t5:.3f}")
        time.sleep(2)
        check("simT frozen again after action", br.probe()["simT"] == t6)

    print("ALL PASS" if ok else "FAILURES PRESENT")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
