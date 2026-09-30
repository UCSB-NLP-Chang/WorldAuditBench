"""Prompt text. `build_system` is byte-identical for a given switch set, so it stays in the
cached prefix across every call and every episode of a run."""
from __future__ import annotations

from typing import Iterable, List, Optional

TAXONOMY = """Standard game-bug TYPES to check for:
(1) GEOMETRY & SPACE: objects clipping into each other or into floors/walls; objects floating in mid-air; abnormal scale vs identical siblings; duplicated/overlapping objects; implausible layout.
(2) COLLISION & PHYSICS: walking through solid-looking objects; invisible blockers where nothing is visible; falling through the floor; objects moving on their own with no cause.
(3) VISUAL CONSISTENCY: missing textures (flat unnatural colors); objects invisible from some viewpoints yet present from others; objects rendering through walls/occluders; wrong materials; shadow/light anomalies.
(4) SPATIOTEMPORAL & STATE CONSISTENCY: an object that is gone (or elsewhere) when you look back at it; abrupt state changes over time; things reverting by themselves. Re-checking a spot you saw earlier is a valid and useful test.
(5) SEMANTICS & WORLD LOGIC: assets that do not belong in the scene; objects placed where they make no sense; impossible spatial connections.
Normal scene content (plants, curtains, banners, pillars, furniture, decorations) is NOT a bug by itself: judge against the scene's own consistency - identical elements should look and behave identically."""

OBS_FINAL = """Observation: after each environment action you receive one full-resolution first-person view taken when the action has finished, plus a text line with the action's result. The reference of that view is a<N> for action number N (a0 is the start view)."""

OBS_FILM = """Observation: after each environment action you receive a FILM STRIP - low-resolution frames sampled at fixed simulated-time intervals during the action (each labelled a<N>.f<i> and t=+X.Xs) - followed by the full-resolution final view a<N>. Use the changes (or lack of changes) between frames to understand what happened during the action; standing still with wait films the scene over time."""

MEMORY = """Memory: every frame you have ever received is archived at full resolution. Use inspect(refs) to bring earlier frames back (optionally a region of one, zoomed) so you can compare then and now, and history(from_action, to_action) to re-read what you did and saw in earlier actions. The conversation may be compacted when it grows long: you then receive your own continuation note plus an index of every action; use inspect/history to recover any detail you need."""

NOTES = """Notes: write_notes appends a short entry to your durable notes (areas checked, suspicions with frame refs, plans). The notes survive compaction: when the context is compacted you rewrite them as a whole, and the rewritten notes are what you keep."""

BUGS = """Bug reports: flag_bug records a bug at your current position with an id (b1, b2, ...). Report a suspicion as status "suspect", then verify it (another angle, closer look, re-check later, inspect earlier frames) and use update_bug to set "confirmed" or "retracted". Attach evidence frame refs when you can. Flag each distinct bug once. Only non-retracted reports count; wrong or duplicated reports are penalized, so retract what does not hold up."""

EXPECT = """Strategy: before each action, say briefly what you expect to see; afterwards, note every visible change, expected or not. A bug is usually a violated expectation."""

RULES = """Rules:
- The world is PAUSED while you think; simulated time passes only inside your actions.
- Actively TEST the area: walk through it, view things from more than one angle, use wait to watch things over time, use interact on mechanisms. If you command a move but travel much less than asked while nothing solid is visibly in the way, that is evidence of an invisible blocker.
- Inspect objects from 2-4 metres away so the whole object and its surroundings fit in view; use look up/down when needed. Verify every claim against the actual images.
- You have a limited budget of environment actions (stated in the task). Memory and bug tools do not consume it. Finish with done when the inspection is complete - do not flag normal objects."""


