#!/usr/bin/env python3
"""Render a local pilot report from actual run artifacts and separate rubric grades."""
import argparse
import csv
import html
import json
from pathlib import Path
import re
import time


def read(path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def estimate_cost(stats, pricing=None):
    if pricing is None:
        pricing = read(Path(__file__).with_name("pricing.json"), {})
    breakdown = []
    for model, usage in stats.get("models", {}).items():
        rate = pricing.get("models", {}).get(model)
        required = ("total_tokens", "input_tokens", "output_tokens", "cached")
        if not rate or any(k not in usage for k in required):
            return {"estimated_usd": None, "error": "Missing model price or usage", "model": model}
        prompt, cached = usage["input_tokens"], usage["cached"]
        generated = usage["total_tokens"] - prompt
        if not 0 <= cached <= prompt or generated < usage["output_tokens"]:
            return {"estimated_usd": None, "error": "Inconsistent token counts", "model": model}
        cost = ((prompt-cached)*rate["input_per_million"] + cached*rate["cached_input_per_million"]
                + generated*rate["output_per_million"]) / 1e6
        breakdown.append({"model": model, "input_tokens": prompt, "cached_input_tokens": cached,
                          "uncached_input_tokens": prompt-cached, "output_tokens": usage["output_tokens"],
                          "reasoning_or_other_tokens_inferred": generated-usage["output_tokens"],
                          "billable_output_tokens": generated, "estimated_usd": cost, "rates": rate})
    return {"estimated_usd": sum(x["estimated_usd"] for x in breakdown) if breakdown else None,
            "breakdown": breakdown, "price_source": pricing.get("source"),
            "price_verified_at": pricing.get("verified_at"), "pricing_mode": pricing.get("mode"),
            "scope": "API token charges including native auxiliary models; not an invoice. No explicit cache storage or built-in paid tools are requested."}


def build(base):
    import fcntl
    with (base / "report.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _build(base)


def _build(base):
    selection = read(base / "selection.json", {})
    price_path = base / "pricing.json"
    if not price_path.exists():
        price_path.write_text(Path(__file__).with_name("pricing.json").read_text())
    pricing = read(price_path, {})
    progress = read(base / "progress.json", {}).get("tasks", {})
    grades = read(base / "grades.json", {})
    rows = []
    for task in selection["tasks"]:
        tid = task["id"]
        run = base / tid / "run"
        state = progress.get(tid, {})
        meta = read(run / "episode/meta.json", {})
        launch = read(run / "launch.json", {})
        stats = {}
        models = set()
        events = run / "native-events.jsonl"
        if events.exists():
            for line in events.read_text().splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "init":
                    models.add(event.get("model"))
                if event.get("type") == "result":
                    stats = event.get("stats", {})
                    models.update(stats.get("models", {}))
        rows.append({**task, "status": state.get("status", "queued"),
                     "actions_used": meta.get("actions_used", 0), "tool_calls": meta.get("tool_calls", 0),
                     "elapsed_seconds": state.get("elapsed_seconds"), "native_stats": stats,
                     "timing": {"environment_startup_seconds": state.get("environment_ready_at", 0)-state.get("started_at", 0) if state.get("environment_ready_at") and task.get("environment") != "threejs" else None,
                                "browser_page_load_seconds": meta.get("backend", {}).get("load_time_s"),
                                "model_process_seconds": state["model_finished_at"]-state["model_started_at"] if state.get("model_finished_at") and state.get("model_started_at") else None,
                                "native_cli_seconds": stats["duration_ms"]/1000 if "duration_ms" in stats else None,
                                "total_task_seconds": state.get("elapsed_seconds")},
                     "cost": estimate_cost(stats, pricing),
                     "models_observed": sorted(m for m in models if m),
                     "thinking_level": launch.get("reasoning_requested"),
                     "flags": meta.get("flags", []), "done_summary": meta.get("done_summary"), "grade": grades.get(tid),
                     "icl": meta.get("icl", {}), "error": state.get("error")})
    completed = sum(r["status"] == "completed" for r in rows)
    graded = [r for r in rows if r["grade"] and isinstance(r["grade"].get("target_found"), bool)]
    found = sum(r["grade"].get("target_found") is True for r in graded)
    starts = [v["started_at"] for v in progress.values() if "started_at" in v]
    ends = [v["cleaned_up_at"] for v in progress.values() if "cleaned_up_at" in v]
    report = {"parallelism": selection["parallelism"], "gpus": sorted(set(selection["gpus"])),
              "total_tokens": sum(r["native_stats"].get("total_tokens", 0) for r in rows),
              "wall_seconds": max(ends) - min(starts) if completed == len(rows) and starts and ends else None,
              "model": selection["model"], "thinking_level": selection["thinking_level"],
              "updated_at": time.time(), "completed": completed, "total": len(rows),
              "graded": len(graded), "target_found": found, "tasks": rows}
    report["recall_graded"] = found / len(graded) if graded else None
    report["pending_grading"] = sum(r["status"] == "completed" and not (r["grade"] and isinstance(r["grade"].get("target_found"), bool)) for r in rows)
    report["runtime_failures"] = sum(r["status"] in {"failed", "interrupted"} for r in rows)
    report["grading_by_protocol"] = {}
    for group in sorted({r.get("protocol_group", "category-icl") for r in rows}):
        cohort = [r for r in graded if r.get("protocol_group", "category-icl") == group]
        hits = sum(r["grade"]["target_found"] for r in cohort)
        report["grading_by_protocol"][group] = {"graded": len(cohort), "target_found": hits,
                                                "recall": hits/len(cohort) if cohort else None}
    report["tasks_with_priced_usage"] = sum(r["cost"]["estimated_usd"] is not None for r in rows)
    report["estimated_api_cost_usd"] = sum(r["cost"]["estimated_usd"] or 0 for r in rows) if report["tasks_with_priced_usage"] else None
    report["cost_coverage"] = "Only tasks with final native usage stats are priced; interrupted/missing usage is unknown, not free."
    (base / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    with (base / "results.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["task", "environment", "subcategory", "protocol_group", "status", "actions",
                         "total_seconds", "startup_seconds", "native_cli_seconds", "total_tokens", "estimated_api_usd",
                         "target_found", "evaluation_status", "grading_reason"])
        for row in rows:
            writer.writerow([row["id"], row.get("environment", "unreal-http"), row["subcategory"],
                             row.get("protocol_group", "category-icl"), row["status"], row["actions_used"],
                             row["elapsed_seconds"], row["timing"]["environment_startup_seconds"],
                             row["timing"]["native_cli_seconds"], row["native_stats"].get("total_tokens"),
                             row["cost"]["estimated_usd"], (row["grade"] or {}).get("target_found"),
                             (row["grade"] or {}).get("evaluation_status"), (row["grade"] or {}).get("reason")])
    esc = lambda value: html.escape(str(value))
    table = []
    details = []
    for row in rows:
        tid = row["id"]
        grade = row["grade"]
        verdict = ("Found" if grade["target_found"] else "Missed") if grade and isinstance(grade.get("target_found"), bool) else ("Run failed" if row["status"] in {"failed", "interrupted"} else "Needs review" if grade else "Pending")
        elapsed = f"{row['elapsed_seconds'] / 60:.1f} min" if row["elapsed_seconds"] is not None else "—"
        total_tokens = row["native_stats"].get("total_tokens")
        tokens = f"{total_tokens:,}" if isinstance(total_tokens, int) else "—"
        cost = row["cost"]["estimated_usd"]
        cost_label = f"${cost:.4f}" if cost is not None else "—"
        table.append(f'<tr><td><a href="#{esc(tid)}">{esc(tid)}</a></td><td>{esc(row["family"])}</td>'
                     f'<td>{esc(row["subcategory"])}</td><td>{esc(row["status"])}</td>'
                     f'<td>{row["actions_used"]}/{selection["max_actions"]}</td><td>{verdict}</td><td>{elapsed}</td><td>{tokens}</td><td>{cost_label}</td></tr>')
        parts = [f'<section id="{esc(tid)}"><h2>{esc(tid)} · {esc(row["subcategory"])}</h2>']
        if grade:
            if grade.get("target_criterion"):
                parts.append(f'<p><strong>Target rubric:</strong> {esc(grade["target_criterion"])}</p>')
            parts.append(f'<p><strong>{verdict}</strong> — {esc(grade["reason"])}</p>')
        if row["done_summary"]:
            parts.append(f'<details><summary>Agent final summary</summary><p>{esc(row["done_summary"])}</p></details>')
        if row["error"]:
            parts.append(f'<p>{esc(row["error"])}</p>')
        for flag in row["flags"]:
            parts.append(f'<h3>{esc(flag.get("id"))} · {esc(flag.get("status"))}</h3><p>{esc(flag.get("note"))}</p>')
            pictures = []
            selected_refs = grade.get("evidence") if grade and grade["target_found"] and len(row["flags"]) == 1 else flag.get("evidence", [])
            for ref in (selected_refs or [])[:3]:
                match = re.fullmatch(r"a(\d+)(?:\.f(\d+))?", ref)
                if not match:
                    continue
                filename = f"a{int(match[1]):03d}" + (f"_f{int(match[2]):02d}" if match[2] else "") + ".jpg"
                rel = Path(tid) / "run/episode/frames" / filename
                if (base / rel).exists():
                    pictures.append(f'<figure><img loading="lazy" src="{esc(rel)}"><figcaption>{esc(ref)}</figcaption></figure>')
            parts.append('<div class="images">' + ''.join(pictures) + '</div>')
        parts.append('</section>')
        details.append(''.join(parts))
    page = '''<!doctype html><html><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Gemini Unreal pilot</title><style>body{font:16px system-ui;background:#f5f6f8;color:#182536;max-width:1280px;margin:40px auto;padding:0 24px}h1{font-size:32px}table{width:100%;border-collapse:collapse;background:white}th,td{text-align:left;padding:12px;border-bottom:1px solid #e3e6ea}section{background:white;margin:24px 0;padding:24px;border-radius:10px}.images{display:flex;gap:12px;flex-wrap:wrap}figure{margin:0;flex:1;min-width:240px;max-width:480px}img{width:100%}figcaption{color:#637083}p{line-height:1.6}a{color:#2467ba}</style><body>'''
    if completed < len(rows) or len(graded) < len(rows):
        page += '<meta http-equiv="refresh" content="15"><p>Running · refreshes every 15 seconds.</p>'
    page += f'<h1>{esc(selection["model"])} · {esc(selection["thinking_level"])} · {selection["max_actions"]} actions</h1><p>{completed}/{len(rows)} completed · {len(graded)} graded · {found} targets found.</p>'
    recall = f'{100*report["recall_graded"]:.1f}%' if graded else '—'
    page += f'<p><strong>Recall among graded tasks: {recall}</strong> · {report["pending_grading"]} completed awaiting grading · {report["runtime_failures"]} runtime failures (reported separately).</p>'
    if len(report["grading_by_protocol"]) > 1:
        for group, metrics in report["grading_by_protocol"].items():
            score = f'{100*metrics["recall"]:.1f}%' if metrics['recall'] is not None else '—'
            page += f'<p>{esc(group)}: {metrics["target_found"]}/{metrics["graded"]} graded targets found · {score}</p>'
    browser_count = sum(r.get("environment") == "threejs" for r in rows)
    exceptions = sum(r.get("protocol_group") == "zero-shot-exception" for r in rows)
    page += f'<p>{len(rows)-browser_count} accepted Unreal and {browser_count} accepted Three.js tasks; {selection["parallelism"]} parallel episodes. Unreal uses AWS GPUs {sorted(set(selection["gpus"]))}; Three.js uses local Chromium. Category-specific ICL is supplied except for {exceptions} explicitly labeled zero-shot exceptions. Found/Missed requires separate rubric grading.</p>'
    auxiliary = sorted({model for row in rows for model in row["models_observed"] if model != selection["model"]})
    if auxiliary:
        page += f'<p>Native CLI usage also includes auxiliary-model calls: {esc(", ".join(auxiliary))}. Token totals include these calls. This pilot evaluates the model together with its native harness.</p>'
    page += '<p>Time is task wall time including environment startup; JSON also lists native CLI time. Cost is a paid-tier API estimate from actual per-model token usage, including cached input and generated/thinking tokens. <a href="https://ai.google.dev/gemini-api/docs/pricing">Google pricing, checked 2026-09-17</a>. Infrastructure, taxes and account credits are excluded.</p>'
    page += '<p><a href="results.json">Download JSON</a> · <a href="results.csv">Download CSV</a></p>'
    page += '<table><thead><tr><th>Task</th><th>Environment</th><th>Category</th><th>Run</th><th>Actions</th><th>Rubric</th><th>Wall time</th><th>Total tokens</th><th>Est. API cost</th></tr></thead><tbody>'
    page += ''.join(table) + '</tbody></table>' + ''.join(details) + '</body></html>'
    (base / "index.html").write_text(page)
    print(json.dumps({k: report[k] for k in ["completed", "total", "graded", "target_found"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path)
    parser.add_argument("--serve", type=int, help="Serve a fresh report on this loopback port")
    args = parser.parse_args()
    base = args.batch.resolve()
    build(base)
    if args.serve:
        from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
        from urllib.parse import urlparse
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *a, **kw):
                super().__init__(*a, directory=str(base), **kw)
            def do_GET(self):
                if urlparse(self.path).path in {"/", "/index.html", "/results.json", "/results.csv"}:
                    build(base)
                super().do_GET()
        ThreadingHTTPServer(("127.0.0.1", args.serve), Handler).serve_forever()
