"""Behavioral verification of the HS (Family House) test suite: every planted bug must
demonstrably manifest, and the clean house must be fully patrollable (both floors).
Usage: .venv/bin/python -m harness.hs_verify
Output: runs/hs-verify/ screenshots + assertion table on stdout
"""
import base64
import io
import math

import numpy as np
from PIL import Image

from harness.bridge import Bridge
from harness.runner import REPO

OUT = REPO / "runs" / "hs-verify"
OUT.mkdir(parents=True, exist_ok=True)
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), str(detail)))
    print(("  PASS " if ok else "  FAIL ") + name + (f"  ({detail})" if detail else ""), flush=True)


def shot(res, fname):
    (OUT / fname).write_bytes(base64.b64decode(res["frames"][-1].split(",", 1)[1]))


def img(res):
    raw = base64.b64decode(res["frames"][-1].split(",", 1)[1])
    return np.asarray(Image.open(io.BytesIO(raw)).convert("RGB"), float)


def face(br, tx, ty, tz):
    st = br.state()
    px, py, pz = st["pos"]
    dx, dz = tx - px, tz - pz
    theta = math.degrees(math.atan2(-dx, -dz))
    turn = st["yaw"] - theta
    while turn > 180: turn -= 360
    while turn < -180: turn += 360
    r = br.act({"action": "turn", "deg": round(turn, 1)})
    pitch_down = math.degrees(math.atan2(py - ty, math.hypot(dx, dz)))   # wanted pitch, +down
    look = st["pitch"] + pitch_down                                       # state pitch is +up; look deg is +down
    if abs(look) > 1:
        r = br.act({"action": "look", "deg": round(look, 1)})
    return r


def obj(br, name):
    return br.page.evaluate("""(n) => { const o = window.__ctx.scene.getObjectByName(n); if (!o) return null;
      const T = window.__ctx.THREE; const b = new T.Box3().setFromObject(o);
      let solid = false; o.traverse(c => { if (c.isMesh && window.__ctx.worldMeshes.includes(c)) solid = true; });
      let dt = null; o.traverse(c => { if (c.isMesh && dt === null) dt = c.material.depthTest; });
      return { min: b.min.toArray(), max: b.max.toArray(), visible: o.visible, solid, depthTest: dt }; }""", name)


def boot(br, cfg):
    br.open_env(cfg, seed=5)
    br.act({"action": "wait", "ms": 150})


def walk(br, dist):
    return br.act({"action": "forward", "dist": dist})


def goto(br, tx, tz, tol=0.5, tries=8):
    """Turn toward (tx,tz) and walk in <=4 m legs until within tol (returns final distance)."""
    d = None
    for _ in range(tries):
        st = br.state()
        d = math.hypot(tx - st["pos"][0], tz - st["pos"][2])
        if d < tol:
            break
        face(br, tx, 1.6, tz)
        walk(br, round(min(d, 4.0), 2))
    st = br.state()
    return math.hypot(tx - st["pos"][0], tz - st["pos"][2])


