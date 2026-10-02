"""Behavioral verification of the SP (Sponza-native) test suite: every planted bug must
demonstrably manifest, and the clean hall must be fully patrollable.
Usage: .venv/bin/python -m agent.vla.sp_verify
Output: runs/sp-verify/ screenshots + assertion table on stdout
"""
import base64
import io
import math

import numpy as np
from PIL import Image

from agent.vla.bridge import Bridge
from agent.vla.runner import REPO

OUT = REPO / "runs" / "sp-verify"
OUT.mkdir(parents=True, exist_ok=True)
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), str(detail)))
    print(("  PASS " if ok else "  FAIL ") + name + (f"  ({detail})" if detail else ""))


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
    if abs(turn) > 0.5:
        br.act({"action": "turn", "deg": round(turn, 1)})
    phi = math.degrees(math.atan2(ty - py, math.hypot(dx, dz)))
    look = br.state()["pitch"] - phi
    if abs(look) > 0.5:
        br.act({"action": "look", "deg": round(look, 1)})
    return br.act({"action": "wait", "ms": 150})


MESH_JS = """(name) => {
  const o = window.__ctx.scene.getObjectByName(name);
  if (!o) return null;
  o.updateMatrixWorld(true);
  o.geometry.computeBoundingBox();
  const bb = o.geometry.boundingBox.clone().applyMatrix4(o.matrixWorld);
  return { visible: o.visible, min: bb.min.toArray(), max: bb.max.toArray(),
           depthTest: o.material ? o.material.depthTest : null,
           side: o.material ? o.material.side : null,
           color: o.material && o.material.color ? '#' + o.material.color.getHexString() : null,
           solid: window.__ctx.worldMeshes.includes(o) };
}"""


def mesh(br, name):
    return br.page.evaluate(MESH_JS, name)


def boot(br, cfg):
    br.open_env(cfg, seed=5)
    br.page.evaluate("() => window.__env.enable()")
    errs = br.console_errors()
    check(f"{cfg}: no console errors", not errs, str(errs)[:100])


def walk(br, dist):
    return br.act({"action": "forward", "dist": dist})


