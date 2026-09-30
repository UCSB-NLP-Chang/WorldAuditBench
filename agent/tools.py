"""Tool schemas (OpenAI function-calling format) and the dispatcher that executes tool calls
against the environment, the frame archive, the bug ledger and the notes."""
from __future__ import annotations

import base64
import json
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from agent.archive import FrameArchive
from agent.context import Conversation
from agent.env.base import is_blocked
from agent.ledger import CATEGORIES, BugLedger
from agent.notes import Notes
from agent.types import Action, Observation, ObsConfig

ENV_ACTIONS = ("move", "turn", "look", "interact", "wait")
MAX_INSPECT = 4
MAX_HISTORY_SPAN = 40


def _fn(name, description, properties=None, required=()):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties or {}, "required": list(required)}}}


def tool_schemas(capabilities: Iterable[str], enabled: Iterable[str], limits: Optional[dict] = None) -> List[dict]:
    """`limits` overrides the per-action maxima (fixed-tick mode: what fits in one tick):
    {"move": metres, "turn": degrees, "look": degrees, "wait": seconds}."""
    caps, en, lim = set(capabilities), set(enabled), dict(limits or {})
    out = []
    if "move" in caps:
        out.append(_fn("move", "Walk in a straight line. Stops early if something blocks the way.",
                       {"distance_m": {"type": "number", "minimum": min(0.3, lim.get("move", 4)), "maximum": lim.get("move", 4),
                                       "description": "metres to walk"},
                        "direction": {"type": "string", "enum": ["forward", "back"]}},
                       ["distance_m", "direction"]))
    if "turn" in caps:
        t = lim.get("turn", 180)
        out.append(_fn("turn", "Turn in place.",
                       {"degrees": {"type": "number", "minimum": -t, "maximum": t,
                                    "description": "positive = turn RIGHT, negative = LEFT"}}, ["degrees"]))
    if "look" in caps:
        t = lim.get("look", 90)
        out.append(_fn("look", "Tilt the view up or down.",
                       {"degrees": {"type": "number", "minimum": -t, "maximum": t,
                                    "description": "positive = look DOWN, negative = UP"}}, ["degrees"]))
    if "interact" in caps:
        out.append(_fn("interact", "Press/use/open what you are aiming at (must be within ~3 m)."))
    if "wait" in caps:
        w = lim.get("wait", 5)
        out.append(_fn("wait", "Stand still and observe for a while (sensing action: watch how things behave over time).",
                       {"seconds": {"type": "number", "minimum": min(0.5, w), "maximum": w}}, ["seconds"]))
    out.append(_fn("done", "Finish the inspection.", {"summary": {"type": "string"}}, ["summary"]))
    if "memory" in en:
        out.append(_fn("inspect", "Bring archived frames back into view at full resolution (up to 4 refs), "
                                  "optionally zooming into a region of them.",
                       {"refs": {"type": "array", "items": {"type": "string"},
                                 "description": "frame refs like a12 (final view of action 12) or a12.f3 (film frame 3)"},
                        "region": {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4,
                                   "description": "optional [x0, y0, x1, y1] in 0..1 image coordinates to crop and zoom"}},
                       ["refs"]))
        out.append(_fn("history", "Re-read what you did, thought and observed in a range of earlier actions "
                                  "(text only; use inspect for the images).",
                       {"from_action": {"type": "integer"}, "to_action": {"type": "integer"}},
                       ["from_action", "to_action"]))
    if "bugs" in en:
        out.append(_fn("flag_bug", "Report a bug at your current position. Returns its id.",
                       {"description": {"type": "string", "description": "what is wrong, which object, how you know"},
                        "category": {"type": "string", "enum": list(CATEGORIES)},
                        "status": {"type": "string", "enum": ["suspect", "confirmed"]},
                        "evidence": {"type": "array", "items": {"type": "string"},
                                     "description": "frame refs that show the problem"}},
                       ["description", "category", "status"]))
        out.append(_fn("update_bug", "Revise a reported bug: change its description, status "
                                     "(suspect / confirmed / retracted) or evidence.",
                       {"id": {"type": "string"}, "description": {"type": "string"},
                        "status": {"type": "string", "enum": ["suspect", "confirmed", "retracted"]},
                        "evidence": {"type": "array", "items": {"type": "string"}}}, ["id"]))
        out.append(_fn("list_bugs", "List the bugs reported so far."))
    if "notes" in en:
        out.append(_fn("write_notes", "Append one short entry to your notes (durable memory that survives "
                                      "context compaction; cite frame refs like a12). You rewrite the whole "
                                      "notes file when the context is compacted.",
                       {"text": {"type": "string"}}, ["text"]))
    return out


