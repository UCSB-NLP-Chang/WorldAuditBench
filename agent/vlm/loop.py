"""The episode loop: a flat tool loop. The model replies with tool calls; the dispatcher runs
them in order (environment actions return observations immediately); everything is appended
to the conversation; the conversation is compacted once when it crosses the token limit."""
from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple

from agent.vlm.archive import FrameArchive
from agent.vlm.context import Conversation, text_tokens
from agent.vlm.ledger import BugLedger
from agent.vlm.notes import Notes
from agent.vlm.prompts import NUDGE, build_system, compact_prompt, header, task_text
from agent.vlm.tools import Dispatcher, tool_schemas
from agent.vlm.types import ObsConfig


@dataclass
class LoopConfig:
    max_actions: int = 100
    max_calls: int = 400
    proprio: bool = True
    blocked_hint: bool = False
    expect: bool = True
    tools: Tuple[str, ...] = ("memory", "bugs", "notes")
    context_limit: int = 64000
    keep_recent: int = 3
    obs: ObsConfig = field(default_factory=ObsConfig)
    temperature: float = 1.0
    max_tokens: int = 4096
    decision: str = "macro"           # "macro": actions run to completion; "tick": fixed sim seconds per decision
    tick: float = 0.5                 # seconds of simulated time per decision in tick mode
    max_sim_seconds: Optional[float] = None   # optional simulated-time budget (both modes)

    def __post_init__(self):
        if self.decision not in ("macro", "tick"):
            raise ValueError("decision must be 'macro' or 'tick'")
        if self.decision == "tick" and self.obs.mode == "film":
            raise ValueError("tick decisions are defined with one frame per tick; film observation is not supported")


class Transcript:
    """Writes every message the model sees to transcript.jsonl (images as refs)."""

    def __init__(self, path: Path, conv: Conversation):
        self.path, self.conv, self.written = path, conv, 0

    def flush(self):
        with open(self.path, "a") as f:
            for m in self.conv.messages[self.written:]:
                f.write(json.dumps(self.conv.transcript_row(m), ensure_ascii=False) + "\n")
        self.written = len(self.conv.messages)

    def compacted(self, epoch: int):
        """Log the rebuild as an event plus the new header; the kept tail was already written."""
        with open(self.path, "a") as f:
            f.write(json.dumps({"event": "compaction", "epoch": epoch}) + "\n")
            f.write(json.dumps(self.conv.transcript_row(self.conv.messages[1]), ensure_ascii=False) + "\n")
        self.written = len(self.conv.messages)


