"""Bug ledger: flagged bugs have ids, can be revised or retracted, and carry optional evidence
frame refs. Scoring reads the final non-retracted set; every change is logged to bugs.jsonl."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import List, Optional

from agent.vlm.types import Pose

CATEGORIES = ("geometry", "collision", "visual", "state", "semantic", "other")
STATUSES = ("suspect", "confirmed", "retracted")


def _native_pos(pose: Pose) -> list:
    return list(pose.raw.get("pos", [pose.x, pose.z, pose.y]))


class BugLedger:
    def __init__(self, run_dir):
        self.path = Path(run_dir) / "bugs.jsonl"
        self.entries: List[dict] = []
        self._events: List[dict] = []

    # ------------------------------------------------------------------ write
    def flag(self, description: str, category: str, status: str, evidence: Optional[List[str]],
             pose: Pose, action_index: int, sim_t: float) -> str:
        if category not in CATEGORIES:
            raise ValueError(f"category must be one of {CATEGORIES}")
        if status not in ("suspect", "confirmed"):
            raise ValueError("status must be 'suspect' or 'confirmed'")
        bid = f"b{len(self.entries) + 1}"
        entry = dict(id=bid, description=description, category=category, status=status,
                     evidence=list(evidence or []), pos=_native_pos(pose), action=action_index,
                     simT=sim_t)
        self.entries.append(entry)
        self._log("flag", entry)
        return bid

    def update(self, bid: str, description: Optional[str] = None, status: Optional[str] = None,
               evidence: Optional[List[str]] = None, pose: Optional[Pose] = None,
               action_index: Optional[int] = None, sim_t: Optional[float] = None) -> dict:
        entry = self.get(bid)                       # KeyError for unknown ids
        if entry["status"] == "retracted":
            raise ValueError(f"{bid} is retracted and cannot be changed")
        if status is not None and status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        if description is not None:
            entry["description"] = description
        if status is not None:
            entry["status"] = status
        if evidence is not None:
            entry["evidence"] = list(evidence)
        if pose is not None:
            entry["pos"] = _native_pos(pose)
        if action_index is not None:
            entry["action"] = action_index
        if sim_t is not None:
            entry["simT"] = sim_t
        self._log("update", entry)
        return entry

    def _log(self, event: str, entry: dict) -> None:
        row = dict(event=event, **entry)
        self._events.append(row)
        with open(self.path, "a") as f:
            f.write(json.dumps(row) + "\n")

    # ------------------------------------------------------------------- read
    def get(self, bid: str) -> dict:
        for e in self.entries:
            if e["id"] == bid:
                return e
        raise KeyError(bid)

    def active(self) -> List[dict]:
        return [e for e in self.entries if e["status"] != "retracted"]

    def history(self) -> List[dict]:
        return copy.deepcopy(self._events)

    def export(self) -> List[dict]:
        """Scoring-compatible flags: the old {pos, note, simT} shape plus ledger fields."""
        return [dict(pos=e["pos"], note=e["description"], simT=e["simT"], id=e["id"],
                     status=e["status"], category=e["category"], evidence=e["evidence"],
                     action=e["action"]) for e in self.active()]

    def render(self) -> str:
        act = self.active()
        if not act:
            return "(no bugs flagged)"
        lines = []
        for e in act:
            ev = ", ".join(e["evidence"]) if e["evidence"] else "-"
            lines.append(f"{e['id']} [{e['status']}] ({e['category']}) at a{e['action']}: "
                         f"{e['description']} | evidence: {ev}")
        return "\n".join(lines)