def _old_action(action: Action) -> dict:
    """Old harness action shape for trajectory.jsonl / eval compatibility."""
    p = action.params
    if action.kind == "move":
        return {"action": "forward" if p.get("direction") != "back" else "back", "dist": p.get("distance_m")}
    if action.kind == "turn":
        return {"action": "turn", "deg": p.get("degrees")}
    if action.kind == "look":
        return {"action": "look", "deg": p.get("degrees")}
    if action.kind == "wait":
        return {"action": "wait", "ms": round(float(p.get("seconds", 1)) * 1000)}
    return {"action": action.kind}


def _describe(action: Action) -> str:
    p = action.params
    if action.kind == "move":
        return f"move {p.get('direction', 'forward')} {float(p['distance_m']):.1f}m"
    if action.kind == "turn":
        d = float(p["degrees"])
        return f"turn {abs(d):.0f} deg ({'right' if d >= 0 else 'left'})"
    if action.kind == "look":
        d = float(p["degrees"])
        return f"look {abs(d):.0f} deg ({'down' if d >= 0 else 'up'})"
    if action.kind == "wait":
        return f"wait {float(p['seconds']):.1f}s"
    return action.kind


def _parse_action(name: str, args: dict) -> Action:
    if name == "move":
        d = float(args.get("distance_m", 1.5))
        direction = args.get("direction", "forward")
        if direction not in ("forward", "back"):
            raise ValueError("direction must be 'forward' or 'back'")
        return Action("move", {"distance_m": min(max(d, 0.3), 4.0), "direction": direction})
    if name == "turn":
        return Action("turn", {"degrees": min(max(float(args.get("degrees", 45)), -180.0), 180.0)})
    if name == "look":
        return Action("look", {"degrees": min(max(float(args.get("degrees", 20)), -90.0), 90.0)})
    if name == "wait":
        return Action("wait", {"seconds": min(max(float(args.get("seconds", 1.0)), 0.5), 5.0)})
    return Action("interact", {})


