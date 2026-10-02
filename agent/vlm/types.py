"""Core data types shared by environments, memory, context and the loop.

Units are environment-agnostic: metres, degrees, simulated seconds. `Pose.raw` keeps the
environment-native pose (e.g. three.js `[x, y_up, z]`) for trajectory/score compatibility.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

ACTION_KINDS = ("move", "turn", "look", "interact", "wait")


@dataclass
class Frame:
    ref: str            # "a12" (final frame of action 12) or "a12.f3" (film frame 3); "" until archived
    kind: str           # "film" | "final"
    t_sim: float        # simulated seconds since the action started
    jpeg: bytes
    w: int
    h: int
    path: Optional[Path] = None


@dataclass
class Pose:
    x: float
    y: float
    z: float            # up
    yaw: float          # degrees, environment convention (documented per adapter)
    pitch: float        # degrees, positive = looking down
    raw: dict = field(default_factory=dict)


@dataclass
class Observation:
    action_index: int
    frames: List[Frame]
    pose: Pose
    moved: float        # metres of horizontal displacement during the action
    sim_elapsed: float  # simulated seconds the action took
    events: dict = field(default_factory=dict)   # teleported / respawned / interacted / env_note


@dataclass
class Action:
    kind: str                       # one of ACTION_KINDS
    params: dict = field(default_factory=dict)


@dataclass
class ObsConfig:
    mode: str = "film"              # "final" | "film"
    film_dt: float = 0.5            # sim seconds between film frames
    film_max: int = 8               # film frames per action
    capture_w: int = 960            # archive resolution requested from the env
    capture_h: int = 600
    ctx_final: Tuple[int, int] = (960, 576)   # in-context size of the final frame (multiples of 32)
    ctx_film: Tuple[int, int] = (480, 288)    # in-context size of film frames
    jpeg_q: int = 85
