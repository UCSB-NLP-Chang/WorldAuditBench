"""Environment protocol. The world is frozen between `step` calls (turn-based)."""
from __future__ import annotations

from typing import FrozenSet, Protocol

from agent.types import Action, Observation, ObsConfig

ALL_CAPABILITIES = frozenset({"move", "turn", "look", "interact", "wait"})


class Env(Protocol):
    name: str
    capabilities: FrozenSet[str]
    speed_mps: float        # walking speed, for fixed-tick decision caps
    turn_dps: float         # turning rate

    # Optional action params understood by every adapter (set by the dispatcher in tick mode):
    #   max_sec  - cut the action short after this many simulated seconds
    #   hold_sec - after the action, keep simulated time running until this much has elapsed

    def reset(self, config: str, seed: int, obs: ObsConfig) -> Observation:
        """Load `config`, return the initial observation (action index 0, final frame only)."""

    def step(self, action: Action) -> Observation:
        """Execute one action with sim time advancing only inside it; return the observation.
        The returned Observation has action_index -1 and frames with empty refs: the loop numbers them."""

    def meta(self) -> dict:
        """Renderer / load time / anything worth recording in meta.json."""

    def close(self) -> None: ...


def is_blocked(action: Action, obs: Observation) -> bool:
    """Environment-agnostic obstruction rule (the audit rule from harness/runner.py): a move
    that falls short of its commanded distance by more than max(0.25 m, 10 %) was obstructed,
    unless the shortfall came from a teleport/respawn."""
    if action.kind != "move" or obs.events.get("teleported") or obs.events.get("respawned"):
        return False
    cmd = float(action.params.get("distance_m", 1.5))
    return (cmd - obs.moved) > max(0.25, 0.1 * cmd)