class Dispatcher:
    def __init__(self, env, archive: FrameArchive, ledger: BugLedger, notes: Notes, conv: Conversation,
                 obs: ObsConfig, run_dir, max_actions: int, proprio: bool = True, blocked_hint: bool = False,
                 decision: str = "macro", tick: float = 0.5, max_sim_seconds: Optional[float] = None):
        self.env, self.archive, self.ledger, self.notes, self.conv = env, archive, ledger, notes, conv
        self.obs_cfg, self.run_dir, self.max_actions = obs, Path(run_dir), max_actions
        self.proprio, self.blocked_hint = proprio, blocked_hint
        self.decision, self.tick, self.max_sim_seconds = decision, tick, max_sim_seconds
        self._tick_remaining: Optional[float] = None
        self._last_env_call: Optional[int] = None
        self.n_actions = 0
        self.done = False
        self.done_summary: Optional[str] = None
        self.budget_hit = False
        self.pose = None
        self.sim_t = 0.0
        self.index_lines: List[str] = []
        self.records: Dict[int, dict] = {}
        self.tool_counts: Counter = Counter()
        self._inspect_cache: Dict[Tuple[str, Optional[tuple]], str] = {}
        self._crop_refs: Dict[Tuple[str, Optional[tuple]], str] = {}

    # ----------------------------------------------------------- observation
    def observe_initial(self, obs: Observation, task: str) -> Tuple[str, list]:
        self.archive.put(obs)
        self.pose = obs.pose
        self._frames_rows(obs, None, "start", False, "")
        self.index_lines.append(f"a0 start -> {self._pose_text(obs)} | frames a0" if self.proprio else "a0 start | frames a0")
        text = f"{task}\n\n[observation a0] start view" + (f" | {self._pose_text(obs)}" if self.proprio else "")
        return text, self._image_items(obs)

    def _pose_text(self, obs: Observation) -> str:
        p = obs.pose
        return f"pos (x={p.x:.2f}, y={p.y:.2f}) yaw {p.yaw:.0f} pitch {p.pitch:.0f}"

    def _image_items(self, obs: Observation) -> list:
        items = []
        for f in obs.frames:
            if f.kind == "film":
                items.append((f"{f.ref} t=+{f.t_sim:.1f}s", self.archive.ctx_image(f.ref, self.obs_cfg.ctx_film), f.ref))
            else:
                caption = f"{f.ref} final view" if obs.action_index else f"{f.ref} start view"
                items.append((caption, self.archive.ctx_image(f.ref, self.obs_cfg.ctx_final), f.ref))
        return items

    def _frames_text(self, obs: Observation) -> str:
        film = [f.ref for f in obs.frames if f.kind == "film"]
        final = [f.ref for f in obs.frames if f.kind == "final"]
        parts = []
        if film:
            parts.append((f"{film[0]}..{film[-1]}" if len(film) > 1 else film[0]) + " (film)")
        if final:
            parts.append(f"{final[0]} (final)")
        return "frames: " + ", ".join(parts)

    # ------------------------------------------------------------- dispatch
    def run(self, tool_calls: List[dict], call_no: int, content: str) -> None:
        env_idx = [i for i, c in enumerate(tool_calls) if c["function"]["name"] in ENV_ACTIONS]
        self._last_env_call = env_idx[-1] if env_idx else None
        self._tick_remaining = self.tick if self.decision == "tick" else None
        for i, call in enumerate(tool_calls):
            self._is_last_env = (i == self._last_env_call)
            name = call["function"]["name"]
            self.tool_counts[name] += 1
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
                if not isinstance(args, dict):
                    raise ValueError("arguments must be a JSON object")
            except (json.JSONDecodeError, ValueError) as e:
                self.conv.append_tool(call["id"], f"ERROR: could not parse arguments for {name}: {e}")
                continue
            try:
                text, label, items = self._execute(name, args, call_no, content)
            except Exception as e:                      # never let a tool take the episode down
                text, label, items = f"ERROR: {name} failed: {e}", None, []
            self.conv.append_tool(call["id"], text)
            if items:
                self.conv.append_user_images(label, items)

    def _execute(self, name: str, args: dict, call_no: int, content: str):
        if name in ENV_ACTIONS:
            return self._env_action(name, args, call_no, content)
        if name == "done":
            self.done, self.done_summary = True, str(args.get("summary", ""))
            return "Inspection finished.", None, []
        if name == "inspect":
            return self._inspect(args)
        if name == "history":
            return self._history(args), None, []
        if name == "flag_bug":
            return self._flag(args), None, []
        if name == "update_bug":
            return self._update(args), None, []
        if name == "list_bugs":
            return self.ledger.render(), None, []
        if name == "write_notes":
            text = str(args.get("text", "")).strip()
            if not text:
                return "ERROR: write_notes needs non-empty text.", None, []
            self.notes.append(text)
            n = self.notes.count()
            return f"Note added ({n} {'entry' if n == 1 else 'entries'}).", None, []
        return f"ERROR: unknown tool {name}", None, []

    # ------------------------------------------------------------ env action
    def _env_action(self, name: str, args: dict, call_no: int, content: str):
        if self.done:
            return "ERROR: the inspection is already finished (done was called).", None, []
        if self.n_actions >= self.max_actions:
            self.budget_hit = True
            return "ERROR: action budget exhausted - no more environment actions; call done.", None, []
        if self.max_sim_seconds is not None and self.sim_t >= self.max_sim_seconds - 1e-6:
            self.budget_hit = True
            return "ERROR: time budget exhausted - no more environment actions; call done.", None, []
        try:
            action = _parse_action(name, args)
        except (ValueError, TypeError) as e:
            return f"ERROR: invalid arguments for {name}: {e}", None, []
        clamp_note = None
        if self._tick_remaining is not None:
            rem = self._tick_remaining
            if rem <= 0.01:
                return (f"ERROR: no time left in this tick ({self.tick:g} s per decision) - "
                        f"this action will be possible at your next decision.", None, [])
            clamp_note = self._fit_to_tick(action, rem)
        obs = self.env.step(action)
        self.n_actions += 1
        n = self.n_actions
        obs.action_index = n
        self.archive.put(obs)
        self.conv.mark_action(n)
        blocked = is_blocked(action, obs)
        self.pose = obs.pose
        self.sim_t = round(self.sim_t + obs.sim_elapsed, 3)
        if self._tick_remaining is not None:
            self._tick_remaining = max(0.0, round(self._tick_remaining - obs.sim_elapsed, 4))
        desc = _describe(action)
        frames = self._frames_text(obs)
        if self.proprio:
            text = (f"a{n} {desc} -> moved {obs.moved:.2f}m | {self._pose_text(obs)} | "
                    f"sim +{obs.sim_elapsed:.1f}s | {frames}")
            if blocked and self.blocked_hint:
                text += "  [BLOCKED - something invisible or solid is in the way]"
            flags = ("BLOCKED " if blocked else "") + ("TELEPORTED " if obs.events.get("teleported") else "") \
                + ("RESPAWNED " if obs.events.get("respawned") else "")
            self.index_lines.append(f"a{n} {desc} -> moved {obs.moved:.2f}m {self._pose_text(obs)} "
                                    f"{flags}| frames {self._frames_text(obs)[8:]}")
        else:
            # pure vision: no action echo, no displacement, no pose, no obstruction hint anywhere the
            # model can see (observation, compaction index); only the frame refs it needs for memory
            text = f"a{n} | {frames}"
            self.index_lines.append(f"a{n} {desc} | frames {self._frames_text(obs)[8:]}")
        if clamp_note:
            text += f"  {clamp_note}"
        if obs.events.get("env_note"):
            text += f"  [{obs.events['env_note']}]"
        self.records[n] = dict(index=n, call=call_no, content=content, desc=desc, result=text)
        self._log_action(n, call_no, action, obs, blocked, content, text)
        self._frames_rows(obs, action, desc, blocked, content)
        return text, f"[observation a{n}]", self._image_items(obs)

    def _fit_to_tick(self, action: Action, rem: float) -> Optional[str]:
        """Clamp an action to what fits in the remaining tick time; the last env action of the reply
        holds the tick to its full length. Moves are clamped to 90 % of the reachable distance so
        the time cap never cuts them (a time-cut move would read as an obstruction). Returns a note
        for the model when the request exceeded the tick: it ran partially and a new decision is due."""
        p = action.params
        speed, turn = getattr(self.env, "speed_mps", 5.2), getattr(self.env, "turn_dps", 120.0)
        note = None
        tail = (f"in one {self.tick:g} s tick; that part ran and the tick is over - decide again: "
                f"continue the same action or choose another]")
        if action.kind == "move":
            lim = round(speed * rem * 0.9, 2)
            if p["distance_m"] > lim + 1e-9:
                note = f"[tick limit: you asked for {p['distance_m']:.1f} m, {lim:g} m fits {tail}"
                p["distance_m"] = lim
        elif action.kind in ("turn", "look"):
            lim = round(turn * rem, 1)
            if abs(p["degrees"]) > lim + 1e-9:
                note = f"[tick limit: you asked for {abs(p['degrees']):.0f} deg, {lim:g} deg fits {tail}"
                p["degrees"] = max(-lim, min(lim, p["degrees"]))
        elif action.kind == "wait":
            if p["seconds"] > rem + 1e-9:
                note = f"[tick limit: you asked for {p['seconds']:.1f} s, {rem:g} s fits {tail}"
            p["seconds"] = round(rem, 3)
        p["max_sec"] = round(rem, 3)
        if self._is_last_env:
            p["hold_sec"] = round(rem, 3)
        return note

    def _log_action(self, n, call_no, action, obs, blocked, content, text):
        p = obs.pose
        row = dict(index=n, call=call_no, action=dict(kind=action.kind, params=action.params), moved=obs.moved,
                   pose=dict(x=p.x, y=p.y, z=p.z, yaw=p.yaw, pitch=p.pitch), blocked=blocked, events=obs.events,
                   sim_elapsed=obs.sim_elapsed, sim_t=self.sim_t, frames=[f.ref for f in obs.frames],
                   content=content, result=text)
        with open(self.run_dir / "actions.jsonl", "a") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        traj = dict(step=n, action=_old_action(action), pos=list(p.raw.get("pos", [p.x, p.z, p.y])),
                    yaw=p.yaw, moved=obs.moved, blocked=blocked,
                    teleported=bool(obs.events.get("teleported")), respawned=bool(obs.events.get("respawned")),
                    latency_s=None, reply=content)
        with open(self.run_dir / "trajectory.jsonl", "a") as f:
            f.write(json.dumps(traj, ensure_ascii=False) + "\n")

    def _frames_rows(self, obs, action, desc, blocked, content):
        p = obs.pose
        with open(self.run_dir / "frames.jsonl", "a") as f:
            for fr in obs.frames:
                cap = [f"a{obs.action_index} | {json.dumps(_old_action(action)) if action else 'start'} | "
                       f"moved {obs.moved}" + (" | BLOCKED" if blocked else "")
                       + (f" | film t=+{fr.t_sim}s" if fr.kind == "film" else ""),
                       f"yaw {p.yaw} | pos ({p.x:.1f},{p.y:.1f})",
                       (content or "")[:120].replace("\n", " ")]
                f.write(json.dumps({"file": f"frames/{fr.path.name}", "caption": cap}, ensure_ascii=False) + "\n")

    # ---------------------------------------------------------- memory tools
    def _inspect(self, args: dict):
        refs = args.get("refs") or []
        if not isinstance(refs, list) or not refs:
            return "ERROR: inspect needs a non-empty list of frame refs.", None, []
        if len(refs) > MAX_INSPECT:
            return f"ERROR: inspect takes at most {MAX_INSPECT} refs per call ({len(refs)} given).", None, []
        unknown = [r for r in refs if not self.archive.has(r)]
        if unknown:
            return f"ERROR: unknown frame ref(s): {', '.join(unknown)}. Refs look like a12 or a12.f3.", None, []
        region = args.get("region")
        if region is not None:
            if not (isinstance(region, list) and len(region) == 4):
                return "ERROR: region must be [x0, y0, x1, y1] in 0..1.", None, []
            region = [float(v) for v in region]
        items = []
        for r in refs:
            key = (r, tuple(region) if region else None)
            url = self._inspect_cache.get(key)
            shown = r
            if url is None:
                jpeg = self.archive.get(r, region)
                url = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()
                self._inspect_cache[key] = url
                if region:
                    self._crop_refs[key] = self.archive.put_derived(r, jpeg, region)   # keep what the model saw
            if region:
                shown = self._crop_refs[key]
            info = self.archive.info(r)
            pz = info["pose"]
            caption = f"{r} (action a{info['action']}, {info['kind']}, t=+{info['t_sim']:.1f}s"
            if self.proprio:
                caption += f", pos (x={pz['x']:.2f}, y={pz['y']:.2f}) yaw {pz['yaw']:.0f}"
            caption += ")" + (f" region {region}" if region else "")
            items.append((caption, url, shown))
        return f"Returning {len(refs)} frame(s): {', '.join(refs)} - see the images below.", "[inspect]", items

    def _history(self, args: dict) -> str:
        try:
            a, b = int(args.get("from_action")), int(args.get("to_action"))
        except (TypeError, ValueError):
            return "ERROR: history needs integer from_action and to_action."
        if b < a:
            a, b = b, a
        if b - a + 1 > MAX_HISTORY_SPAN:
            return f"ERROR: history covers at most {MAX_HISTORY_SPAN} actions per call."
        lines = []
        for i in range(max(a, 1), min(b, self.n_actions) + 1):
            r = self.records.get(i)
            if r:
                c = (r["content"] or "").strip().replace("\n", " ")
                lines.append(f"a{i} [call {r['call']}] model: {c[:400] or '-'} | {r['result']}")
        return "\n".join(lines) if lines else f"(no actions in a{a}..a{b}; {self.n_actions} actions so far)"

    # ------------------------------------------------------------- bug tools
    def _flag(self, args: dict) -> str:
        desc = str(args.get("description", "")).strip()
        if not desc:
            return "ERROR: flag_bug needs a description."
        evidence = args.get("evidence") or []
        unknown = [r for r in evidence if not self.archive.has(r)]
        if unknown:
            return f"ERROR: evidence refers to unknown frame ref(s): {', '.join(unknown)}."
        try:
            bid = self.ledger.flag(desc, args.get("category", "other"), args.get("status", "suspect"),
                                   evidence, self.pose, self.n_actions, self.sim_t)
        except ValueError as e:
            return f"ERROR: {e}"
        e = self.ledger.get(bid)
        return f"Recorded {bid} [{e['status']}] ({e['category']}): {desc}\nLedger:\n{self.ledger.render()}"

    def _update(self, args: dict) -> str:
        bid = str(args.get("id", ""))
        evidence = args.get("evidence")
        if evidence:
            unknown = [r for r in evidence if not self.archive.has(r)]
            if unknown:
                return f"ERROR: evidence refers to unknown frame ref(s): {', '.join(unknown)}."
        try:
            e = self.ledger.update(bid, description=args.get("description"), status=args.get("status"),
                                   evidence=evidence)
        except KeyError:
            return f"ERROR: unknown bug id {bid}. Known: {', '.join(x['id'] for x in self.ledger.entries) or 'none'}."
        except ValueError as err:
            return f"ERROR: {err}"
        return f"Updated {bid} [{e['status']}]: {e['description']}\nLedger:\n{self.ledger.render()}"