def main():
    with Bridge() as br:
        # ---- hs00 clean: both floors patrollable ----
        boot(br, "hs00-clean")
        respawned = False
        # hall north, dining, kitchen, living, then the stairs to the landing and the lounge
        # straight legs only (no path planning): dining west aisle x=2.7, living-room loop via the
        # passage west of the side table (-5.25, 2.35)
        for wp in [(0.6, -3.6), (0.6, 3.6), (2.0, 3.8), (2.7, 3.6), (2.7, -0.2), (4.4, -0.9), (2.0, -3.4),
                   (0.6, -3.6), (0.6, 3.6), (-1.9, 3.8), (-4.0, 3.9), (-5.25, 2.35), (-4.6, 1.2), (-2.4, 1.5)]:
            d = goto(br, *wp)
            respawned |= br.act({"action": "wait", "ms": 50})["respawned"]
            check(f"hs00: reaches {wp}", d < 0.8, f"d={d:.2f}")
        shot(br.act({"action": "wait", "ms": 100}), "hs00_living.jpg")
        goto(br, -4.6, 1.2); goto(br, -5.25, 2.35); goto(br, -4.0, 3.9); goto(br, -1.9, 3.8); goto(br, -1.25, 2.9)
        d = goto(br, -1.25, -2.2, tol=0.6, tries=10)   # up the stairs onto the landing
        st = br.state()
        check("hs00: climbs the stairs to the landing (y~3)", st["pos"][1] > 4.4, f"pos={st['pos']}")
        shot(br.act({"action": "wait", "ms": 100}), "hs00_landing.jpg")
        d = goto(br, 0.6, 3.6, tol=0.6); d = goto(br, 2.6, 3.6, tol=0.6); d = goto(br, 4.4, 2.8, tol=0.7)
        check("hs00: reaches the upstairs lounge", d < 0.9, f"d={d:.2f} pos={br.state()['pos']}")
        shot(face(br, 4.4, 3.5, -0.04), "hs00_lounge.jpg")
        check("hs00: no respawn while patrolling", not respawned)
        for nm in ("DINING_CHAIR#1", "DINING_CHAIR#3", "BAR_STOOL#3"):
            mn = obj(br, nm)["min"][1]
            check(f"hs00: {nm} rests on the floor", abs(mn) < 0.08, f"min.y={mn:.2f}")
        # indoor clamp: push toward the (locked) front door / outside
        goto(br, 0.0, 3.8, tol=0.5); face(br, 0.0, 1.6, 9.0)
        for _ in range(2): walk(br, 3.0)
        z = br.state()["pos"][2]
        check("hs00: front door locked / bounds keep the player indoors", z < 4.7, f"z={z:.2f}")

        # ---- hs01 floating chair ----
        boot(br, "hs01-float")
        mn = obj(br, "DINING_CHAIR#1")["min"][1]
        check("hs01: chair floats (min.y>0.35)", mn > 0.35, f"min.y={mn:.2f}")
        goto(br, 2.0, 3.8); goto(br, 3.4, 4.2); goto(br, 5.0, 4.3, tol=0.4)
        shot(face(br, 5.11, 0.9, 2.91), "hs01_chair.jpg")

        # ---- hs02 sunken stool ----
        boot(br, "hs02-clip")
        mn = obj(br, "BAR_STOOL#3")["min"][1]
        check("hs02: stool clips below floor (min.y<-0.2)", mn < -0.2, f"min.y={mn:.2f}")
        goto(br, 2.0, 3.8); goto(br, 2.7, 3.6); goto(br, 2.7, -0.2); goto(br, 3.6, -0.3, tol=0.4)
        shot(face(br, 5.1, 0.3, -1.75), "hs02_stool.jpg")

        # ---- hs03 oversized chair ----
        boot(br, "hs03-scale")
        big, sib = obj(br, "DINING_CHAIR#3"), obj(br, "DINING_CHAIR#1")
        ratio = (big["max"][1] - big["min"][1]) / (sib["max"][1] - sib["min"][1])
        check("hs03: chair ~1.8x sibling height", 1.6 < ratio < 2.0, f"ratio={ratio:.2f}")
        check("hs03: oversized chair still grounded", abs(big["min"][1]) < 0.15, f"min.y={big['min'][1]:.2f}")
        goto(br, 2.0, 3.8); goto(br, 2.7, 3.6); goto(br, 2.5, 0.4, tol=0.4)
        shot(face(br, 3.69, 0.8, 1.49), "hs03_chair.jpg")

        # ---- hs04 double-spawned armchair ----
        def chair_closeup(cfg):
            boot(br, cfg)
            goto(br, -1.9, 3.8); goto(br, -3.6, 3.9); goto(br, -5.0, 3.9, tol=0.4)
            r = face(br, -6.1, 0.45, 2.6)
            shot(r, f"hs04_close_{cfg}.jpg")
            return img(r)
        a_bug = chair_closeup("hs04-doublespawn")
        dup, orig = obj(br, "ARMCHAIR#2_dup"), obj(br, "ARMCHAIR#2")
        check("hs04: duplicate exists", dup is not None)
        if dup:
            off = max(abs(dup["min"][i] - orig["min"][i]) for i in range(3))
            check("hs04: duplicate is co-located (offset < 0.12m)", off < 0.12, f"off={off:.3f}")
        a_cln = chair_closeup("hs00-clean")
        h, w, _ = a_bug.shape
        crop = lambda a: a[int(h*0.3):int(h*0.8), int(w*0.3):int(w*0.7)]
        hot = (np.abs(crop(a_bug) - crop(a_cln)).max(axis=2) > 30).mean()
        check("hs04: doubling visible in close-up vs clean", hot > 0.008, f"center hot={hot*100:.2f}%")

        # ---- hs05 air wall across the hall at z=0.9 ----
        boot(br, "hs05-airwall")
        goto(br, 0.6, 2.4, tol=0.4)
        face(br, 0.6, 1.6, -3.6)
        for _ in range(3): walk(br, 2.5)
        z = br.state()["pos"][2]
        check("hs05: blocked near z=1.4 (wall at 0.9)", 1.0 < z < 1.8, f"z={z:.2f}")
        shot(br.act({"action": "wait", "ms": 150}), "hs05_wall.jpg")
        # reachable around: dining -> kitchen -> hall north
        goto(br, 2.0, 3.8); goto(br, 2.7, 3.6); goto(br, 2.7, -0.2); goto(br, 4.4, -0.9); d = goto(br, 2.0, -3.4); d = goto(br, 0.6, -3.6)
        check("hs05: north hall reachable around via the kitchen", d < 0.9, f"d={d:.2f}")

        # ---- hs06 floor hole at (0.6,-1.9) ----
        boot(br, "hs06-hole")
        goto(br, 0.6, 2.0, tol=0.4); face(br, 0.6, 1.6, -3.6)
        resp = False
        for _ in range(3):
            r = walk(br, 2.5)
            resp |= r["respawned"]
            if resp: break
        check("hs06: falls through the hall floor and respawns", resp)
        p = br.state()["pos"]
        check("hs06: back at spawn after respawn", abs(p[0] - 0.55) < 0.5 and abs(p[2] - 3.9) < 0.5, f"pos={p}")

        # ---- hs07 ghost island: push through it from the dining side ----
        def island_push(cfg):
            # from the kitchen aisle (between counter and island) push south through the island
            boot(br, cfg)
            goto(br, 0.6, -3.6); goto(br, 2.0, -3.4); goto(br, 3.4, -3.65); goto(br, 4.4, -3.65, tol=0.35)
            face(br, 4.4, 0.9, -2.6)
            r = walk(br, 2.0)
            shot(r, f"hs07_push_{cfg}.jpg")
            return r["pos"][2]
        z_bug = island_push("hs07-ghostisland")
        check("hs07: island unbaked from collision", obj(br, "KITCHEN_ISLAND#1")["solid"] is False)
        check("hs07: island still visible", obj(br, "KITCHEN_ISLAND#1")["visible"] is True)
        z_cln = island_push("hs00-clean")
        check("hs07: walks THROUGH the ghost island (bug) but is blocked by it (clean)",
              z_bug > -2.5 and z_cln < -3.1, f"bug z={z_bug:.2f} clean z={z_cln:.2f}")

        # ---- hs08 trembling floor lamp ----
        boot(br, "hs08-jitter")
        xs = []
        for _ in range(6):
            br.act({"action": "wait", "ms": 250})
            xs.append(obj(br, "FLOOR_LAMP#1")["min"][0])
        span = max(xs) - min(xs)
        check("hs08: lamp trembles (0.01m < span < 0.2m)", 0.01 < span < 0.2, f"span={span:.3f}")
        check("hs08: lamp stays in place (no net drift)", abs(xs[-1] - xs[0]) < 0.1, f"net={abs(xs[-1] - xs[0]):.3f}")

        # ---- hs09 magenta TV console ----
        boot(br, "hs09-magenta")
        goto(br, -1.9, 3.8); goto(br, -4.0, 3.9); goto(br, -5.25, 2.35); goto(br, -4.6, 1.2); goto(br, -3.2, 1.5, tol=0.4)
        r = face(br, -3.2, 0.4, -0.86)
        a = img(r)
        h, w, _ = a.shape
        c = a[h // 3: 2 * h // 3, w // 3: 2 * w // 3]
        magenta = (c[..., 0] > 120) & (c[..., 2] > 120) & (c[..., 1] < 90)
        check("hs09: magenta dominates view center", magenta.mean() > 0.12, f"frac={magenta.mean():.2f}")
        shot(r, "hs09_console.jpg")
        check("hs09: only the console changed (sibling cabinet materials intact)",
              br.page.evaluate("() => { const o = window.__ctx.scene.getObjectByName('SIDEBOARD#1'); let ok = true; o.traverse(c => { if (c.isMesh && c.material.color.g < 0.2 && c.material.color.r > 0.9) ok = false; }); return ok; }"))

        # ---- hs10 backcull sofa: normal from the TV side, missing from the window side ----
        def sofa_view(cfg, behind):
            boot(br, cfg)
            goto(br, -1.9, 3.8)
            if behind:
                goto(br, -3.2, 4.3, tol=0.4)
            else:
                goto(br, -4.0, 3.9); goto(br, -5.25, 2.35); goto(br, -4.6, 1.2); goto(br, -2.6, 1.5, tol=0.4)
            r = face(br, -3.2, 0.6, 2.35)
            shot(r, f"hs10_{'behind' if behind else 'front'}_{cfg}.jpg")
            return img(r)
        a_bug = sofa_view("hs10-backcull", False)
        check("hs10: sofa visible from the front", obj(br, "SOFA#1")["visible"] is True and
              br.page.evaluate("() => { let v = true; window.__ctx.scene.getObjectByName('SOFA#1').traverse(c => { if (c.isMesh && !c.visible) v = false; }); return v; }"))
        a_cln = sofa_view("hs00-clean", False)
        small = lambda a: np.asarray(Image.fromarray(a.astype('uint8')).resize((120, 75)), float)
        diff = np.abs(small(a_bug) - small(a_cln)).mean()
        check("hs10: front view content-identical to clean", diff < 6, f"lowres diff={diff:.1f}")
        sofa_view("hs10-backcull", True)
        vis = br.page.evaluate("() => { let v = false; window.__ctx.scene.getObjectByName('SOFA#1').traverse(c => { if (c.isMesh && c.visible) v = true; }); return v; }")
        check("hs10: sofa invisible from behind", vis is False)

        # ---- hs11 x-ray coffee table ----
        boot(br, "hs11-xray")
        m = obj(br, "COFFEE_TABLE#1")
        check("hs11: depthTest disabled", m["depthTest"] is False)
        goto(br, 0.6, 1.2, tol=0.4)
        shot(face(br, -3.2, 0.4, 0.55), "hs11_through_wall.jpg")

        # ---- hs12 plant unload (visit -> leave -> gone on return) ----
        boot(br, "hs12-unload")
        n_ev = lambda: br.page.evaluate("() => window.__ctx.bugEvents.length")
        goto(br, -1.9, 3.8); goto(br, -4.4, 4.0, tol=0.5)      # within enterR=3.5 of the plant (-6.35,4.4)
        r = face(br, -6.35, 0.6, 4.4)
        shot(r, "hs12_before.jpg")
        check("hs12: plant present while visiting", obj(br, "PLANT#1")["visible"] is True)
        check("hs12: no fire while inside the area", n_ev() == 0, f"events={n_ev()}")
        goto(br, -1.9, 3.8); goto(br, 1.4, 3.6); goto(br, 1.4, -1.5)   # leave beyond exitR=7
        check("hs12: unload fires on leaving the area", n_ev() == 1, f"events={n_ev()}")
        check("hs12: plant gone", obj(br, "PLANT#1")["visible"] is False)
        goto(br, 0.6, 3.6); goto(br, -1.9, 3.8); goto(br, -3.6, 3.9)
        r = face(br, -6.35, 0.6, 4.4)
        shot(r, "hs12_after.jpg")
        check("hs12: still gone on return", obj(br, "PLANT#1")["visible"] is False)

        # ---- hs13 chair state reset on revisit ----
        boot(br, "hs13-statereset")
        n_ev = lambda: br.page.evaluate("() => window.__ctx.bugEvents.length")
        x0 = obj(br, "DINING_CHAIR#2")["min"][0]
        goto(br, 2.0, 3.8); goto(br, 2.7, 3.6); goto(br, 2.7, 1.5, tol=0.5)   # within enterR of the chair (5.11,1.49)
        check("hs13: no fire while visiting", n_ev() == 0, f"events={n_ev()}")
        goto(br, 2.0, 3.8); goto(br, -1.9, 3.8); goto(br, -4.0, 3.9)   # leave beyond exitR=7
        x1 = obj(br, "DINING_CHAIR#2")["min"][0]
        check("hs13: chair relocated after leaving", abs(x1 - x0) > 1.0, f"dx={x1 - x0:.2f}")
        check("hs13: exactly one reset event on leave", n_ev() == 1, f"events={n_ev()}")
        goto(br, -1.9, 3.8); goto(br, 2.0, 3.8); goto(br, 2.7, 3.6); goto(br, 2.7, 1.5)
        shot(face(br, 6.31, 0.5, 0.69), "hs13_after.jpg")

        # ---- hs14 rug texture LOD pop ----
        boot(br, "hs14-lodpop")
        n_ev = lambda: br.page.evaluate("() => window.__ctx.bugEvents.length")
        map_w = lambda: br.page.evaluate(
            "() => { let w = -1; window.__ctx.scene.getObjectByName('RUG#1').traverse(c => { if (c.isMesh && c.material.map && c.material.map.image) w = c.material.map.image.width; }); return w; }")
        goto(br, -1.9, 3.8); goto(br, -2.2, 4.4, tol=0.4)
        br.act({"action": "wait", "ms": 300})
        check("hs14: blocky low-res map beyond threshold (3.6 m)", map_w() == 8, f"map={map_w()}")
        goto(br, -4.0, 3.9); goto(br, -5.25, 2.35); goto(br, -4.6, 1.2); goto(br, -2.4, 1.5, tol=0.4)
        face(br, -3.2, 0.1, 0.9)
        check("hs14: pops back to sharp when near", map_w() > 64, f"map={map_w()}")
        check("hs14: pop events logged", n_ev() >= 2, f"events={n_ev()}")
        shot(br.act({"action": "wait", "ms": 100}), "hs14_rug_near.jpg")

        # ---- hs15 furniture pile in the hall ----
        boot(br, "hs15-spawnpile")
        piles = br.page.evaluate(
            "() => { const out = []; window.__ctx.scene.traverse(o => {"
            " if (!o.name.endsWith('_pile')) return;"
            " const b = new window.__ctx.THREE.Box3().setFromObject(o);"
            " out.push({ min: b.min.toArray(), max: b.max.toArray() }); }); return out; }")
        origs = [obj(br, n) for n in ("DINING_CHAIR#4", "BAR_STOOL#1", "NIGHTSTAND#1", "ARMCHAIR#1")]
        check("hs15: original furniture untouched", all(abs(o["min"][1]) < 0.1 or abs(o["min"][1] - 3.0) < 0.1 for o in origs))
        check("hs15: pile of cloned furniture present (4 pieces)", len(piles) == 4, f"n={len(piles)}")
        inter = 0
        for i in range(len(piles)):
            for j in range(i + 1, len(piles)):
                a, b = piles[i], piles[j]
                if all(a["min"][k] < b["max"][k] and a["max"][k] > b["min"][k] for k in range(3)):
                    inter += 1
        check("hs15: pieces interpenetrate (>=2 overlapping pairs)", inter >= 2, f"pairs={inter}")
        cx = sum((c["min"][0] + c["max"][0]) / 2 for c in piles) / max(1, len(piles))
        cz = sum((c["min"][2] + c["max"][2]) / 2 for c in piles) / max(1, len(piles))
        check("hs15: pile centered in the hall at (0.6,-0.6)", math.hypot(cx - 0.6, cz + 0.6) < 0.6, f"center=({cx:.2f},{cz:.2f})")
        goto(br, 0.6, 2.4, tol=0.4)
        shot(face(br, 0.6, 0.5, -0.6), "hs15_pile.jpg")

    n_ok = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n{n_ok}/{len(RESULTS)} assertions passed")
    (OUT / "report.md").write_text(
        "# HS suite behavioral verification\n\n" +
        "\n".join(f"- {'PASS' if ok else 'FAIL'} {name}" + (f" ({d})" if d else "")
                  for name, ok, d in RESULTS) + "\n")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