def tick_text(tick: float, limits: dict) -> str:
    return (f"Decision ticks: simulated time advances in fixed ticks of {tick:g} s per decision. The environment "
            f"actions in one reply run in order inside one tick (move at most {limits.get('move', 0):g} m, turn or "
            f"look at most {limits.get('turn', 0):g} degrees, wait = observe for the tick); the tick always lasts "
            f"{tick:g} s - the agent stands still for whatever time is left - and the observation you receive is the "
            f"view at the end of the tick. interact triggers a mechanism and it keeps running through the following "
            f"ticks. If you ask for more than fits in a tick, the part that fits runs and the observation says so "
            f"([tick limit ...]); then decide again - continue the same action or do something else. Memory and "
            f"bug tools take no time.")


def build_system(obs_mode: str, expect: bool, enabled: Iterable[str], capabilities: Iterable[str],
                 decision: str = "macro", tick: float = 0.5, limits: Optional[dict] = None) -> str:
    enabled, caps = set(enabled), set(capabilities)
    acts: List[str] = []
    if "move" in caps:
        acts.append("move(distance_m, direction) walks forward/back")
    if "turn" in caps:
        acts.append("turn(degrees) turns in place (positive = right)")
    if "look" in caps:
        acts.append("look(degrees) tilts the view (positive = down)")
    if "interact" in caps:
        acts.append("interact() uses what you are aiming at within ~3 m")
    if "wait" in caps:
        acts.append("wait(seconds) stands still and observes")
    parts = [
        "You are a game QA tester controlling a first-person agent in a 3D world through tools. "
        "Your job is to inspect the world for BUGS - anything broken, impossible, or inconsistent with how "
        "a normal game world should look and behave - and to report them precisely.",
        TAXONOMY,
        "Environment actions: " + "; ".join(acts) + "; done(summary) ends the inspection. "
        "You may call several tools in one reply; they run in the order given, and each environment action "
        "returns its own observation.",
        OBS_FILM if obs_mode == "film" else OBS_FINAL,
    ]
    if decision == "tick":
        parts.append(tick_text(tick, limits or {}))
    if "memory" in enabled:
        parts.append(MEMORY)
    if "notes" in enabled:
        parts.append(NOTES)
    if "bugs" in enabled:
        parts.append(BUGS)
    if expect:
        parts.append(EXPECT)
    parts.append(RULES)
    return "\n\n".join(parts)


def task_text(instr: str, max_actions: int, max_sim_seconds: Optional[float] = None,
              tick: Optional[float] = None) -> str:
    if max_sim_seconds is not None:
        t = max_sim_seconds
        line = f"Time budget: {t:g} simulated second{'' if t == 1 else 's'}"
        if tick:
            line += f" (about {int(t / tick)} decisions of {tick:g} s)"
        return f"TASK: {instr}\n{line}."
    return f"TASK: {instr}\nAction budget: {max_actions} environment actions."


def compact_prompt(notes: str) -> str:
    cur = notes.strip() or "(empty)"
    return f"""Your context is about to be compacted: everything above except the last few actions will be dropped, and your notes will be carried over instead. Rewrite your notes now as a complete continuation state (at most about 300 words). Keep what is still useful from the current notes, drop what is stale, and cover:
1. task progress so far;
2. areas covered and not yet covered, citing action refs like a12;
3. suspicious observations, with the frame refs that show them;
4. your current judgement on each flagged bug;
5. what you will do next.

Current notes:
{cur}

Reply with the rewritten notes only."""


NUDGE = "Reply with a tool call: an environment action, a memory or bug tool, or done when the inspection is complete."


def header(task: str, epoch: int, n_actions: int, notes: str, index_lines: List[str], ledger: str,
           keep_recent: int) -> str:
    idx = "\n".join(index_lines) if index_lines else "(no actions yet)"
    return (f"{task}\n\n[Continuation #{epoch} after context compaction - {n_actions} actions done]\n\n"
            f"## Your notes (rewritten at compaction)\n{notes.strip() or '(empty)'}\n\n"
            f"## Action index (a0..a{n_actions})\n{idx}\n\n"
            f"## Bug ledger\n{ledger}\n\n"
            f"The last {keep_recent} actions follow verbatim.")
