"""Setting 2, stage 2: a strong VLM audits the VLA explorer's recording via VQA,
scored with TIERED accuracy:

  Tier E  (exposure):        did the bug observably manifest in this recording?
                             (env event log + gaze/trajectory geometry, per-case rules)
  Tier I|E (identification): given exposure, did any VQA claim match the planted bug
                             (LLM judge, same strict v2 prompt as Setting 1)?
  End-to-end found = E x I|E ;  plus clean-recording FP rate.

Usage:
  .venv/bin/python -m judge.vqa_audit runs/vla-p2p --base-url http://localhost:8010/v1 \
      --model Qwen/Qwen3-VL-32B-Instruct --out reports/sp-suite/vla-vqa-matrix.md
"""
import argparse
import base64
import json
import math
import re
from collections import defaultdict
from pathlib import Path

from judge.judge_sem import GT, JUDGE_PROMPT, LABELS
from agent.vla.vlm import VLMClient

CHUNK = 16          # frames per VQA call
VQA_W, VQA_H = 480, 300

VQA_SYSTEM = (
    "You are a game QA tester reviewing a first-person gameplay recording for BUGS. "
    "Frames are given in chronological order with timestamps.\n"
    "Bug types to check: (1) GEOMETRY & SPACE: clipping, floating objects, abnormal scale, "
    "duplicated/overlapping objects. (2) COLLISION & PHYSICS: passing through solid objects, "
    "blocked by nothing visible, falling through the floor / sudden teleport back, objects "
    "moving on their own. (3) VISUAL CONSISTENCY: missing textures (flat unnatural colors), "
    "objects visible through occluders, objects invisible from some viewpoints. "
    "(4) SPATIOTEMPORAL & STATE: objects that disappear or change position/color between "
    "observations of the same spot. (5) SEMANTICS: assets that do not belong.\n"
    "Normal scene content (plants, curtains, banners, pillars) is NOT a bug; identical "
    "elements should look and behave identically.\n"
    "If this clip shows no bug, reply exactly: NO_BUG\n"
    "Otherwise reply one line per bug: BUG: <short description> (around t=<seconds>s)")


def poses_of(ep):
    return [json.loads(l) for l in (ep / "poses.jsonl").read_text().splitlines()]


def gaze_hits(poses, target, dmax=8.0, dot_min=0.75):
    """Ticks at which target (x,z) is in the view cone and near."""
    hits = []
    for p in poses:
        px, _, pz = p["pos"]
        dx, dz = target[0] - px, target[1] - pz
        dist = math.hypot(dx, dz)
        if dist > dmax or dist < 1e-6:
            continue
        yaw = math.radians(p["yaw"])
        fx, fz = -math.sin(yaw), -math.cos(yaw)
        if (dx * fx + dz * fz) / dist > dot_min:
            hits.append(p["t"])
    return hits

# bug carrier positions (world x,z) per case
POS = {"sp01": (0.95, 1.23), "sp02": (6.67, 1.23), "sp03": (0.96, -1.78),
       "sp04": (6.67, -1.78), "sp07": (2.44, 1.56), "sp08": (-1.95, 1.22),
       "sp09": (2.44, 1.56), "sp10": (-0.49, 1.61), "sp11": (-1.95, -1.8),
       "sp12": (0.95, 1.23), "sp13": (6.67, 1.23), "sp14": (2.44, 1.56),
       "sp15": (0.0, 0.0),
       # HS suite (Family House; scripts/tools/gen_house_cases.py)
       "hs01": (5.11, 2.91), "hs02": (5.1, -1.75), "hs03": (3.69, 1.49), "hs04": (-6.1, 2.6),
       "hs07": (4.4, -2.6), "hs08": (-6.45, -0.75), "hs09": (-3.2, -0.86), "hs10": (-3.2, 2.35),
       "hs11": (-3.2, 0.55), "hs12": (-6.35, 4.4), "hs13": (5.11, 1.49), "hs14": (-3.2, 0.9),
       "hs15": (0.6, -0.6)}
# per-case exposure rule: the hs cases mirror sp type-for-type
KIND = {c: c for c in POS}
KIND.update({"sp05": "airwall", "sp06": "hole", "hs05": "airwall", "hs06": "hole",
             "hs01": "sp01", "hs02": "sp02", "hs03": "sp03", "hs04": "sp04", "hs07": "sp07",
             "hs08": "sp08", "hs09": "sp09", "hs10": "sp10", "hs11": "sp11", "hs12": "sp12",
             "hs13": "sp13", "hs14": "sp14", "hs15": "sp15", "sp01": "sp01"})