def run_episode(env, llm, task_instr: str, config: str, seed: int, run_dir, cfg: LoopConfig) -> dict:
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    for name in ("actions.jsonl", "trajectory.jsonl", "frames.jsonl", "calls.jsonl", "transcript.jsonl", "bugs.jsonl"):
        (run_dir / name).write_text("")
    for sub in ("frames", "context"):                  # a rerun (resume after a crash) starts from a clean archive
        if (run_dir / sub).exists():
            shutil.rmtree(run_dir / sub)
    for name in ("notes.md", "meta.json", "video.mp4"):
        if (run_dir / name).exists():
            (run_dir / name).unlink()
    archive, ledger, notes = FrameArchive(run_dir), BugLedger(run_dir), Notes(run_dir)
    enabled = set(cfg.tools)
    limits = None
    if cfg.decision == "tick":
        speed, turn = getattr(env, "speed_mps", 5.2), getattr(env, "turn_dps", 120.0)
        limits = {"move": round(speed * cfg.tick * 0.9, 2), "turn": turn * cfg.tick, "look": turn * cfg.tick,
                  "wait": cfg.tick}
    system = build_system(cfg.obs.mode, cfg.expect, enabled, env.capabilities, cfg.decision, cfg.tick, limits)
    tools = tool_schemas(env.capabilities, enabled, limits)
    conv = Conversation(system, context_limit=cfg.context_limit, keep_recent=cfg.keep_recent,
                        extra_tokens=text_tokens(json.dumps(tools)))
    task = task_text(task_instr, cfg.max_actions, cfg.max_sim_seconds,
                     cfg.tick if cfg.decision == "tick" else None)

    obs0 = env.reset(config, seed, cfg.obs)
    obs0.action_index = 0
    disp = Dispatcher(env, archive, ledger, notes, conv, cfg.obs, run_dir, cfg.max_actions,
                      proprio=cfg.proprio, blocked_hint=cfg.blocked_hint, decision=cfg.decision, tick=cfg.tick,
                      max_sim_seconds=cfg.max_sim_seconds)
    text, items = disp.observe_initial(obs0, task)
    conv.append_user_images(text, items)
    transcript = Transcript(run_dir / "transcript.jsonl", conv)
    transcript.flush()

    n_calls = 0
    empty_streak = 0
    outcome = None
    steps_since_compaction = 1      # compaction is allowed only after at least one step call
    required_ok = True              # some providers reject tool_choice="required" (thinking modes)
    trunc_retries = 0               # thinking models can spend the whole output budget before the tool call
    max_tokens = cfg.max_tokens
    t_start = time.time()

    def log_call(kind, resp, tool_choice, predicted, names):
        u = resp["usage"]
        row = dict(call=n_calls, t=round(time.time(), 2), kind=kind, tool_choice=tool_choice, tools=names,
                   rate_limited=resp.get("rate_limited", 0), rate_limit_wait_s=resp.get("rate_limit_wait_s", 0),
                   reasoning_chars=len(resp.get("reasoning") or ""),
                   prompt_tokens=u["prompt_tokens"], completion_tokens=u["completion_tokens"],
                   cached_tokens=u["cached_tokens"], reasoning_tokens=u.get("reasoning_tokens", 0),
                   predicted_prompt=predicted,
                   drift=u["prompt_tokens"] - predicted, latency_s=resp.get("latency_s"),
                   finish_reason=resp.get("finish_reason"), provider=resp.get("provider"),
                   content_chars=len(resp["message"].get("content") or ""))
        with open(run_dir / "calls.jsonl", "a") as f:
            f.write(json.dumps(row) + "\n")

    def compact():
        nonlocal n_calls
        conv.begin_compaction(compact_prompt(notes.read()))
        predicted = conv.predicted_next()
        resp = llm.chat(conv.snapshot(), tools=None, max_tokens=cfg.max_tokens, temperature=cfg.temperature)
        n_calls += 1
        log_call("compaction", resp, "none", predicted, [])
        note = (resp["message"].get("content") or "").strip()
        if note:                                   # the rewrite replaces the notes; an empty reply keeps them
            notes.write(note)
        epoch = conv.compactions + 1
        ctx_dir = run_dir / "context"
        ctx_dir.mkdir(exist_ok=True)
        (ctx_dir / f"note_{epoch}.md").write_text(notes.read())
        head = header(task, epoch, disp.n_actions, notes.read(), disp.index_lines, ledger.render(),
                      cfg.keep_recent)
        old = conv.finish_compaction(head)
        (ctx_dir / f"epoch_{epoch}.json").write_text(
            json.dumps([conv.transcript_row(m) for m in old], ensure_ascii=False, indent=1))
        transcript.compacted(epoch)

    while True:
        if n_calls >= cfg.max_calls:
            outcome = "max_calls"
            break
        # Compact once the predicted prompt crosses the limit, but never twice in a row: if the
        # header + kept tail alone exceeds the limit (tiny limits), proceed rather than spin.
        if conv.needs_compaction() and steps_since_compaction > 0:
            compact()
            steps_since_compaction = 0
            continue
        tool_choice = "required" if (empty_streak >= 2 and required_ok) else "auto"
        predicted = conv.predicted_next()
        try:
            resp = llm.chat(conv.snapshot(), tools=tools, tool_choice=tool_choice,
                            max_tokens=max_tokens, temperature=cfg.temperature)
        except RuntimeError as e:
            if tool_choice == "required" and "400" in str(e):
                required_ok = False                     # fall back to auto for the rest of the episode
                tool_choice = "auto"
                resp = llm.chat(conv.snapshot(), tools=tools, tool_choice=tool_choice,
                                max_tokens=max_tokens, temperature=cfg.temperature)
            else:
                raise
        n_calls += 1
        steps_since_compaction += 1
        msg = resp["message"]
        calls = msg.get("tool_calls") or []
        if not calls and resp.get("finish_reason") == "length" and trunc_retries < 2:
            # truncated before any tool call (reasoning ate the budget): retry with more room, append nothing
            log_call("step", resp, tool_choice, predicted, [])
            trunc_retries += 1
            max_tokens = min(max_tokens * 2, cfg.max_tokens * 4)
            continue
        trunc_retries = 0
        if resp.get("reasoning") and "reasoning_content" not in msg:
            msg["_reasoning"] = resp["reasoning"]        # preserve_thinking off: log it, do not re-send it
        conv.append_assistant(msg, call=n_calls)
        conv.record_usage(resp["usage"]["prompt_tokens"], resp["usage"]["completion_tokens"])
        log_call("step", resp, tool_choice, predicted, [c["function"]["name"] for c in calls])
        if not calls:
            empty_streak += 1
            if empty_streak >= 3:
                outcome = "no_action"
                break
            if empty_streak == 1:
                conv.append_user_text(NUDGE)
            transcript.flush()
            continue
        empty_streak = 0
        disp.run(calls, n_calls, msg.get("content") or "")
        transcript.flush()
        if disp.done:
            outcome = "done"
            break
        if disp.budget_hit or disp.n_actions >= cfg.max_actions or \
                (cfg.max_sim_seconds is not None and disp.sim_t >= cfg.max_sim_seconds - 1e-6):
            outcome = "budget"
            break

    transcript.flush()
    return dict(outcome=outcome, n_actions=disp.n_actions, n_calls=n_calls, compactions=conv.compactions,
                usage=dict(llm.total_usage), tool_counts=dict(disp.tool_counts), flags=ledger.export(),
                bugs_history=ledger.history(), done_summary=disp.done_summary, notes=notes.read(),
                sim_t=disp.sim_t, wall_s=round(time.time() - t_start, 1),
                index_lines=list(disp.index_lines))
