#!/usr/bin/env python3
"""Automatic ESTIMATE of a VLA-replay batch's detection rate: the strict text judge of judge/judge_sem.py (JUDGE_PROMPT)
run by gemini-3.8-flash (thinking low) on every ledger entry against the task's English rubric criterion, exactly the
estimate used for the earlier VLA reports (judge/vla_video_judge.py).  It is NOT the GPT-6 binary judge (judge/judge.py:
rubric + ledger + evidence screenshots) that the embodied batches are graded with; run
agent/vla/replay.py --stage judge for that once Codex is logged in.

usage: .venv/bin/python -m judge.vla_replay_estimate out/native-agents/batches/<batch> [--profiles ...] [--workers 8]
Writes <batch>/estimate-gemini-judge.json and .md (per episode: flags, matches, cost) and prints the summary.
"""
import argparse, concurrent.futures, json, pathlib, sys, threading

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from judge.vla_video_judge import api_key, judge_report  # noqa: E402


def episode_cost(run, price):
    events = run / "native-events.jsonl"
    if not events.exists():
        return None
    for line in events.read_text().splitlines():
        if '"result"' not in line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("type") != "result":
            continue
        if "total_cost_usd" in r:                       # Claude Code
            return round(float(r["total_cost_usd"]), 3)
        stats = r.get("stats") or {}                     # Gemini CLI
        c = 0.0
        for m, x in stats.get("models", {}).items():
            p = price.get(m)
            if not p:
                return None
            c += x["input"] / 1e6 * p["input_per_million"] + x["cached"] / 1e6 * p["cached_input_per_million"] + x["output_tokens"] / 1e6 * p["output_per_million"]
        return round(c, 3)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("batch"); ap.add_argument("--profiles", default=str(REPO / "reports/ue-aws-profiles-20260918.json"))
    ap.add_argument("--exposure", default=None, help="exposure.json of the recordings (default: <recordings>/exposure.json from selection.json)")
    ap.add_argument("--workers", type=int, default=8); ap.add_argument("--model", default="gemini-3.8-flash")
    a = ap.parse_args()
    batch = pathlib.Path(a.batch)
    sel = json.loads((batch / "selection.json").read_text())
    prof = json.loads(pathlib.Path(a.profiles).read_text())["tasks"]
    price = json.loads((REPO / "agent/vlm/native/pricing.json").read_text())["models"]
    exp_path = pathlib.Path(a.exposure) if a.exposure else pathlib.Path(sel["recordings"]) / "exposure.json"
    exposure = {r.get("task") or r.get("config"): r for r in json.loads(exp_path.read_text())} if exp_path.exists() else {}
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key())
    out_json = batch / "estimate-gemini-judge.json"
    done = {r["task"]: r for r in json.loads(out_json.read_text())} if out_json.exists() else {}
    lock = threading.Lock()

    def work(t):
        tid = t["id"]
        if tid in done:
            return done[tid]
        run = batch / "cases" / tid / "run"
        meta_path = run / "episode/meta.json"
        rec = {"task": tid, "family": t.get("family"), "subcategory": t.get("subcategory"), "gt": prof[tid]["task"]["rubrics_i18n"]["en"]["criteria"],
               "status": None, "flags": [], "found": False, "cost_usd": episode_cost(run, price), "exposed": exposure.get(tid, {}).get("exposed")}
        if not meta_path.exists():
            rec["status"] = "missing"; return rec
        meta = json.loads(meta_path.read_text()); rec["status"] = meta["status"]
        for f in meta.get("flags", []):
            note = f"{f['note']} (category: {f.get('category')}, {f.get('status')})"
            match, jtext, _ = judge_report(client, types, a.model, rec["gt"], note)
            rec["flags"].append({"id": f["id"], "status": f["status"], "category": f["category"], "evidence": f.get("evidence", []),
                                 "note": f["note"], "match": match, "judge_text": jtext[-200:]})
        rec["found"] = any(x["match"] for x in rec["flags"])
        return rec

    tasks = sel["tasks"]
    listed = {t["id"] for t in tasks}
    for d in sorted((batch / "cases").iterdir()):                 # cases added later with --resume are not in selection.json
        if d.name not in listed and d.name in prof and (d / "run/episode/meta.json").exists():
            tasks.append({"id": d.name, "family": prof[d.name]["family"], "subcategory": prof[d.name]["task"].get("subcategory")})
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as ex:
        rows = list(ex.map(work, tasks))
    out_json.write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    graded = [r for r in rows if r["status"] == "completed"]
    found = sum(1 for r in graded if r["found"]); n_flags = sum(len(r["flags"]) for r in graded); matched = sum(1 for r in graded for x in r["flags"] if x["match"])
    costs = [r["cost_usd"] for r in graded if r["cost_usd"] is not None]
    by = {}
    for r in graded:
        g = by.setdefault(r["family"], [0, 0]); g[0] += 1; g[1] += r["found"]
    ex_rows = [r for r in graded if r["exposed"]]; nex_rows = [r for r in graded if r["exposed"] is False]
    lines = [f"# Estimated detection (Gemini strict text judge, NOT the GPT-6 judge) - {batch.name}", "",
             f"agent {sel.get('client')} {sel.get('model') or ''} mode {sel.get('replay_mode')}; {len(graded)} completed episodes of {len(rows)}", "",
             f"- found (>= 1 ledger entry matches the planted bug): **{found}/{len(graded)}** ({found / max(len(graded), 1):.0%})",
             f"- ledger entries {n_flags}, matched {matched}, unmatched {n_flags - matched} (precision {matched / max(n_flags, 1):.0%}); episodes with >= 1 entry {sum(1 for r in graded if r['flags'])}",
             f"- heuristic exposure: exposed {sum(1 for r in ex_rows if r['found'])}/{len(ex_rows)} found, not exposed {sum(1 for r in nex_rows if r['found'])}/{len(nex_rows)} found",
             f"- cost per episode (list price): mean ${sum(costs) / max(len(costs), 1):.3f}, total ${sum(costs):.2f}", "",
             "| family | episodes | found |", "|---|---:|---:|"] + [f"| {k} | {v[0]} | {v[1]} |" for k, v in sorted(by.items())] + ["",
             "| case | sub | exposed | found | entries | cost | first entry |", "|---|---|---|---|---:|---:|---|"]
    for r in rows:
        first = (r["flags"][0]["note"][:100] if r["flags"] else "-").replace("|", "/")
        cost = "" if r["cost_usd"] is None else f"${r['cost_usd']:.2f}"
        exposed = "yes" if r["exposed"] else "no" if r["exposed"] is False else "?"
        lines.append(f"| {r['task']} | {r['subcategory']} | {exposed} | {'yes' if r['found'] else 'no'} | {len(r['flags'])} | {cost} | {first} |")
    (batch / "estimate-gemini-judge.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:12]))


if __name__ == "__main__":
    main()