# airwall: (axis, wall coordinate); ghost object: crossing plane spec; backcull: "behind" predicate
AIRWALL = {"sp05": ("x", 2.5), "hs05": ("z", 0.9)}
GHOST_CROSS = {"sp07": ("z", 1.56, "x", 2.44, 1.15),    # crosses z=1.56 while |x-2.44|<1.15
               "hs07": ("z", -2.6, "x", 4.4, 1.0)}      # crosses the island's z line while within its x span
BEHIND = {"sp10": lambda p: p["pos"][2] > 1.75, "hs10": lambda p: p["pos"][2] > 2.5}
RESET_OFF = {"sp13": (0, -2.4), "hs13": (1.2, -0.8)}


def exposure(case, meta, poses):
    """Per-case rule: did the bug observably manifest in this recording?"""
    ev = meta.get("bug_events", [])
    kind = KIND.get(case, case)
    if kind in ("sp01", "sp02", "sp03", "sp04", "sp09", "sp11", "sp15"):
        return len(gaze_hits(poses, POS[case])) >= 10        # >=0.5s of clear view
    if kind == "airwall":  # blocked with W held near the wall line
        axis, at = AIRWALL[case]
        idx = 0 if axis == "x" else 2
        return any("KeyW" in p["keys"] and p["moved"] < 0.02 and abs(p["pos"][idx] - at) < 0.8
                   for p in poses)
    if kind == "hole":
        return any(e["type"] == "respawn" for e in ev)
    if kind == "sp07":  # ghost object: only manifestation is crossing its plane
        cax, cat, sax, sat, span = GHOST_CROSS[case]
        ci, si = (2, 0) if cax == "z" else (0, 2)
        for p, q in zip(poses, poses[1:]):
            if (abs(p["pos"][si] - sat) < span and abs(q["pos"][si] - sat) < span
                    and (p["pos"][ci] - cat) * (q["pos"][ci] - cat) < 0):
                return True
        return False
    if kind == "sp08":
        return len(gaze_hits(poses, POS[case], dmax=8)) >= 30    # >=1.5s watching the trembling object
    if kind == "sp10":  # backcull: manifests only when viewed FROM BEHIND
        behind = [p for p in poses if BEHIND[case](p)]
        return len(gaze_hits(behind, POS[case])) >= 10
    if kind == "sp12":
        t_fire = [e["t"] for e in ev if e["type"] == "despawn_fired"]
        if not t_fire:
            return False
        t0 = t_fire[0] / (meta["dt_ms"] / 1000)              # sim s -> tick index
        return len([t for t in gaze_hits(poses, POS[case]) if t > t0]) >= 10
    if kind == "sp13":
        t_fire = [e["t"] for e in ev if e["type"] == "teleport_fired"]
        if not t_fire:
            return False
        t0 = t_fire[0] / (meta["dt_ms"] / 1000)
        ox, oz = RESET_OFF[case]
        near = gaze_hits(poses, POS[case], dmax=9) + gaze_hits(poses, (POS[case][0] + ox, POS[case][1] + oz), dmax=9)
        return len([t for t in near if t > t0]) >= 10
    if kind == "sp14":  # a pop is observable if the carrier is in view within +-1s of the event
        pops = [e["t"] for e in ev if e["type"] == "lod_pop"]
        hits = gaze_hits(poses, POS[case], dmax=12, dot_min=0.6)
        dt = meta["dt_ms"] / 1000
        return any(any(abs(h * dt - p) < 1.0 for h in hits) for p in pops)
    return False


def b64frame(path):
    return base64.b64encode(path.read_bytes()).decode()


