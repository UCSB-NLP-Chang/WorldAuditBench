#!/usr/bin/env python3
"""Export a VLA-replay batch into a self-contained results folder for offline grading (the GPT-6 binary judge of
judge/judge.py, run elsewhere): one folder per VLM, one case per task, the same judge-input rule as the embodied batches.

<out>/<name>/
  README.md, selection.json, results.json, results.md, estimate-gemini-judge.{json,md} (if present), costs.csv
  cases/<TASK>/judge-input.json   {bugs: final active ledger, summary: done summary, attached_evidence: [{image, ref, file}]}
               rubric.json        the rubric captured for this run (for the judge only)
               frames/<file>      the evidence frames listed in attached_evidence (evidence refs in chronological order;
                                  if the ledger cites none, the first and last view)
               meta.json, mcp-calls.jsonl, launch.json, episode-config.json, prompt.txt, cost.json, native-stderr.log
usage: python3 scripts/experiments/export_vla_results.py --batch out/native-agents/batches/<batch> --out ~/vla-results --name gemini-3.8-flash-medium-vqa
"""
import argparse, csv, json, pathlib, shutil, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from judge.judge import usage_from_events


def export_rubric(case, out, profile):
    if (case / 'rubric.json').exists():
        shutil.copyfile(case / 'rubric.json', out / 'rubric.json')
        return
    # Older, ungraded batches did not snapshot their rubrics.
    if profile is None:
        raise ValueError(f"No saved rubric or archival profile for {case.name}")
    task = profile['task']
    (out / 'rubric.json').write_text(json.dumps({
        'case_type': profile['case_type'], 'rubrics': task['rubrics_i18n']['en'],
        'title': task.get('title'), 'subcategory': task.get('subcategory')},
        ensure_ascii=False, indent=2) + '\n')


