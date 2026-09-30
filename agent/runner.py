"""Episode runner: single episode or a grid, with resume. Output layout is compatible with the
old harness's evaluation scripts (eval/judge_sem.py, eval/video.py, eval/metrics.py):

  runs/<tag>/<task>-p<proprio>-s<seed>/
    meta.json  trajectory.jsonl  frames.jsonl  frames/  actions.jsonl  calls.jsonl
    transcript.jsonl  bugs.jsonl  notes.md  context/  video.mp4

Usage:
  python -m agent.runner --task audit_sp05_bug --seed 0 --model M --base-url http://host:8010/v1
  python -m agent.runner --grid audit_sp05_bug,audit_sp00_clean --episodes 3 --parallel 4 --tag t1 --resume
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from agent.loop import LoopConfig, run_episode
from agent.types import ObsConfig
from harness.tasks import TASKS

REPO = Path(__file__).resolve().parents[1]
# Qwen's recommended sampling for thinking models; top_k / min_p / repetition_penalty are vLLM and
# OpenRouter extensions (OpenRouter drops the ones a provider does not support).
DEFAULT_SAMPLING = dict(top_p=0.95, top_k=20, min_p=0.0, presence_penalty=0.0, repetition_penalty=1.0)


@dataclass
class EpisodeSpec:
    task: str
    seed: int
    run_dir: Path
    obs: str = "film"
    film_dt: float = 0.5
    film_max: int = 8
    ctx_final: Tuple[int, int] = (960, 576)
    ctx_film: Tuple[int, int] = (480, 288)
    context_limit: int = 64000
    keep_recent: int = 3
    tools: Tuple[str, ...] = ("memory", "bugs", "notes")
    expect: bool = True
    proprio: bool = True
    blocked_hint: bool = False
    max_actions: Optional[int] = 100
    max_calls: int = 400
    rate_limit_wait: float = 3600.0
    network_wait: float = 1800.0
    temperature: float = 1.0
    max_tokens: int = 4096
    sampling: dict = field(default_factory=lambda: dict(DEFAULT_SAMPLING))
    reasoning_effort: Optional[str] = "low"
    preserve_thinking: bool = True
    extra_body: dict = field(default_factory=dict)
    decision: str = "macro"
    tick: float = 0.5
    max_sim_seconds: Optional[float] = None
    video: bool = True
    env: str = "threejs"
    gpu: str = "gl-egl"
    model: Optional[str] = None
    base_url: Optional[str] = None
    ue_url: Optional[str] = None


def _size(s: str) -> Tuple[int, int]:
    w, h = s.lower().split("x")
    return int(w), int(h)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Run the tool-calling VLM agent on audit tasks.")
    ap.add_argument("--task", help="single-episode mode: task name from harness/tasks.py")
    ap.add_argument("--grid", help="batch mode: comma-separated task names")
    ap.add_argument("--suite", choices=["tc", "sp", "hs", "wt", "af", "wl", "ct"],
                    help="batch mode: compose the grid from a suite (with --variant [--cases])")
    ap.add_argument("--variant", default="all",
                    help="bug | clean | all (= bug + clean) | l1 | l2 | l3 (ladder levels, SP/HS only)")
    ap.add_argument("--cases", help="comma-separated case numbers to keep, e.g. 01,05,09 (default: every case)")
    ap.add_argument("--episodes", type=int, default=3, help="seeds 0..N-1 per task in grid mode")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--tag", help="run directory name under runs/ (default: timestamp)")
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--resume", action="store_true", help="skip episodes whose meta.json is finished")
    ap.add_argument("--env", default="threejs", choices=["threejs", "ue", "fake"])
    ap.add_argument("--gpu", default="gl-egl", choices=["vulkan", "gl-egl", "swiftshader", "native"],
                    help="Chromium GPU mode: gl-egl (Linux/NVIDIA), native (full Chromium, new headless mode: "
                         "Apple GPU on macOS), swiftshader (software), vulkan")
    ap.add_argument("--ue-url", help="simworld_server base URL (env: SIMWORLD_URL)")
    ap.add_argument("--model", help="model name (env: VLM_MODEL)")
    ap.add_argument("--base-url", help="OpenAI-compatible endpoint (env: VLM_BASE_URL)")
    ap.add_argument("--obs", default="film", choices=["final", "film"])
    ap.add_argument("--film-dt", type=float, default=0.5)
    ap.add_argument("--film-max", type=int, default=8)
    ap.add_argument("--ctx-final", default="960x576", help="in-context size of final frames (multiples of 32)")
    ap.add_argument("--ctx-film", default="480x288", help="in-context size of film frames")
    ap.add_argument("--context-limit", type=int, default=64000,
                    help="compaction threshold in prompt tokens (the note request itself may exceed it by one observation)")
    ap.add_argument("--keep-recent", type=int, default=3, help="env actions kept verbatim after compaction")
    ap.add_argument("--tools", default="memory,bugs,notes", help="enabled tool groups (comma list, or 'none')")
    ap.add_argument("--expect", default="on", choices=["on", "off"], help="expectation-vs-outcome prompt hint")
    ap.add_argument("--proprio", type=int, default=1, choices=[0, 1])
    ap.add_argument("--blocked-hint", type=int, default=0, choices=[0, 1])
    ap.add_argument("--max-actions", default="100",
                    help="env-action budget (default 100; 'task' = the task's own steps from harness/tasks.py)")
    ap.add_argument("--decision", default="macro", choices=["macro", "tick"],
                    help="macro: each action runs to completion; tick: fixed --tick sim seconds per decision")
    ap.add_argument("--tick", type=float, default=0.5, help="simulated seconds per decision in tick mode")
    ap.add_argument("--max-sim-seconds", type=float, help="simulated-time budget (both modes; the action budget still applies)")
    ap.add_argument("--max-calls", type=int, default=400, help="hard cap on model calls")
    ap.add_argument("--rate-limit-wait", type=float, default=3600.0,
                    help="seconds to keep retrying HTTP 429 before giving up on the episode")
    ap.add_argument("--network-wait", type=float, default=1800.0,
                    help="seconds to keep retrying connection errors / timeouts (network outage) before giving up")
    ap.add_argument("--temperature", type=float, default=1.0)
    ap.add_argument("--max-tokens", type=int, default=4096, help="completion budget incl. hidden reasoning")
    ap.add_argument("--top-p", type=float, default=DEFAULT_SAMPLING["top_p"])
    ap.add_argument("--top-k", type=int, default=DEFAULT_SAMPLING["top_k"])
    ap.add_argument("--min-p", type=float, default=DEFAULT_SAMPLING["min_p"])
    ap.add_argument("--presence-penalty", type=float, default=DEFAULT_SAMPLING["presence_penalty"])
    ap.add_argument("--repetition-penalty", type=float, default=DEFAULT_SAMPLING["repetition_penalty"])
    ap.add_argument("--reasoning-effort", default="low", choices=["none", "low", "medium", "high"],
                    help="sent as reasoning.effort; dropped automatically if the server rejects it")
    ap.add_argument("--preserve-thinking", default="on", choices=["on", "off"],
                    help="re-send the model's chain of thought with its earlier turns (Qwen3.8 default); off = "
                         "final text and tool calls only (the older Qwen3 recommendation), thinking still logged")
    ap.add_argument("--thinking-budget", type=int,
                    help="hard cap on reasoning tokens per call (DashScope enable_thinking + thinking_budget; 0 = no "
                         "thinking). Overrides --reasoning-effort, whose levels do not bound the reasoning length.")
    ap.add_argument("--provider-sort", choices=["latency", "throughput", "price"],
                    help="OpenRouter provider routing: sent as provider.sort (latency = lowest time to first token)")
    ap.add_argument("--extra-body", default="{}",
                    help="JSON merged into every chat request (provider routing, seed, ...)")
    ap.add_argument("--no-video", action="store_true")
    return ap


def suite_tasks(suite: str, variant: str = "all", cases: Optional[str] = None) -> List[str]:
    """Task names of one suite: `audit_<suite><NN>_<variant>` for the planted cases, plus the
    clean control (`audit_<suite>00_clean`, TC: `audit_tcNN_clean`) when variant is clean/all."""
    import re
    pat = re.compile(rf"^audit_{suite}(\d\d)_(\w+)$")
    found = {}
    for name in TASKS:
        m = pat.match(name)
        if m:
            found.setdefault(m.group(2), {})[m.group(1)] = name
    if variant == "all":
        wanted = [("bug", True), ("clean", True)]
    else:
        wanted = [(variant, True)]
    keep = set(c.zfill(2) for c in cases.split(",")) if cases else None
    out = []
    for var, _ in wanted:
        if var not in found:
            sys.exit(f"suite {suite} has no '{var}' tasks (available: {', '.join(sorted(found))})")
        for num, name in sorted(found[var].items()):
            if keep is None or num in keep or (var == "clean" and num == "00"):
                out.append(name)
    return out


def specs_from_args(args, runs_base: Path) -> List[EpisodeSpec]:
    if getattr(args, "suite", None) and args.grid:
        sys.exit("use either --suite/--variant or --grid, not both")
    if args.task:
        tasks = [args.task]
    elif getattr(args, "suite", None):
        tasks = suite_tasks(args.suite, args.variant, getattr(args, "cases", None))
    else:
        tasks = args.grid.split(",") if args.grid else []
    if not tasks:
        sys.exit("one of --task / --grid / --suite is required")
    for t in tasks:
        if t not in TASKS:
            sys.exit(f"unknown task {t}; see harness/tasks.py")
        if TASKS[t].get("kind") != "audit":
            sys.exit(f"task {t} is not an audit task; this harness runs audit tasks only")
    if args.decision == "tick" and args.obs == "film":
        sys.exit("--decision tick uses one frame per tick; combine it with --obs final")
    tag = args.tag or time.strftime("%m%d-%H%M%S")
    try:
        extra_body = json.loads(args.extra_body or "{}")
    except ValueError as e:
        sys.exit(f"--extra-body is not valid JSON: {e}")
    if args.provider_sort:
        extra_body.setdefault("provider", {})["sort"] = args.provider_sort
    reasoning_effort = None if args.reasoning_effort == "none" else args.reasoning_effort
    if args.thinking_budget is not None:
        reasoning_effort = None
        extra_body.update({"enable_thinking": True, "thinking_budget": args.thinking_budget} if args.thinking_budget > 0
                          else {"enable_thinking": False})
    seeds = [args.seed] if args.task else list(range(args.episodes))
    tools = tuple(t for t in args.tools.split(",") if t and t != "none")
    common = dict(obs=args.obs, film_dt=args.film_dt, film_max=args.film_max, ctx_final=_size(args.ctx_final),
                  ctx_film=_size(args.ctx_film), context_limit=args.context_limit, keep_recent=args.keep_recent,
                  tools=tools, expect=args.expect == "on", proprio=bool(args.proprio),
                  blocked_hint=bool(args.blocked_hint),
                  max_actions=None if str(args.max_actions) == "task" else int(args.max_actions),
                  max_calls=args.max_calls, rate_limit_wait=args.rate_limit_wait, network_wait=args.network_wait,
                  temperature=args.temperature, max_tokens=args.max_tokens, video=not args.no_video,
                  sampling=dict(top_p=args.top_p, top_k=args.top_k, min_p=args.min_p,
                                presence_penalty=args.presence_penalty, repetition_penalty=args.repetition_penalty),
                  reasoning_effort=reasoning_effort, preserve_thinking=args.preserve_thinking == "on",
                  extra_body=extra_body, decision=args.decision, tick=args.tick, max_sim_seconds=args.max_sim_seconds,
                  env=args.env, gpu=args.gpu, model=args.model, base_url=args.base_url, ue_url=args.ue_url)
    return [EpisodeSpec(task=t, seed=s, run_dir=runs_base / tag / f"{t}-p{int(args.proprio)}-s{s}", **common)
            for t in tasks for s in seeds]


def filter_resume(specs: List[EpisodeSpec]) -> List[EpisodeSpec]:
    def finished(rd: Path) -> bool:
        m = rd / "meta.json"
        return m.exists() and '"ended"' in m.read_text()
    return [s for s in specs if not finished(s.run_dir)]


def make_env(spec: EpisodeSpec):
    if spec.env == "threejs":
        from agent.env.threejs import ThreeJSEnv
        return ThreeJSEnv(gpu=spec.gpu)
    if spec.env == "ue":
        from agent.env.ue import UEEnv
        return UEEnv(base_url=spec.ue_url)
    from agent.env.fake import FakeEnv
    return FakeEnv()


def make_llm(spec: EpisodeSpec):
    from agent.llm import LLMClient
    return LLMClient(base_url=spec.base_url, model=spec.model, temperature=spec.temperature,
                     max_tokens=spec.max_tokens, reasoning_effort=spec.reasoning_effort,
                     extra_body=spec.extra_body, rate_limit_wait=spec.rate_limit_wait, network_wait=spec.network_wait,
                     preserve_thinking=spec.preserve_thinking, **spec.sampling)


def run_one(spec: EpisodeSpec, env_factory: Callable = make_env, llm_factory: Callable = make_llm) -> dict:
    task = TASKS[spec.task]
    cfg = LoopConfig(max_actions=spec.max_actions or task["steps"], max_calls=spec.max_calls,
                     proprio=spec.proprio, blocked_hint=spec.blocked_hint, expect=spec.expect, tools=spec.tools,
                     context_limit=spec.context_limit, keep_recent=spec.keep_recent,
                     obs=ObsConfig(mode=spec.obs, film_dt=spec.film_dt, film_max=spec.film_max,
                                   ctx_final=tuple(spec.ctx_final), ctx_film=tuple(spec.ctx_film)),
                     temperature=spec.temperature, max_tokens=spec.max_tokens,
                     decision=spec.decision, tick=spec.tick, max_sim_seconds=spec.max_sim_seconds)
    env, llm = env_factory(spec), llm_factory(spec)
    started = time.strftime("%F %T")
    try:
        result = run_episode(env, llm, task["instr"], task["config"], spec.seed, spec.run_dir, cfg)
        env_meta = env.meta()
    finally:
        env.close()
    usage = result["usage"]
    meta = dict(
        harness="agent", task=spec.task, config=task["config"], model=llm.model, seed=spec.seed,
        kind=task.get("kind", "nav"), proprio=int(spec.proprio), blocked_hint=int(spec.blocked_hint),
        obs=spec.obs, film_dt=spec.film_dt, film_max=spec.film_max, ctx_final=list(spec.ctx_final),
        ctx_film=list(spec.ctx_film), context_limit=spec.context_limit, keep_recent=spec.keep_recent,
        tools=list(spec.tools), expect=spec.expect, temperature=spec.temperature, max_tokens=spec.max_tokens,
        sampling=dict(spec.sampling), reasoning_effort=spec.reasoning_effort, extra_body=dict(spec.extra_body),
        preserve_thinking=spec.preserve_thinking,
        decision=spec.decision, tick=spec.tick, max_sim_seconds=spec.max_sim_seconds,
        steps_budget=cfg.max_actions, steps_used=result["n_actions"], max_calls=spec.max_calls,
        calls=result["n_calls"], compactions=result["compactions"], started=started, ended=time.strftime("%F %T"),
        env=spec.env, gpu=spec.gpu, renderer=env_meta.get("renderer"), load_time_s=env_meta.get("load_time_s"),
        page_errors=env_meta.get("page_errors", []), console_errors=env_meta.get("console_errors", []),
        flags=result["flags"], bugs_history=result["bugs_history"], vlm_usage=usage,
        cached_ratio=round(usage["cached_tokens"] / usage["prompt_tokens"], 3) if usage.get("prompt_tokens") else None,
        tool_counts=result["tool_counts"], outcome=result["outcome"], done_by_model=result["outcome"] == "done",
        done_summary=result["done_summary"], success=None, false_done=False, sim_t=result["sim_t"],
        wall_s=result["wall_s"], notes=result["notes"])
    (spec.run_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))
    if spec.video:
        try:
            from eval.video import make_video
            make_video(spec.run_dir)
        except Exception:
            traceback.print_exc()
    return meta


def _worker(spec: EpisodeSpec) -> dict:
    try:
        m = run_one(spec)
        return dict(run_dir=str(spec.run_dir), outcome=m["outcome"], actions=m["steps_used"], calls=m["calls"],
                    flags=len(m["flags"]), compactions=m["compactions"], cached_ratio=m["cached_ratio"])
    except Exception as e:
        traceback.print_exc()
        return dict(run_dir=str(spec.run_dir), error=str(e))


def summary_table(rows: List[dict]) -> str:
    cols = ["run_dir", "outcome", "actions", "calls", "flags", "compactions", "cached_ratio", "error"]
    rows = [{c: r.get(c, "") for c in cols} for r in rows]
    widths = {c: max(len(c), *(len(str(r[c])) for r in rows)) for c in cols}
    out = ["  ".join(c.ljust(widths[c]) for c in cols), "  ".join("-" * widths[c] for c in cols)]
    out += ["  ".join(str(r[c]).ljust(widths[c]) for c in cols) for r in rows]
    return "\n".join(out)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    specs = specs_from_args(args, REPO / "runs")
    if args.resume:
        n0 = len(specs)
        specs = filter_resume(specs)
        print(f"resume: {n0 - len(specs)} finished episodes skipped")
    if args.task:
        m = run_one(specs[0])
        print(json.dumps({k: m[k] for k in ("task", "model", "outcome", "steps_used", "calls", "compactions",
                                            "cached_ratio")}, ensure_ascii=False))
        print(f"flags: {len(m['flags'])}  output: {specs[0].run_dir}")
        return 0
    base = specs[0].run_dir.parent if specs else None
    print(f"{len(specs)} episodes, parallel={args.parallel} -> {base}")
    from multiprocessing import get_context
    rows = []
    with get_context("spawn").Pool(args.parallel) as pool:
        for r in pool.imap_unordered(_worker, specs):
            rows.append(r)
            print(json.dumps(r, ensure_ascii=False))
    if base:
        table = summary_table(sorted(rows, key=lambda r: r["run_dir"]))
        (base / "summary.md").write_text(table + "\n")
        print("\n" + table)
    return 0


if __name__ == "__main__":
    sys.exit(main())