def main():
    with Bridge() as br:
        # ---- sp00 clean: full patrol must be unobstructed ----
        boot(br, "sp00-clean")
        respawned = False
        for i in range(6):
            r = walk(br, 3.0)
            respawned |= r["respawned"]
            if i == 2:
                shot(r, "sp00_mid.jpg")
        x = br.state()["pos"][0]
        check("sp00: full hall walkable (reach x>8)", x > 8, f"x={x:.2f}")
        check("sp00: no respawn on clean floor", not respawned)
        for nm in ("mesh_0_88", "mesh_0_90"):
            mn = mesh(br, nm)["min"][1]
            check(f"sp00: {nm} rests on floor", abs(mn) < 0.15, f"min.y={mn:.2f}")

        # ---- sp01 floating pot ----
        boot(br, "sp01-float")
        mn = mesh(br, "mesh_0_88")["min"][1]
        check("sp01: pot floats (min.y>0.35)", mn > 0.35, f"min.y={mn:.2f}")
        shot(face(br, 0.95, 0.9, 1.23), "sp01_pot.jpg")

        # ---- sp02 sunken pot ----
        boot(br, "sp02-clip")
        mn = mesh(br, "mesh_0_90")["min"][1]
        check("sp02: pot clips below floor (min.y<-0.15)", mn < -0.15, f"min.y={mn:.2f}")
        for _ in range(2): walk(br, 3.0)
        shot(face(br, 6.67, 0.2, 1.23), "sp02_pot.jpg")

        # ---- sp03 oversized pot ----
        boot(br, "sp03-scale")
        h_big = mesh(br, "mesh_0_94")
        h_sib = mesh(br, "mesh_0_92")
        ratio = (h_big["max"][1] - h_big["min"][1]) / (h_sib["max"][1] - h_sib["min"][1])
        check("sp03: pot ~2.2x sibling height", 1.9 < ratio < 2.5, f"ratio={ratio:.2f}")
        base = mesh(br, "mesh_0_94")["min"][1]
        check("sp03: oversized pot still grounded", abs(base) < 0.2, f"min.y={base:.2f}")
        shot(face(br, 0.96, 0.8, -1.78), "sp03_pot.jpg")

        # ---- sp04 double-spawned pot (co-located duplicate) ----
        def pot_closeup(cfg):
            boot(br, cfg)
            face(br, 5.4, 1.0, -0.7)
            for _ in range(3): walk(br, 2.9)
            st = br.state()
            d = math.hypot(5.4 - st["pos"][0], -0.7 - st["pos"][2])
            if d > 0.5:
                face(br, 5.4, 1.0, -0.7); walk(br, round(d, 1))
            r = face(br, 6.67, 0.35, -1.78)
            shot(r, f"sp04_close_{cfg}.jpg")
            return img(r)
        a_bug = pot_closeup("sp04-doublespawn")
        dup = mesh(br, "mesh_0_92_dup")
        orig = mesh(br, "mesh_0_92")
        check("sp04: duplicate exists", dup is not None)
        if dup:
            off = max(abs(dup["min"][i] - orig["min"][i]) for i in range(3))
            check("sp04: duplicate is co-located (offset < 0.12m)", off < 0.12, f"off={off:.3f}")
        a_cln = pot_closeup("sp00-clean")
        h, w, _ = a_bug.shape
        crop = lambda a: a[int(h*0.3):int(h*0.75), int(w*0.35):int(w*0.65)]  # pot is centered
        hot = (np.abs(crop(a_bug) - crop(a_cln)).max(axis=2) > 30).mean()
        check("sp04: doubling visible in close-up vs clean", hot > 0.008, f"center hot={hot*100:.2f}%")

        # ---- sp05 air wall ----
        boot(br, "sp05-airwall")
        moved = 0.0
        for _ in range(4):
            r = walk(br, 3.0)
            moved += r["moved"]
        x = br.state()["pos"][0]
        check("sp05: blocked near x=2.1 (wall at 2.5)", 0.8 < x < 2.4, f"x={x:.2f}")
        shot(br.act({"action": "wait", "ms": 150}), "sp05_wall.jpg")

        # ---- sp06 floor hole ----
        boot(br, "sp06-hole")
        resp = False
        for _ in range(3):
            r = walk(br, 2.5)
            resp |= r["respawned"]
            if resp: break
        check("sp06: falls through floor and respawns", resp)
        px = br.state()["pos"][0]
        check("sp06: back at spawn after respawn", px < -7.5, f"x={px:.2f}")

        # ---- sp07 ghost drape: push perpendicular through it into the aisle ----
        def drape_push(cfg):
            boot(br, cfg)
            face(br, 2.44, 1.0, -0.4)
            for _ in range(3): walk(br, 3.0)
            st = br.state()
            face(br, 2.44, 1.0, -0.4)
            d = math.hypot(2.44 - st["pos"][0], -0.4 - st["pos"][2])
            if d > 0.35: walk(br, round(d, 1))
            face(br, 2.44, 1.0, 1.56)
            r = walk(br, 3.4)
            shot(r, f"sp07_push_{cfg}.jpg")
            return r["pos"][2]
        z_bug = drape_push("sp07-ghostdrape")
        check("sp07: drape unbaked from collision", mesh(br, "mesh_0_67")["solid"] is False)
        check("sp07: drape still visible", mesh(br, "mesh_0_67")["visible"] is True)
        z_cln = drape_push("sp00-clean")
        check("sp07: walks THROUGH ghost drape (bug) but is blocked by it (clean)",
              z_bug > 1.9 and z_cln < 1.3, f"bug z={z_bug:.2f} clean z={z_cln:.2f}")

        # ---- sp08 trembling pot (physics jitter) ----
        boot(br, "sp08-jitter")
        xs = []
        for _ in range(6):
            br.act({"action": "wait", "ms": 250})
            xs.append(mesh(br, "mesh_0_86")["min"][0])
        span = max(xs) - min(xs)
        check("sp08: pot trembles (0.02m < span < 0.25m)", 0.02 < span < 0.25, f"span={span:.3f}")
        check("sp08: pot stays in place (no net drift)", abs(xs[-1] - xs[0]) < 0.15,
              f"net={abs(xs[-1] - xs[0]):.3f}")

        # ---- sp09 magenta drape ----
        boot(br, "sp09-magenta")
        for _ in range(3): walk(br, 3.0)
        r = face(br, 2.44, 1.1, 1.56)
        a = img(r)
        h, w, _ = a.shape
        c = a[h // 3: 2 * h // 3, w // 3: 2 * w // 3]
        magenta = (c[..., 0] > 120) & (c[..., 2] > 120) & (c[..., 1] < 90)
        check("sp09: magenta dominates view center", magenta.mean() > 0.2, f"frac={magenta.mean():.2f}")
        shot(r, "sp09_drape.jpg")

        # ---- sp10 backcull drape: normal from the hall, missing when seen from behind ----
        def hall_view(cfg):
            boot(br, cfg)
            for _ in range(2): walk(br, 3.0)
            face(br, -0.49, 1.1, 1.61)
            walk(br, 1.2)
            r1 = face(br, -0.49, 1.1, 1.61)
            shot(r1, f"sp10_hall_{cfg}.jpg")
            return img(r1)
        a_bug = hall_view("sp10-backcull")
        check("sp10: drape visible from the hall", mesh(br, "mesh_0_63")["visible"] is True)
        a_cln = hall_view("sp00-clean")
        # compare at low res: frame timing differs slightly across configs, causing sub-pixel
        # camera shifts; content differences (the v1 culled drape) survive downscaling
        small = lambda a: np.asarray(Image.fromarray(a.astype('uint8')).resize((120, 75)), float)
        diff = np.abs(small(a_bug) - small(a_cln)).mean()
        check("sp10: hall view content-identical to clean", diff < 5, f"lowres diff={diff:.1f}")
        # go around: east past the last drape, into the north aisle, west to behind the drape
        boot(br, "sp10-backcull")
        for wp in [(7.6, -0.3), (7.6, 2.8), (0.6, 2.8), (-0.49, 2.9)]:
            for _ in range(6):
                st = br.state()
                d = math.hypot(wp[0] - st["pos"][0], wp[1] - st["pos"][2])
                if d < 0.7: break
                face(br, wp[0], 1.0, wp[1])
                walk(br, round(min(d, 3.0), 1))
        st = br.state()
        reached = math.hypot(-0.49 - st["pos"][0], 2.9 - st["pos"][2]) < 2.0
        check("sp10: reached the aisle behind the drape", reached,
              f"pos=({st['pos'][0]:.1f},{st['pos'][2]:.1f})")
        r = face(br, -0.49, 1.1, 1.61)
        shot(r, "sp10_behind_bug.jpg")
        check("sp10: drape invisible from behind", mesh(br, "mesh_0_63")["visible"] is False)
        check("sp10: neighbor drape still visible from behind", mesh(br, "mesh_0_64")["visible"] is True)

        # ---- sp11 x-ray pot ----
        boot(br, "sp11-xray")
        m = mesh(br, "mesh_0_2")
        check("sp11: depthTest disabled", m["depthTest"] is False)
        shot(face(br, -1.95, 0.4, -1.8), "sp11_pot.jpg")

        # ---- sp12 streaming unload (visit -> leave -> gone on return) ----
        boot(br, "sp12-unload")
        n_ev = lambda: br.page.evaluate("() => window.__ctx.bugEvents.length")
        walk(br, 4.0); walk(br, 2.4)      # within enterR=5 of the pot
        r = face(br, 0.95, 0.6, 1.23)
        shot(r, "sp12_before.jpg")
        check("sp12: pot present while visiting", mesh(br, "mesh_0_88")["visible"] is True)
        check("sp12: no fire while inside the area", n_ev() == 0, f"events={n_ev()}")
        br.act({"action": "turn", "deg": 180})
        check("sp12: turning alone does NOT fire (distance trigger)", n_ev() == 0)
        face(br, -8.4, 1.0, -0.3)         # head straight back west along the walkway
        for _ in range(3): walk(br, 2.6)  # walk away beyond exitR=9
        check("sp12: unload fires on leaving the area", n_ev() == 1, f"events={n_ev()}")
        check("sp12: pot gone", mesh(br, "mesh_0_88")["visible"] is False)
        face(br, 0.95, 1.0, 1.23)
        for _ in range(2): walk(br, 3.0)  # come back
        r = face(br, 0.95, 0.6, 1.23)
        shot(r, "sp12_after.jpg")
        check("sp12: still gone on return (never respawns)", mesh(br, "mesh_0_88")["visible"] is False)

        # ---- sp13 state reset on revisit (leave -> position changed) ----
        boot(br, "sp13-statereset")
        n_ev = lambda: br.page.evaluate("() => window.__ctx.bugEvents.length")
        z0 = mesh(br, "mesh_0_90")["min"][2]
        for _ in range(4): walk(br, 3.1)  # to ~x4, within enterR of the pot at (6.67,1.23)
        face(br, 6.67, 0.6, 1.23)
        check("sp13: no fire while visiting", n_ev() == 0, f"events={n_ev()}")
        face(br, -8.4, 1.0, -0.3)         # straight back west
        for _ in range(4): walk(br, 3.1)  # leave beyond exitR=9
        z1 = mesh(br, "mesh_0_90")["min"][2]
        check("sp13: pot relocated after leaving", abs(z1 - z0) > 2.0, f"dz={z1 - z0:.2f}")
        check("sp13: exactly one reset event on leave", n_ev() == 1, f"events={n_ev()}")
        br.act({"action": "turn", "deg": 180})
        shot(br.act({"action": "wait", "ms": 150}), "sp13_after.jpg")

        # ---- sp14 texture LOD pop (distance-driven) ----
        boot(br, "sp14-lodpop")
        n_ev = lambda: br.page.evaluate("() => window.__ctx.bugEvents.length")
        map_w = lambda: br.page.evaluate(
            "() => { const m = window.__ctx.scene.getObjectByName('mesh_0_67').material.map;"
            " return m && m.image ? m.image.width : -1; }")
        br.act({"action": "wait", "ms": 300})
        check("sp14: blocky low-res map beyond threshold", map_w() == 8, f"map={map_w()}")
        for _ in range(3): walk(br, 2.4)   # approach within 5.6m
        face(br, 2.44, 1.1, 1.56)
        check("sp14: pops back to sharp when near", map_w() > 64, f"map={map_w()}")
        check("sp14: pop events logged", n_ev() >= 2, f"events={n_ev()}")

        # ---- sp15 pile of cloned real props at world origin ----
        boot(br, "sp15-spawnpile")
        crates = br.page.evaluate(
            "() => { const out = []; window.__ctx.scene.traverse(o => {"
            " if (!o.isMesh || !o.name.endsWith('_pile')) return;"
            " o.geometry.computeBoundingBox();"
            " const b = o.geometry.boundingBox.clone().applyMatrix4(o.matrixWorld);"
            " out.push({ min: b.min.toArray(), max: b.max.toArray() }); }); return out; }")
        origs = [mesh(br, n) for n in ("mesh_0_88", "mesh_0_92", "mesh_0_90")]
        check("sp15: original props untouched at their spots",
              all(abs(o["min"][1]) < 0.15 for o in origs))
        check("sp15: pile of cloned real props present (>=6 meshes)", len(crates) >= 6, f"n={len(crates)}")
        inter = 0
        for i in range(len(crates)):
            for j in range(i + 1, len(crates)):
                a, b = crates[i], crates[j]
                if all(a["min"][k] < b["max"][k] and a["max"][k] > b["min"][k] for k in range(3)):
                    inter += 1
        check("sp15: props interpenetrate (>=2 overlapping pairs)", inter >= 2, f"pairs={inter}")
        cx = sum((c["min"][0] + c["max"][0]) / 2 for c in crates) / len(crates)
        cz = sum((c["min"][2] + c["max"][2]) / 2 for c in crates) / len(crates)
        check("sp15: pile centered at world origin", math.hypot(cx, cz) < 0.6,
              f"center=({cx:.2f},{cz:.2f})")
        for _ in range(2): walk(br, 3.0)
        shot(face(br, 0.0, 0.5, 0.0), "sp15_pile.jpg")

    n_ok = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n{n_ok}/{len(RESULTS)} assertions passed")
    (OUT / "report.md").write_text(
        "# SP suite behavioral verification\n\n" +
        "\n".join(f"- {'PASS' if ok else 'FAIL'} {name}" + (f" ({d})" if d else "")
                  for name, ok, d in RESULTS) + "\n")
    return 0 if n_ok == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