def episode_cost(run, price):
    events = run / "native-events.jsonl"
    if not events.exists():
        return {}
    raw = events.read_text()
    codex = usage_from_events(raw)
    if codex["completed_turns"]:
        manifest = json.loads((run / "launch.json").read_text())
        seconds = manifest.get("cli_wall_s")
        return {"client": "codex", **codex, **codex["usage"], "cost_usd": None,
                "cost_basis": "ChatGPT subscription; no API invoice inferred",
                "duration_ms": seconds * 1000 if seconds is not None else None,
                "duration_source": "measured CLI subprocess wall time" if seconds is not None else "unavailable"}
    if raw.startswith('{"type":"step_start"') or '"type":"step_finish"' in raw[:4000]:   # OpenCode --format json: one step_finish per model call
        steps = [json.loads(l) for l in raw.splitlines() if l.startswith('{"type":"step_finish"')]
        tok = {"input": 0, "output": 0, "reasoning": 0, "cache_read": 0, "cache_write": 0}; cost = 0.0; times = []
        for st in steps:
            t = st["part"].get("tokens", {}); tok["input"] += t.get("input", 0); tok["output"] += t.get("output", 0); tok["reasoning"] += t.get("reasoning", 0)
            tok["cache_read"] += (t.get("cache") or {}).get("read", 0); tok["cache_write"] += (t.get("cache") or {}).get("write", 0)
            cost += st["part"].get("cost", 0) or 0; times.append(st.get("timestamp"))
        launch = json.loads((run / "launch.json").read_text()) if (run / "launch.json").exists() else {}
        return {"client": "opencode", "model": launch.get("model_requested"), "cost_usd": round(cost, 4),
                "cost_basis": "opencode step cost from the pricing declared in opencode.json (pricing.json list price)",
                "input_tokens": tok["input"], "output_tokens": tok["output"], "reasoning_tokens": tok["reasoning"],
                "cache_read_input_tokens": tok["cache_read"], "cache_creation_input_tokens": tok["cache_write"], "model_calls": len(steps),
                "duration_ms": None if launch.get("cli_wall_s") is None else int(launch["cli_wall_s"] * 1000), "num_turns": len(steps)}
    for line in raw.splitlines():
        if '"result"' not in line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("type") != "result":
            continue
        if "total_cost_usd" in r:                       # Claude Code: list-price cost reported by the CLI
            u = r.get("usage") or {}
            return {"client": "claude", "cost_usd": round(float(r["total_cost_usd"]), 4), "cost_basis": "claude code list price",
                    "input_tokens": u.get("input_tokens"), "cache_creation_input_tokens": u.get("cache_creation_input_tokens"),
                    "cache_read_input_tokens": u.get("cache_read_input_tokens"), "output_tokens": u.get("output_tokens"),
                    "duration_ms": r.get("duration_ms"), "num_turns": r.get("num_turns"), "model_usage": r.get("modelUsage")}
        stats = r.get("stats") or {}                     # Gemini CLI: token counts, priced with agent/vlm/native/pricing.json
        if not stats:                                    # Qwen Code / other OpenAI-compatible CLIs: usage totals over all turns
            u = r.get("usage") or {}
            model = json.loads((run / "launch.json").read_text()).get("model_requested") if (run / "launch.json").exists() else None
            p = price.get(model or "")
            cost, basis = None, "subscription plan, no per-token price"
            if p and u:                                  # e.g. OpenRouter models: pricing.json list price on the CLI's token totals
                cached = u.get("cache_read_input_tokens") or 0
                cost = round(((u.get("input_tokens") or 0) - cached) / 1e6 * p["input_per_million"] + cached / 1e6 * p["cached_input_per_million"]
                             + (u.get("output_tokens") or 0) / 1e6 * p["output_per_million"], 4)
                basis = "pricing.json list price on the CLI usage totals"
            return {"client": "cli", "model": model, "cost_usd": cost, "cost_basis": basis,
                    "duration_ms": r.get("duration_ms"), "duration_api_ms": r.get("duration_api_ms"), "num_turns": r.get("num_turns"),
                    "usage": u or None, "model_usage": r.get("modelUsage")}
        c = 0.0
        for m, x in stats.get("models", {}).items():
            p = price.get(m)
            if not p:
                c = None; break
            c += x["input"] / 1e6 * p["input_per_million"] + x["cached"] / 1e6 * p["cached_input_per_million"] + x["output_tokens"] / 1e6 * p["output_per_million"]
        return {"client": "gemini", "cost_usd": None if c is None else round(c, 4), "cost_basis": "pricing.json list price",
                "total_tokens": stats.get("total_tokens"), "uncached_input_tokens": stats.get("input"), "cached_tokens": stats.get("cached"),
                "output_tokens": stats.get("output_tokens"), "duration_ms": stats.get("duration_ms"), "tool_calls": stats.get("tool_calls"),
                "models": stats.get("models")}
    return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=pathlib.Path, required=True); ap.add_argument("--out", type=pathlib.Path, required=True)
    ap.add_argument("--name", required=True, help="folder name for this VLM/setting, e.g. gemini-3.8-flash-medium-vqa")
    ap.add_argument("--profiles", type=pathlib.Path, default=ROOT / "reports/ue-aws-profiles-20260918.json")
    a = ap.parse_args()
    prof = json.loads(a.profiles.read_text())["tasks"] if a.profiles.exists() else {}
    price = json.loads((ROOT / "agent/vlm/native/pricing.json").read_text())["models"]
    dst = a.out / a.name
    (dst / "cases").mkdir(parents=True, exist_ok=True)
    for f in ["selection.json", "results.json", "results.md", "estimate-gemini-judge.json", "estimate-gemini-judge.md", "progress.json"]:
        if (a.batch / f).exists():
            shutil.copyfile(a.batch / f, dst / f)
    sel = json.loads((a.batch / "selection.json").read_text())
    progress = json.loads((a.batch / "progress.json").read_text())["tasks"] if (a.batch / "progress.json").exists() else {}
    launches = [json.loads((c / "run/launch.json").read_text()) for c in sorted((a.batch / "cases").iterdir()) if (c / "run/launch.json").exists()]
    effort = sorted({str(l.get("reasoning_requested")) for l in launches}) if launches else []
    models = sorted({str(l.get("model_requested")) for l in launches}) if launches else []
    rows = []
    for selected in sel["tasks"]:
        tid = selected["id"]
        case = a.batch / "cases" / tid
        run = case / "run"; ep = run / "episode"
        out = dst / "cases" / tid
        out.mkdir(parents=True, exist_ok=True)
        state = progress.get(tid, {})
        (out / "status.json").write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
        for source, names in [(case, ["judge.json", "judge-provenance.json", "judge-metrics.json", "judge-native-events.jsonl", "judge-native-stderr.log", "judge.log"]),
                              (run, ["native-events.jsonl", "native-stderr.log", "launch.json", "codex-overrides.json"])]:
            for name in names:
                if (source / name).exists():
                    shutil.copyfile(source / name, out / name)
        if not (ep / "meta.json").exists() or state.get("status") != "completed":
            rows.append({"task": tid, "status": state.get("status", "missing"), "error": state.get("error"),
                         "judge_error": state.get("judge_error"), "wall_s": state.get("elapsed_seconds")})
            continue
        meta = json.loads((ep / "meta.json").read_text())
        (out / "frames").mkdir(parents=True, exist_ok=True)
        index = {}
        if (ep / "frames/index.jsonl").exists():
            for line in (ep / "frames/index.jsonl").read_text().splitlines():
                if line.strip():
                    row = json.loads(line); index[row["ref"]] = row
        output = {"bugs": meta.get("flags", []), "summary": meta.get("done_summary", "")}
        refs = []
        for flag in output["bugs"]:
            for ref in flag.get("evidence", []):
                if ref in index and ref not in refs:
                    refs.append(ref)
        rule = "all valid evidence refs from the final active ledger, chronological"
        if not refs:
            refs = list(dict.fromkeys(r for r in ["a0", f"a{meta.get('actions_used', 0)}"] if r in index))
            rule += "; if none, initial and final observation"
        refs.sort(key=lambda r: (index[r]["action"], index[r].get("t_sim", 0), r))
        output["attached_evidence"] = [{"image": i + 1, "ref": r, "file": "frames/" + index[r]["file"],
                                        "recording_t": index[r].get("t_sim") if index[r]["kind"] != "final" or index[r]["action"] else 0.0}
                                       for i, r in enumerate(refs)]
        output["evidence_rule"] = rule
        for r in refs:
            shutil.copyfile(ep / "frames" / index[r]["file"], out / "frames" / index[r]["file"])
        (out / "judge-input.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
        export_rubric(case, out, prof.get(tid))
        for f in ["meta.json", "mcp-calls.jsonl", "tools.json", "bugs.jsonl"]:
            if (ep / f).exists():
                shutil.copyfile(ep / f, out / f)
        for f in ["launch.json", "episode-config.json", "prompt.txt", "native-stderr.log"]:
            if (run / f).exists():
                shutil.copyfile(run / f, out / f)
        cost = episode_cost(run, price)
        cost["wall_s"] = progress.get(tid, {}).get("elapsed_seconds")      # runner wall clock: launcher start to exit, incl. MCP start-up
        (out / "cost.json").write_text(json.dumps(cost, ensure_ascii=False, indent=2) + "\n")
        judge = json.loads((case / "judge.json").read_text()) if (case / "judge.json").exists() else {}
        jm = json.loads((case / "judge-metrics.json").read_text()) if (case / "judge-metrics.json").exists() else {}
        calls = [json.loads(line) for line in (ep / "mcp-calls.jsonl").read_text().splitlines() if line.strip()]
        observed = set(ref for c in calls if c.get("tool") == "observe" for ref in c.get("images", []))
        launch = json.loads((run / "launch.json").read_text())
        ec = json.loads((run / "episode-config.json").read_text())
        usage = cost.get("usage", {})
        ju = jm.get("usage", {})
        rows.append({"task": tid, "family": t["family"], "subcategory": t["task"].get("subcategory"), "status": meta.get("status"),
                     "tool_calls": meta.get("tool_calls"), "flags": len(output["bugs"]), "evidence_frames": len(refs),
                     "cost_usd": cost.get("cost_usd"), "cli_duration_s": None if cost.get("duration_ms") is None else round(cost["duration_ms"] / 1000, 1),
                     "wall_s": cost.get("wall_s"), "model": launch.get("model_requested"), "reasoning_effort": launch.get("reasoning_requested"),
                     "cli_version": launch.get("cli_version"), "observed_images": len(observed),
                     "recording_frames": ec.get("recording", {}).get("frames"), "actions_used": meta.get("actions_used"),
                     "tool_errors": sum(bool(c.get("is_error")) for c in calls), "judge_model": jm.get("model"),
                     "judge_effort": jm.get("reasoning_effort"), "judge_score": judge.get("score"), "judge_reason": judge.get("reason"),
                     "judge_wall_s": jm.get("wall_s"), "judge_images": jm.get("images"), "judge_error": state.get("judge_error"),
                     "usage_complete": cost.get("usage_complete"), "judge_usage_complete": jm.get("usage_complete"),
                     **{"agent_" + k: usage.get(k) for k in ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens")},
                     **{"judge_" + k: ju.get(k) for k in ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens")}})
    fields = list(dict.fromkeys(k for row in rows for k in row)) or ["task", "status"]
    for name in ["costs.csv", "metrics.csv"]:
        with (dst / name).open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    (dst / "metrics.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    priced = [r["cost_usd"] for r in rows if r.get("cost_usd") is not None]
    total = sum(priced) if len(priced) == len(rows) and rows else None
    cost_text = f"list-price estimate ${total:.2f}" if total is not None else "unpriced (subscription or unavailable); not $0"
    walls = [r["wall_s"] for r in rows if r.get("wall_s")]
    mean_wall = sum(walls) / len(walls) if walls else 0
    (dst / "README.md").write_text(f"""# VLA arm audit results - {a.name}

Recordings: {sel.get('recordings')} (Open-P2P 1.2B explorer, 60 s of simulated time, one frame every 0.5 s).
Auditor: {sel.get('client')} client, model {', '.join(models) or sel.get('model') or 'client default'}, thinking/effort {', '.join(effort)},
replay mode {sel.get('replay_mode')} (tools: read_example, observe with every recorded frame inline, one report call), ICL example per subcategory: {sel.get('icl')}.
Episodes: {len(rows)}; completed {sum(1 for r in rows if r['status'] == 'completed')}; cost: {cost_text};
mean wall time {mean_wall:.0f} s per episode (`wall_s` in costs.csv = launcher start to CLI exit; `cli_duration_s` = the CLI's own run time).

Per case: `judge-input.json` (final ledger + done summary + attached evidence frames, the embodied batches' judge-input rule),
`rubric.json` (the task rubric, for the judge only), `frames/` (the attached evidence frames), `meta.json`, `mcp-calls.jsonl`,
`launch.json`, `episode-config.json`, `prompt.txt`, `cost.json`, and available judge results/metrics/raw events.
`metrics.csv` / `metrics.json` include agent and judge tokens, times, scores, and protocol counts; `costs.csv` mirrors the same table.
Cached input tokens are a subset of input tokens; reasoning tokens are a subset of output tokens. Missing values remain blank/null.
Failed tasks remain visible and are not assigned score zero. `estimate-gemini-judge.md` (if present) is an
automatic estimate with the Gemini strict text judge, not the GPT-6 judge.

Grade a case with the GPT-6 binary judge (from the game-auditing repo root, Codex logged in):
```
python3 -m judge.judge --rubrics cases/A05/rubric.json --model-output cases/A05/judge-input.json \\
    --images cases/A05/frames/<the files listed in attached_evidence, in order> --output cases/A05/judge.json
```
""")
    print(f"{dst}: {len(rows)} cases, {cost_text}")


if __name__ == "__main__":
    main()