def vqa_episode(client, ep, meta):
    """Chunked VQA over the recording; returns list of claim strings."""
    from PIL import Image
    import io
    frames = meta["frames"]
    dt = meta["dt_ms"] * meta["record_every"] / 1000
    claims = []
    for c0 in range(0, len(frames), CHUNK):
        chunk = frames[c0:c0 + CHUNK]
        content = [{"type": "text", "text":
                    f"Recording clip: frames every {dt:.1f}s, t={c0 * dt:.0f}s to {(c0 + len(chunk)) * dt:.0f}s."}]
        for i, fn in enumerate(chunk):
            img = Image.open(ep / fn).convert("RGB").resize((VQA_W, VQA_H), Image.BILINEAR)
            buf = io.BytesIO(); img.save(buf, "JPEG", quality=80)
            content.append({"type": "text", "text": f"t={(c0 + i) * dt:.1f}s:"})
            content.append({"type": "image_url", "image_url": {
                "url": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()}})
        r = client.chat([{"role": "system", "content": VQA_SYSTEM},
                         {"role": "user", "content": content}])
        for line in r["text"].splitlines():
            line = line.strip()
            if line.startswith("BUG:"):
                claims.append(line[4:].strip())
    return claims


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_base")
    ap.add_argument("--base-url", default="http://localhost:8010/v1")
    ap.add_argument("--model", default="Qwen/Qwen3-VL-32B-Instruct")
    ap.add_argument("--judge-url", default="http://localhost:8010/v1")
    ap.add_argument("--judge-model", default="Qwen/Qwen3-VL-30B-A3B-Instruct")
    ap.add_argument("--out", default="reports/sp-suite/vla-vqa-matrix.md")
    ap.add_argument("--cache", default="runs/judge_cache_vqa_v3.json")
    ap.add_argument("--claims-out", default=None, help="claims jsonl path (dump / reload)")
    ap.add_argument("--stage", default="all", choices=["vqa", "judge", "all"],
                    help="vqa: run VQA + exposure, dump claims, stop; judge: reload claims and score")
    args = ap.parse_args()
    claims_p = Path(args.claims_out or (Path(args.run_base) / "claims.jsonl"))

    if args.stage == "judge":
        rows = [json.loads(l) for l in claims_p.read_text().splitlines()]
    else:
        eps = sorted(p for p in Path(args.run_base).iterdir() if (p / "meta.json").exists())
        client = VLMClient(base_url=args.base_url, model=args.model, temperature=0.0, max_tokens=400)
        rows = []
        for ep in eps:
            meta = json.loads((ep / "meta.json").read_text())
            case = meta["config"].split("-")[0]
            poses = poses_of(ep)
            exp = exposure(case, meta, poses) if case not in ("sp00", "hs00") else None
            claims = vqa_episode(client, ep, meta)
            rows.append(dict(ep=ep.name, case=case, exposed=exp, claims=claims))
            print(f"{ep.name}: exposed={exp} claims={len(claims)}")
        claims_p.write_text("\n".join(json.dumps(r) for r in rows))
        if args.stage == "vqa":
            print(f"claims dumped to {claims_p}; run --stage judge next")
            return

    # judge claims for bug episodes
    cache_p = Path(args.cache)
    cache = json.loads(cache_p.read_text()) if cache_p.exists() else {}
    judge = VLMClient(base_url=args.judge_url, model=args.judge_model, temperature=0.0, max_tokens=160)
    for r in rows:
        if r["case"] in ("sp00", "hs00"):
            continue
        for cl in r["claims"]:
            key = f"{r['case']}||{cl.lower()}"
            if key not in cache:
                resp = judge.chat([{"role": "user", "content":
                                    JUDGE_PROMPT.format(gt=GT[r["case"]], note=cl)}])
                m = re.search(r'"match"\s*:\s*(true|false)', resp["text"], re.I)
                cache[key] = (m.group(1).lower() == "true") if m else False
    cache_p.write_text(json.dumps(cache))

    # Event-timed cases: a judge-matched claim must also cite a time inside the logged
    # event window [event-3s, event+8s] - otherwise a coincidentally-phrased egomotion
    # hallucination elsewhere in the recording collects false credit (observed on sp12:
    # claim about t=24-26s matched while the despawn fired at t=2.1s).
    EVENT_TYPE = {"sp06": "respawn", "sp12": "despawn_fired",
                  "sp13": "teleport_fired", "sp14": "lod_pop",
                  "hs06": "respawn", "hs12": "despawn_fired",
                  "hs13": "teleport_fired", "hs14": "lod_pop"}

    def time_ok(r, claim):
        ct = [float(x) for x in re.findall(r"t\s*=\s*(\d+(?:\.\d+)?)", claim)]
        if r["case"] in EVENT_TYPE:
            meta = json.loads((Path(args.run_base) / r["ep"] / "meta.json").read_text())
            ev_ts = [e["t"] for e in meta.get("bug_events", []) if e["type"] == EVENT_TYPE[r["case"]]]
            return any(ev - 3 <= t <= ev + 8 for ev in ev_ts for t in ct)
        if r["case"] == "sp10":
            # the defect is observable only while gazing at the drape FROM BEHIND: claims
            # citing other moments are egomotion artifacts riding on the GT phrasing
            meta = json.loads((Path(args.run_base) / r["ep"] / "meta.json").read_text())
            poses = poses_of(Path(args.run_base) / r["ep"])
            behind = [p for p in poses if p["pos"][2] > 1.75]
            hits = gaze_hits(behind, POS["sp10"])
            if not hits:
                return False
            dt = meta["dt_ms"] / 1000
            lo, hi = min(hits) * dt - 2, max(hits) * dt + 3
            return any(lo <= t <= hi for t in ct)
        return True

    # joint fallback: a QA report is read as a whole - if no single claim matches but the
    # episode has several, judge the concatenated claim set once (complementary partial
    # observations, e.g. "disappeared at A" + "appeared at B" + "state reset", can jointly
    # describe the defect). Same time gate applies to the concatenation.
    from judge.judge_sem import load_adjudications
    adjud = load_adjudications()
    verdict = lambda key: adjud.get(key, cache.get(key, False))

    def joint_match(r):
        if len(r["claims"]) < 2:
            return False
        note = " ; ".join(dict.fromkeys(r["claims"]))
        key = f"{r['case']}||JOINT||{r['ep']}"
        if key in adjud:
            return adjud[key]
        if key not in cache:
            resp = judge.chat([{"role": "user", "content":
                                JUDGE_PROMPT.format(gt=GT[r["case"]], note=note)}])
            m = re.search(r'"match"\s*:\s*(true|false)', resp["text"], re.I)
            cache[key] = (m.group(1).lower() == "true") if m else False
            cache_p.write_text(json.dumps(cache))
        return cache[key] and time_ok(r, note)

    per = defaultdict(lambda: dict(n=0, e=0, found=0, joint=0))
    fp_eps = fp_n = 0
    claims_exposed = claims_all = tp_total = clean_claims = 0
    for r in rows:
        if r["case"] in ("sp00", "hs00"):
            fp_n += 1
            fp_eps += bool(r["claims"])
            clean_claims += len(r["claims"])
            claims_all += len(r["claims"])
            continue
        v = per[r["case"]]
        v["n"] += 1
        claims_all += len(r["claims"])
        if r["exposed"]:
            v["e"] += 1
            claims_exposed += len(r["claims"])
            if any(verdict(f"{r['case']}||{c.lower()}") and time_ok(r, c)
                   for c in r["claims"]):
                v["found"] += 1
                tp_total += 1
            elif joint_match(r):
                v["found"] += 1
                v["joint"] += 1
                tp_total += 1

    explorer = {json.loads((p / "meta.json").read_text()).get("model", "?")
                for p in Path(args.run_base).iterdir() if (p / "meta.json").exists()}
    lines = [f"# VQA audit with tiered accuracy - {Path(args.run_base).name}",
             "",
             f"Explorer: {'/'.join(sorted(explorer))}; auditor: {args.model.split('/')[-1]}; judge: {args.judge_model.split('/')[-1]} (strict v2).",
             "Tier E = bug observably manifested in the recording (env events + gaze geometry).",
             "Tier I|E = a VQA claim judge-matched to the planted bug, given exposure; for",
             "event-timed cases (fall-through/despawn/teleport/colorflip) the claim's cited time",
             "must also fall in the logged event window [event-3s, event+8s].",
             "",
             "| case | exposed | found given exposed | end-to-end |",
             "|---|---|---|---|"]
    E = I = N = 0
    for case in sorted(per):
        v = per[case]
        E += v["e"]; I += v["found"]; N += v["n"]
        j = " (joint)" if v["joint"] else ""
        lines.append(f"| {case} {LABELS.get(case, '')} | {v['e']}/{v['n']} | "
                     f"{v['found']}/{v['e'] if v['e'] else 0}{j} | {v['found']}/{v['n']} |")
    lines.append(f"| **total** | {E}/{N} | {I}/{E if E else 0} | {I}/{N} |")
    lines.append(f"\nClean-recording FP: {fp_eps}/{fp_n} episodes with >=1 claim.")
    # detection-style P/R/F1, same convention as Setting 1 (<=1 TP per instance;
    # surplus claims and clean-episode claims are FP)
    def prf(tp, fp, fn):
        p = tp / (tp + fp) if tp + fp else 0.0
        rr = tp / (tp + fn) if tp + fn else 0.0
        f = 2 * p * rr / (p + rr) if p + rr else 0.0
        return p, rr, f
    p1, r1, f1 = prf(tp_total, claims_exposed - tp_total, E - tp_total)
    p2, r2, f2 = prf(tp_total, claims_all - tp_total, N - tp_total)
    lines.append("\n| metric scope | P | R | F1 | TP | claims |")
    lines.append("|---|---|---|---|---|---|")
    lines.append(f"| given a video with the bug (exposed episodes only) | {p1:.2f} | {r1:.2f} | {f1:.2f} | {tp_total} | {claims_exposed} |")
    lines.append(f"| end-to-end (all bug + clean episodes) | {p2:.2f} | {r2:.2f} | {f2:.2f} | {tp_total} | {claims_all} |")
    out = "\n".join(lines) + "\n"
    Path(args.out).write_text(out)
    print(out)


if __name__ == "__main__":
    main()
