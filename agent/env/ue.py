"""Unreal Engine adapter: HTTP client for `simworld_server` (the SimWorld environment service).

ASSUMED SERVER CONTRACT - this is the specification for the turn-based extension of
simworld_server (to be implemented there; the current server runs the world in real time and
waits wall-clock `settle` seconds per action):

  POST /envs                       {agents: 1, label, map_path?}          -> {env_id, ...}
  POST /envs/{env}/reset           {agent_id, observe}                    -> {observations: [obs]}
  POST /envs/{env}/agents/{a}/step {action, observe, clock: "tick", film?} -> obs
  DELETE /envs/{env}

  clock: "tick"   The world is paused between steps (UnrealCV `vset /action/game/pause`); the
                  action is advanced with `vset /action/tick` for exactly its simulated duration
                  (move: distance / speed; turn: its duration; wait: `duration` seconds), then the
                  observation is taken while still paused.
  film: {dt, max_frames}   While ticking, capture the agent camera every `dt` simulated seconds
                  (at most max_frames); returned as obs.frames = [{t, rgb}] (base64 JPEG at the
                  requested observe width/height). Omitted -> no strip.
  hold: s         Optional. After the action completes, keep ticking (agent idle) until `s`
                  simulated seconds have elapsed since the step started (fixed-tick decisions).
  obs additions:  moved (cm, horizontal displacement during the step), sim_elapsed (s).
  Existing fields used: position [cm], rotation [pitch, yaw, roll] (yaw increases clockwise),
                  rgb (base64 JPEG of the final view), action_ok, action_message.

Units: the harness works in metres; positions are converted from centimetres here. Capabilities
are move / turn / wait (no look or interact in SimWorld's low-level action space).
"""
from __future__ import annotations

import base64
import io
import math
import os
import time
from typing import Optional

import requests
from PIL import Image

from agent.types import Action, Frame, Observation, ObsConfig, Pose


class UEEnv:
    name = "ue"
    capabilities = frozenset({"move", "turn", "wait"})
    turn_dps = 120.0

    def __init__(self, base_url: Optional[str] = None, env_id: Optional[str] = None, agent_id: str = "agent-0",
                 speed_cms: float = 200.0, view: str = "first", timeout: float = 300.0,
                 label: str = "agent-harness"):
        self.base_url = (base_url or os.environ.get("SIMWORLD_URL", "http://localhost:8000")).rstrip("/")
        self.env_id, self.agent_id = env_id, agent_id
        self.speed_cms, self.view, self.timeout, self.label = speed_cms, view, timeout, label
        self._created = False
        self._session = requests.Session()
        self.obs = ObsConfig()
        self._prev_pos = None
        self._meta: dict = {}

    # ------------------------------------------------------------------ http
    def _call(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        r = self._session.request(method, self.base_url + path, json=body, timeout=self.timeout)
        if not r.ok:
            try:
                detail = r.json().get("detail", r.text)
            except ValueError:
                detail = r.text
            raise RuntimeError(f"{method} {path} -> {r.status_code}: {detail}")
        return r.json()

    @property
    def speed_mps(self) -> float:
        return self.speed_cms / 100.0

    def _observe_spec(self) -> dict:
        return {"rgb": True, "state": True, "depth": False, "mask": False, "view": self.view,
                "width": self.obs.capture_w, "height": self.obs.capture_h,
                "encoding": "jpeg", "jpeg_quality": self.obs.jpeg_q}

    # ------------------------------------------------------------------- api
    def reset(self, config: Optional[str], seed: int, obs: ObsConfig) -> Observation:
        self.obs = obs
        t0 = time.time()
        if self.env_id is None:
            body = {"agents": 1, "label": self.label}
            if config and config.startswith("/Game"):
                body["map_path"] = config
            info = self._call("POST", "/envs", body)
            self.env_id, self._created = info["env_id"], True
            self._meta["map_path"] = info.get("map_path")
        res = self._call("POST", f"/envs/{self.env_id}/reset",
                         {"agent_id": self.agent_id, "observe": self._observe_spec()})
        self._meta.update(renderer="unreal", env_id=self.env_id, load_time_s=round(time.time() - t0, 2))
        o = res["observations"][0]
        self._prev_pos = o["position"]
        return Observation(action_index=0, frames=[self._frame(o["rgb"], "final", 0.0)], pose=self._pose(o),
                           moved=0.0, sim_elapsed=0.0, events={})

    def step(self, action: Action) -> Observation:
        p = action.params
        max_sec = p.get("max_sec")
        cap = (lambda s: min(s, float(max_sec))) if max_sec is not None else (lambda s: s)
        if action.kind == "move":
            dist_cm = float(p.get("distance_m", 1.5)) * 100.0
            a = {"choice": 1, "duration": round(cap(dist_cm / self.speed_cms), 3),
                 "direction": 1 if p.get("direction") == "back" else 0}
            nominal = a["duration"]
        elif action.kind == "turn":
            deg = float(p.get("degrees", 45))
            a = {"choice": 2, "angle": abs(deg), "clockwise": deg >= 0,
                 "duration": round(cap(abs(deg) / self.turn_dps), 3)}
            nominal = a["duration"]
        elif action.kind == "wait":
            a = {"choice": 0, "duration": round(cap(float(p.get("seconds", 1.0))), 3)}
            nominal = a["duration"]
        else:
            raise ValueError(f"UE adapter does not support action kind {action.kind}")
        body = {"action": a, "observe": self._observe_spec(), "clock": "tick"}
        if p.get("hold_sec") is not None:
            body["hold"] = float(p["hold_sec"])
        if self.obs.mode == "film":
            body["film"] = {"dt": self.obs.film_dt, "max_frames": self.obs.film_max}
        o = self._call("POST", f"/envs/{self.env_id}/agents/{self.agent_id}/step", body)
        frames = [self._frame(f["rgb"], "film", f["t"]) for f in (o.get("frames") or [])]
        elapsed = float(o.get("sim_elapsed", nominal))
        frames.append(self._frame(o["rgb"], "final", elapsed))
        if "moved" in o:
            moved = float(o["moved"]) / 100.0
        else:
            moved = math.hypot(o["position"][0] - self._prev_pos[0], o["position"][1] - self._prev_pos[1]) / 100.0
        self._prev_pos = o["position"]
        events = {"teleported": False, "respawned": False, "interacted": False}
        if not o.get("action_ok", True):
            events["env_note"] = f"action rejected: {o.get('action_message')}"
        return Observation(action_index=-1, frames=frames, pose=self._pose(o), moved=round(moved, 4),
                           sim_elapsed=round(elapsed, 3), events=events)

    def meta(self) -> dict:
        return dict(self._meta)

    def close(self) -> None:
        if self._created and self.env_id:
            try:
                self._call("DELETE", f"/envs/{self.env_id}")
            finally:
                self._created = False

    # ------------------------------------------------------------- internals
    @staticmethod
    def _pose(o: dict) -> Pose:
        x, y, z = o["position"]
        pitch, yaw, roll = o.get("rotation", [0.0, 0.0, 0.0])
        return Pose(x=x / 100.0, y=y / 100.0, z=z / 100.0, yaw=float(yaw), pitch=float(pitch),
                    raw={"position": list(o["position"]), "rotation": [pitch, yaw, roll]})

    @staticmethod
    def _frame(b64: str, kind: str, t: float) -> Frame:
        raw = base64.b64decode(b64)
        w, h = Image.open(io.BytesIO(raw)).size
        return Frame(ref="", kind=kind, t_sim=float(t), jpeg=raw, w=w, h=h)
