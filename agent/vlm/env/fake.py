"""Deterministic synthetic environment for tests: flat plane, optional invisible wall at x = wall_x.
Frames are PIL drawings of the pose, so every distinct pose gives a distinct JPEG."""
from __future__ import annotations

import io
import math

from PIL import Image, ImageDraw

from agent.vlm.env.base import ALL_CAPABILITIES
from agent.vlm.types import Action, Frame, Observation, ObsConfig, Pose

SPEED = 5.2          # m/s, same as environments/threejs/runtime/core.js
TURN_RATE = 120.0    # deg/s
EYE = 1.7


class FakeEnv:
    name = "fake"
    speed_mps = SPEED
    turn_dps = TURN_RATE

    def __init__(self, wall_x=None, w=960, h=600, capabilities=None):
        self.wall_x = wall_x
        self.w, self.h = w, h
        self.capabilities = frozenset(capabilities) if capabilities else ALL_CAPABILITIES
        self.obs = ObsConfig()
        self.x = self.y = 0.0
        self.yaw = self.pitch = 0.0
        self.sim_t = 0.0

    # ------------------------------------------------------------------ api
    def reset(self, config: str, seed: int, obs: ObsConfig) -> Observation:
        self.obs = obs
        self.x = self.y = 0.0
        self.yaw = self.pitch = 0.0
        self.sim_t = 0.0
        return Observation(action_index=0, frames=[self._frame("final", 0.0)], pose=self._pose(),
                           moved=0.0, sim_elapsed=0.0, events={})

    def step(self, action: Action) -> Observation:
        x0, y0 = self.x, self.y
        p = action.params
        max_sec, hold_sec = p.get("max_sec"), p.get("hold_sec")
        cap = (lambda s: min(s, float(max_sec))) if max_sec is not None else (lambda s: s)
        if action.kind == "move":
            dist = min(max(float(p.get("distance_m", 1.5)), 0.3), 4.0)
            sign = -1.0 if p.get("direction") == "back" else 1.0
            elapsed = cap(dist / SPEED)
            dist = SPEED * elapsed                          # cut short by max_sec
            dx = math.cos(math.radians(self.yaw)) * dist * sign
            dy = math.sin(math.radians(self.yaw)) * dist * sign
            nx = self.x + dx
            if self.wall_x is not None and self.x <= self.wall_x < nx:
                frac = (self.wall_x - self.x) / dx if dx else 0.0
                nx, dy = self.wall_x, dy * frac
            self.x, self.y = nx, self.y + dy
        elif action.kind == "turn":
            deg = float(p.get("degrees", 45))
            self.yaw = (self.yaw + deg) % 360.0
            elapsed = cap(abs(deg) / TURN_RATE)
        elif action.kind == "look":
            deg = float(p.get("degrees", 20))
            self.pitch = max(-75.0, min(75.0, self.pitch + deg))
            elapsed = cap(abs(deg) / TURN_RATE)
        elif action.kind == "interact":
            elapsed = cap(2.8)
        elif action.kind == "wait":
            elapsed = cap(min(max(float(p.get("seconds", 1.0)), 0.1), 5.0))
        else:
            raise ValueError(f"unknown action kind {action.kind}")
        if hold_sec is not None:
            elapsed = max(elapsed, float(hold_sec))

        frames = []
        if self.obs.mode == "film":
            t = 0.0
            while t <= elapsed + 1e-9 and len(frames) < self.obs.film_max:
                frames.append(self._frame("film", t))
                t += self.obs.film_dt
        frames.append(self._frame("final", elapsed))
        self.sim_t += elapsed
        moved = math.hypot(self.x - x0, self.y - y0)
        return Observation(action_index=-1, frames=frames, pose=self._pose(), moved=round(moved, 4),
                           sim_elapsed=round(elapsed, 3),
                           events={"teleported": False, "respawned": False, "interacted": False})

    def meta(self) -> dict:
        return {"renderer": "fake", "load_time_s": 0.0}

    def close(self) -> None:
        pass

    # ------------------------------------------------------------- internals
    def _pose(self) -> Pose:
        return Pose(x=round(self.x, 3), y=round(self.y, 3), z=EYE, yaw=round(self.yaw, 1),
                    pitch=round(self.pitch, 1),
                    raw={"pos": [round(self.x, 3), EYE, round(self.y, 3)], "yaw": round(self.yaw, 1),
                         "pitch": round(self.pitch, 1)})

    def _frame(self, kind: str, t: float) -> Frame:
        hue = int(self.yaw) % 360
        color = (60 + hue // 3, 90 + int(abs(self.x) * 10) % 100, 120 + int(t * 40) % 100)
        img = Image.new("RGB", (self.w, self.h), color)
        d = ImageDraw.Draw(img)
        d.text((20, 20), f"x={self.x:.2f} y={self.y:.2f} yaw={self.yaw:.0f} pitch={self.pitch:.0f}",
               fill=(255, 255, 255))
        d.text((20, 40), f"kind={kind} t=+{t:.2f}s sim={self.sim_t + t:.2f}", fill=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=self.obs.jpeg_q)
        return Frame(ref="", kind=kind, t_sim=round(t, 3), jpeg=buf.getvalue(), w=self.w, h=self.h)
