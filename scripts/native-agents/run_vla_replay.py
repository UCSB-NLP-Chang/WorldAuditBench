#!/usr/bin/env python3
"""VLA arm, audit stage: a native CLI agent (Gemini CLI by default) reviews each VLA recording through the world_audit
MCP server's vla-replay environment, then the GPT-6 binary judge grades the final ledger with the task rubric and the
cited evidence frames - the same agent client, prompt, ICL example, observation mode, action budget, tool budget, judge
model and judge input rule as the embodied (pure VLM) batches (see ~/gemini-medieval-20260919 for the reference batch).

usage:
  scripts/native-agents/run_vla_replay.py --recordings runs/vla-ue-v1 --batch out/native-agents/batches/<name> \
      --tasks A05,I13,MV07,R13,H02 --key-file <gemini api key file> --workers 4 [--stage agent|judge|all] [--resume]
Layout: <batch>/selection.json, progress.json, cases/<ID>/run/... (launch.py run directory), cases/<ID>/{judge-input,rubric,
judge-provenance,judge}.json, results.json, results.md.  Hidden rubrics are read only by the judge stage.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import shlex
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from auditor.task_dataset import load_task
ALL_INSTRUCTION = (
    "Inspect the assigned 3D environment for bugs by reviewing the explorer's recording. Go through the recorded frames and inspect "
    "the ones that matter at full resolution to gather visual evidence. Report each distinct bug with a clear description, category, "
    "and evidence frame refs. Do not assume every unusual object is a bug. Report bugs through flag_bug/update_bug and finish with done. "
    "If you find no bug, say so explicitly in done.")
ALL_INSTRUCTION = ALL_INSTRUCTION.replace("Go through the recorded frames and inspect the ones that matter at full resolution to gather visual evidence.",
                                          "Go through the recorded frames to gather visual evidence; inspect only to zoom in or to view a frame that is not shown.")
VQA_INSTRUCTION = (
    "Inspect the assigned 3D environment for bugs by reviewing the explorer's recording. Report each distinct bug with a clear "
    "description, category, and evidence frame refs. Do not assume every unusual object is a bug. Answer with one report call; "
    "if you find no bug, report an empty list and say so in the summary.")
DEFAULT_INSTRUCTION = (
    "Inspect the assigned 3D environment for bugs by reviewing the explorer's recording. Play and inspect the recording "
    "to gather visual evidence. Report each distinct bug with a clear description, category, and evidence frame refs. "
    "Do not assume every unusual object is a bug. Use the full 40-play budget to review and verify, even after finding an "
    "initial bug. Finish earlier only if the environment fails. Report bugs through flag_bug/update_bug and finish with done. "
    "If you find no bug, say so explicitly in done.")


def cli():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--recordings", type=Path, required=True, help="runs/<tag> of harness/vla_ue.py or vla_explore.py")
    p.add_argument("--batch", type=Path, required=True, help="batch directory (new, or existing with --resume / --stage judge)")
    p.add_argument("--tasks", default="all", help="comma-separated task ids, @file, or all (every episode directory with meta.json)")
    p.add_argument("--profiles", type=Path, default=ROOT / "reports/ue-aws-profiles-20260918.json",
                   help="mirrored AWS catalog: rubrics (judge only), subcategory fallback, map for the scene fallback")
    p.add_argument("--scene-catalog", type=Path, default=SCRIPTS / "task-scenes.json")
    p.add_argument("--task-catalog", type=Path, default=SCRIPTS / "task-subcategories.json")
    p.add_argument("--dataset", type=Path, help="Unified HF task table; downloads the pinned release by default")
    p.add_argument("--legacy-task-files", action="store_true", help="Use archival task catalogs and profile rubrics")
    p.add_argument("--client", choices=["gemini", "codex", "claude", "qwen", "muse", "opencode"], default="gemini")
    p.add_argument("--qwen-effort", default="medium", choices=["low", "medium", "high"])
    p.add_argument("--qwen-api-key-file", type=Path, default=Path.home() / ".config/keys/qwen-api")
    p.add_argument("--qwen-context-window", type=int, default=None, help="context window to declare to Qwen Code for models it does not know")
    p.add_argument("--qwen-base-url", default=None, help="OpenAI-compatible endpoint for the qwen client (default: Qwen Token Plan); e.g. https://openrouter.ai/api/v1 to run other models through Qwen Code")
    p.add_argument("--muse-effort", default="medium")
    p.add_argument("--opencode-effort", default="medium", choices=["minimal", "low", "medium", "high", "xhigh", "max"])
    p.add_argument("--opencode-api-key-file", type=Path, default=Path.home() / ".config/keys/openrouter")
    p.add_argument("--opencode-home", type=Path, default=None, help="shared OpenCode config dir (see launch.py)")
    p.add_argument("--muse-base-url", default=None, help="route Muse Code to another endpoint (e.g. https://openrouter.ai/api/v1)")
    p.add_argument("--muse-api-key-file", type=Path, default=None, help="API key file for --muse-base-url")
    p.add_argument("--muse-supports-video", action="store_true", help="see launch.py")
    p.add_argument("--claude-effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    p.add_argument("--model", default=None, help="exact model id; default = the client's default")
    p.add_argument("--gemini-thinking", default="medium", choices=["low", "medium", "high"])
    p.add_argument("--reasoning-effort", default="low", choices=["low", "medium", "high", "xhigh"], help="codex only")
    p.add_argument("--key-file", type=Path, help="Gemini API key file (read into the child environment only)")
    p.add_argument("--cli", default=None, help="native CLI executable")
    p.add_argument("--node-bin", type=Path, default=None, help="directory with node, prepended to PATH for the CLI")
    p.add_argument("--max-actions", type=int, default=40)
    p.add_argument("--max-tool-calls", type=int, default=400)
    p.add_argument("--observation", choices=["on-demand", "film", "final"], default="on-demand")
    p.add_argument("--preview-every", type=float, default=5.0)
    p.add_argument("--replay-mode", choices=["play", "all", "vqa"], default="play",
                   help="all: whole recording delivered by observe, no play actions; vqa: all frames, tools = read_example, observe, report only")
    p.add_argument("--inline-low-res", action="store_true", help="all: inline frames at 480x288 instead of the final-view resolution")
    p.add_argument("--inspect-budget", type=int, default=None, help="maximum inspect calls per episode; 0 removes the inspect tool")
    p.add_argument("--instruction", default=None, help="default: the mode's instruction (40-play budget text for play, review text for all)")
    p.add_argument("--no-icl", action="store_true")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--task-timeout", type=float, default=3600)
    p.add_argument("--stage", choices=["agent", "judge", "all"], default="all")
    p.add_argument("--judge-model", default="gpt-6-astra")
    p.add_argument("--judge-effort", default="medium", choices=["low", "medium", "high", "xhigh"])
    p.add_argument("--judge-workers", type=int, default=2)
    p.add_argument("--judge-python", type=Path, default=ROOT / ".venv/bin/python", help="python with Pillow for eval.judge")
    p.add_argument("--resume", action="store_true", help="skip tasks that already have a case directory (never replay a started episode)")
    p.add_argument("--dry-run", action="store_true", help="prepare the launcher configuration of every task, no model call")
    return p


def load_tasks(args):
    profiles_all = json.loads(args.profiles.read_text())["tasks"] if args.profiles.exists() else {}
    if args.tasks == "all" and any("recording_dir" in v for v in profiles_all.values()):
        ids = sorted(tid for tid, v in profiles_all.items() if (args.recordings / v.get("recording_dir", tid) / "meta.json").exists())
    elif args.tasks == "all":
        ids = sorted(p.name for p in args.recordings.iterdir() if p.is_dir() and (p / "meta.json").exists())
    elif args.tasks.startswith("@"):
        ids = [l.strip() for l in Path(args.tasks[1:]).read_text().splitlines() if l.strip() and not l.startswith("#")]
    else:
        ids = [t.strip() for t in args.tasks.split(",") if t.strip()]
    profiles = json.loads(args.profiles.read_text())["tasks"] if args.profiles.exists() else {}
    if not args.legacy_task_files:
        tasks = []
        for tid in ids:
            prof = profiles.setdefault(tid, {})
            native = prof.get('task_id', tid)
            row = load_task(native, args.dataset)
            rec = args.recordings / prof.get('recording_dir', tid)
            if not (rec / 'meta.json').exists():
                raise SystemExit(f'{tid}: no recording under {rec}')
            prof.update(case_type='bug', family=row['environment'])
            prof['task'] = {**prof.get('task', {}), 'rubrics_i18n': {'en': {
                'expected': row['rubric']['expected_behavior'],
                'steps': row['rubric']['reproduction_steps'],
                'criteria': row['rubric']['success_criteria']}}}
            tasks.append({'id': tid, 'task_id': native, 'recording': str(rec.resolve()),
                          'family': row['environment'], 'subcategory': row['subcategory'],
                          'label_source': 'dataset', 'scene_source': 'dataset',
                          'scene': row['input']['scene_description'], 'case_type': 'bug',
                          'has_rubric': bool(row['rubric']['success_criteria'])})
        return tasks, profiles
    scenes = json.loads(args.scene_catalog.read_text())["scenes"]
    scene_of = {t: s["description"]["en"].strip() for s in scenes for t in s["task_ids"]}
    labels = json.loads(args.task_catalog.read_text())["task_subcategories"]
    map_scene = {}
    for tid, e in profiles.items():
        if scene_of.get(tid):
            map_scene.setdefault(e["policy"].get("map"), scene_of[tid])
    tasks = []
    for tid in ids:
        prof = profiles.get(tid, {})
        native = prof.get("task_id", tid)                       # three.js recordings: case name -> catalog task id (JS_AF01)
        rec = args.recordings / prof.get("recording_dir", tid)
        if not (rec / "meta.json").exists():
            raise SystemExit(f"{tid}: no recording under {rec}")
        raw = (prof.get("task") or {}).get("subcategory") or ""
        code = labels.get(native) or (raw if len(raw) == 2 else None)
        scene = scene_of.get(native) or ((prof.get("task") or {}).get("scene_i18n") or {}).get("en") or map_scene.get(prof.get("policy", {}).get("map"))
        if not code and not args.no_icl:
            raise SystemExit(f"{tid}: no subcategory label (catalog or profile); cannot select the ICL example")
        if not scene:
            raise SystemExit(f"{tid}: no public scene description")
        rubric = ((prof.get("task") or {}).get("rubrics_i18n") or {}).get("en")
        tasks.append({"id": tid, "task_id": native, "recording": str(rec.resolve()), "family": prof.get("family"), "subcategory": code,
                      "label_source": "catalog" if labels.get(native) else "profile", "scene_source": "catalog" if scene_of.get(native) else "fallback",
                      "scene": scene, "case_type": prof.get("case_type", "bug"), "has_rubric": bool(rubric)})
    return tasks, profiles


def write_json(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temp.replace(path)


class Batch:
    def __init__(self, args):
        self.args = args
        self.base = args.batch
        self.lock = threading.Lock()
        self.progress_path = self.base / "progress.json"
        self.state = json.loads(self.progress_path.read_text())["tasks"] if self.progress_path.exists() else {}

    def update(self, tid, **values):
        with self.lock:
            self.state.setdefault(tid, {}).update(values)
            write_json(self.progress_path, {"updated_at": time.time(), "tasks": self.state})
            print(tid, values, flush=True)

    # ------------------------------------------------------------ agent stage
    def run_agent(self, task):
        a = self.args
        tid = task["id"]
        job = self.base / "cases" / tid
        job.mkdir(parents=True)
        scene_file = job / "scene.txt"
        scene_file.write_text(task["scene"] + "\n")
        cmd = [sys.executable, str(SCRIPTS / "launch.py"), a.client, "--environment", "vla-replay", "--replay-dir", task["recording"],
               "--task", task.get("task_id", tid), "--scene-description-file", str(scene_file), "--task-catalog", str(a.task_catalog),
               "--max-actions", str(0 if a.replay_mode in ("all", "vqa") else a.max_actions), "--max-tool-calls", str(a.max_tool_calls),
               "--observation", a.observation, "--preview-every", str(a.preview_every), "--replay-mode", a.replay_mode,
               "--instruction", a.instruction, "--run-dir", str(job / "run")]
        if a.dataset:
            cmd += ['--dataset', str(a.dataset.resolve())]
        if a.legacy_task_files:
            cmd += ['--legacy-task-files']
        if a.replay_mode == "play":
            cmd += ["--require-full-budget"]
        if a.inline_low_res:
            cmd += ["--inline-low-res"]
        if a.inspect_budget is not None:
            cmd += ["--inspect-budget", str(a.inspect_budget)]
        if task["label_source"] == "profile":
            cmd += ["--subcategory", task["subcategory"]]
        if a.no_icl:
            cmd += ["--no-icl"]
        if a.model:
            cmd += ["--model", a.model]
        if a.cli:
            cmd += ["--cli", str(Path(a.cli).resolve())]      # the CLI runs from the episode workspace, so relative paths break
        if a.client == "gemini":
            cmd += ["--gemini-thinking", a.gemini_thinking]
            if a.key_file:
                cmd += ["--gemini-auth", "gemini-api-key", "--gemini-api-key-file", str(a.key_file)]
        elif a.client == "claude":
            cmd += ["--claude-effort", a.claude_effort]
        elif a.client == "qwen":
            cmd += ["--qwen-effort", a.qwen_effort, "--qwen-api-key-file", str(a.qwen_api_key_file)]
            if a.qwen_base_url:
                cmd += ["--qwen-base-url", a.qwen_base_url]
            if a.qwen_context_window:
                cmd += ["--qwen-context-window", str(a.qwen_context_window)]
        elif a.client == "opencode":
            cmd += ["--opencode-effort", a.opencode_effort, "--opencode-api-key-file", str(a.opencode_api_key_file)]
            if a.opencode_home:
                cmd += ["--opencode-home", str(a.opencode_home)]
        elif a.client == "muse":
            cmd += ["--muse-effort", a.muse_effort]
            if a.muse_base_url:
                cmd += ["--muse-base-url", a.muse_base_url, "--muse-api-key-file", str(a.muse_api_key_file)]
            if a.muse_supports_video:
                cmd += ["--muse-supports-video"]
        else:
            cmd += ["--reasoning-effort", a.reasoning_effort]
        if a.dry_run:
            cmd += ["--dry-run"]
        env = os.environ.copy()
        if a.node_bin:
            env["PATH"] = str(Path(a.node_bin).resolve()) + os.pathsep + env["PATH"]
        started = time.time()
        self.update(tid, status="running", started_at=started, family=task["family"], subcategory=task["subcategory"])
        with (job / "launcher.log").open("w") as log:
            try:
                result = subprocess.run(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=a.task_timeout)
                code = result.returncode
            except subprocess.TimeoutExpired:
                code = -1
                self.update(tid, error="agent exceeded the task time limit")
        manifest_path = job / "run/launch.json"
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        meta_path = job / "run/episode/meta.json"
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        status = "prepared" if a.dry_run else manifest.get("status", "failed")
        if code and status == "completed":
            status = "failed"
        backend = meta.get("backend", {})
        self.update(tid, status=status, exit_code=code, actions_used=meta.get("actions_used", 0), tool_calls=meta.get("tool_calls", 0),
                    flags_count=len(meta.get("flags", [])), plays=backend.get("plays"), frames_coverage=backend.get("frames_coverage"),
                    elapsed_seconds=round(time.time() - started, 1), error=manifest.get("error") or self.state.get(tid, {}).get("error"))

    # ------------------------------------------------------------ judge stage
    def grade(self, task, profiles):
        a = self.args
        tid = task["id"]
        job = self.base / "cases" / tid
        ep = job / "run/episode"
        meta = json.loads((ep / "meta.json").read_text())
        if meta.get("status") != "completed":
            raise RuntimeError("episode not completed; not graded")
        prof = profiles[tid]["task"]
        # Judge input: the final active ledger and done summary only - no reasoning, ICL answers or hidden catalog text.
        output = {"bugs": meta.get("flags", []), "summary": meta.get("done_summary", "")}
        index = {}
        for line in (ep / "frames/index.jsonl").read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                index[row["ref"]] = row
        refs = []
        for flag in output["bugs"]:
            for ref in flag.get("evidence", []):
                if ref in index and ref not in refs:
                    refs.append(ref)
        rule = "all valid evidence refs from the final active ledger, chronological"
        if not refs:
            refs = [r for r in ["a0", f"a{meta['actions_used']}"] if r in index]
            refs = list(dict.fromkeys(refs))
            rule += "; if none, initial and final observation"
        refs.sort(key=lambda r: (index[r]["action"], index[r].get("t_sim", 0), r))
        output["attached_evidence"] = [{"image": i + 1, "ref": r, "file": index[r]["file"]} for i, r in enumerate(refs)]
        write_json(job / "judge-input.json", output)
        rubric = {"case_type": profiles[tid]["case_type"], "rubrics": prof["rubrics_i18n"]["en"]}
        write_json(job / "rubric.json", rubric)
        source_args = ['--rubrics', str(job / 'rubric.json')] if a.legacy_task_files else ['--task', task.get('task_id', tid)]
        if a.dataset and not a.legacy_task_files:
            source_args += ['--dataset', str(a.dataset.resolve())]
        cmd = [str(a.judge_python), "-m", "eval.judge", *source_args, "--model-output", str(job / "judge-input.json"),
               "--model", a.judge_model, "--reasoning-effort", a.judge_effort, "--timeout", "600", "--output", str(job / "judge.json")]
        if refs:
            cmd += ["--images", *[str(ep / "frames" / index[r]["file"]) for r in refs]]
        revision = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
        write_json(job / "judge-provenance.json", {"revision": revision, "model": a.judge_model, "reasoning_effort": a.judge_effort,
                                                   "images": refs, "selection_rule": rule, "command": cmd})
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=660)
        (job / "judge.log").write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(result.stderr[-1500:])
        return json.loads((job / "judge.json").read_text())

    def run_judge(self, task, profiles):
        tid = task["id"]
        if (self.base / "cases" / tid / "judge.json").exists():
            self.update(tid, judge=json.loads((self.base / "cases" / tid / "judge.json").read_text()))
            return
        try:
            self.update(tid, judge=self.grade(task, profiles), judge_error=None)
        except Exception as e:
            self.update(tid, judge_error=str(e)[-500:])

    # --------------------------------------------------------------- summary
    def summary(self, tasks):
        a = self.args
        rows = []
        for t in tasks:
            row = {"id": t["id"], "family": t["family"], "subcategory": t["subcategory"], "case_type": t["case_type"], **self.state.get(t["id"], {})}
            rows.append(row)
        graded = [r for r in rows if isinstance(r.get("judge"), dict)]
        successes = sum(r["judge"]["score"] for r in graded)
        groups = {"bug": {"total": len(rows), "completed": sum(1 for r in rows if r.get("status") == "completed"), "graded": len(graded),
                          "successes": successes, "success_rate": successes / len(graded) if graded else None,
                          "pending_or_failed": len(rows) - len(graded)}}
        by_family = {}
        for r in graded:
            g = by_family.setdefault(r["family"] or "?", {"graded": 0, "successes": 0})
            g["graded"] += 1; g["successes"] += r["judge"]["score"]
        value = {"updated_at": time.time(), "setting": "vla-replay", "recordings": str(a.recordings), "agent_client": a.client,
                 "agent": a.model or {"gemini": "gemini-3.8-flash", "codex": "gpt-6-astra", "claude": "claude-opus-5", "qwen": "qwen3.8-flash", "muse": "muse-spark-1.3", "opencode": "openrouter/meta/muse-spark-1.3-contributor"}[a.client],
                 "thinking": {"gemini": a.gemini_thinking, "claude": a.claude_effort, "qwen": a.qwen_effort, "muse": a.muse_effort, "opencode": a.opencode_effort}.get(a.client, a.reasoning_effort), "max_actions": a.max_actions,
                 "observation": a.observation, "preview_every": a.preview_every, "replay_mode": a.replay_mode, "judge": a.judge_model, "judge_reasoning": a.judge_effort,
                 "groups": groups, "by_family": by_family, "tasks": rows}
        write_json(self.base / "results.json", value)
        rate = f"{groups['bug']['success_rate']:.1%}" if groups["bug"]["success_rate"] is not None else "pending"
        lines = [f"# VLA replay audit - {self.base.name}", "",
                 f"Agent: {value['agent']} / {value['thinking']} ({a.client} CLI, vla-replay mode {a.replay_mode}, "
                 f"{'all frames, single report' if a.replay_mode == 'vqa' else 'all frames at once' if a.replay_mode == 'all' else str(a.max_actions) + ' plays'}, {a.observation}); "
                 f"Judge: {a.judge_model} / {a.judge_effort}.", "",
                 f"- Bug cases: graded {groups['bug']['graded']}/{groups['bug']['total']}, found {successes}, success rate {rate}.",
                 f"- Completed episodes: {groups['bug']['completed']}/{groups['bug']['total']}.", ""]
        if by_family:
            lines += ["| family | graded | found |", "|---|---:|---:|"]
            lines += [f"| {f} | {g['graded']} | {g['successes']} |" for f, g in sorted(by_family.items())]
            lines.append("")
        lines += ["Incomplete batches are not final rates; run or judge failures are listed separately.", "",
                  "| Case | sub | status | plays | coverage | flags | score | reason |", "|---|---|---|---:|---:|---:|---:|---|"]
        for r in rows:
            j = r.get("judge") or {}
            reason = (j.get("reason") or r.get("judge_error") or r.get("error") or "").replace("|", "/").replace("\n", " ")
            cov = f"{r['frames_coverage']:.0%}" if isinstance(r.get("frames_coverage"), (int, float)) else ""
            lines.append(f"| {r['id']} | {r['subcategory']} | {r.get('status', '')} | {r.get('plays', '')} | {cov} | {r.get('flags_count', '')} | {j.get('score', '')} | {reason} |")
        (self.base / "results.md").write_text("\n".join(lines) + "\n")
        print(json.dumps(groups), flush=True)


def main():
    args = cli().parse_args()
    if args.instruction is None:
        args.instruction = VQA_INSTRUCTION if args.replay_mode == "vqa" else ALL_INSTRUCTION if args.replay_mode == "all" else DEFAULT_INSTRUCTION
        if args.inspect_budget == 0:
            args.instruction = args.instruction.replace("; inspect only to zoom in or to view a frame that is not shown", "")
    tasks, profiles = load_tasks(args)
    base = args.batch
    if base.exists() and not (args.resume or args.stage == "judge"):
        raise SystemExit("Batch directory exists; pass --resume to add the tasks that have no attempt yet, or --stage judge")
    base.mkdir(parents=True, exist_ok=True)
    (base / "cases").mkdir(exist_ok=True)
    batch = Batch(args)
    if not (base / "selection.json").exists():
        write_json(base / "selection.json", {"created_at": datetime.now(timezone.utc).isoformat(), "recordings": str(args.recordings),
                                            "client": args.client, "model": args.model, "gemini_thinking": args.gemini_thinking, "claude_effort": args.claude_effort,
                                            "max_actions": args.max_actions, "max_tool_calls": args.max_tool_calls, "observation": args.observation,
                                            "preview_every": args.preview_every, "replay_mode": args.replay_mode, "inspect_budget": args.inspect_budget,
                                            "inline_low_res": args.inline_low_res, "instruction": args.instruction, "icl": not args.no_icl,
                                            "judge_model": args.judge_model, "judge_reasoning_effort": args.judge_effort,
                                            "tasks": [{k: v for k, v in t.items() if k != "scene"} for t in tasks]})
    if args.stage in ("agent", "all"):
        pending = queue.Queue()
        for t in tasks:
            if (base / "cases" / t["id"]).exists():
                if batch.state.get(t["id"], {}).get("status") not in {"completed", "failed", "prepared"}:
                    batch.update(t["id"], status="interrupted", error="existing attempt preserved; not replayed")
                continue
            pending.put(t)

        def worker():
            while True:
                try:
                    t = pending.get_nowait()
                except queue.Empty:
                    return
                try:
                    batch.run_agent(t)
                except Exception as e:
                    batch.update(t["id"], status="failed", error=str(e)[-500:])
        threads = [threading.Thread(target=worker, daemon=True) for _ in range(max(1, args.workers))]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        (base / "agents.finished").write_text(datetime.now(timezone.utc).isoformat() + "\n")
    if args.stage in ("judge", "all") and not args.dry_run:
        todo = [t for t in tasks if batch.state.get(t["id"], {}).get("status") == "completed"
                or (base / "cases" / t["id"] / "run/episode/meta.json").exists()]
        missing = [t["id"] for t in todo if not t["has_rubric"]]
        if missing:
            raise SystemExit(f"no English rubric for {missing}; the judge stage needs one per task")
        q = queue.Queue()
        for t in todo:
            q.put(t)

        def judge_worker():
            while True:
                try:
                    t = q.get_nowait()
                except queue.Empty:
                    return
                batch.run_judge(t, profiles)
        threads = [threading.Thread(target=judge_worker, daemon=True) for _ in range(max(1, args.judge_workers))]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
    batch.summary(tasks)


if __name__ == "__main__":
    main()
