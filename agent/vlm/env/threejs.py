"""three.js page adapter: drives environments/threejs/runtime/agent.html through the Playwright bridge (agent/vla/bridge.py).

Pose mapping: the page reports [x, y_up, z]; harness Pose uses x, y (= page z, horizontal) and
z (= page y, up). Yaw/pitch are passed through as the page reports them (degrees; turn(+) = right).
Film frames are requested at capture resolution (filmW/filmH URL params, see environments/threejs/runtime/agent.html) so
the archive holds full-resolution frames; the loop downsizes for the context.
"""
from __future__ import annotations

import base64
import io
from typing import Optional

from PIL import Image

from agent.vlm.env.base import ALL_CAPABILITIES
from agent.vlm.types import Action, Frame, Observation, ObsConfig, Pose


def _decode(url: str, kind: str, t: float) -> Frame:
    raw = base64.b64decode(url.split(",", 1)[1])
    w, h = Image.open(io.BytesIO(raw)).size
    return Frame(ref="", kind=kind, t_sim=float(t), jpeg=raw, w=w, h=h)


def _pose(res: dict) -> Pose:
    x, y_up, z = res["pos"]
    return Pose(x=float(x), y=float(z), z=float(y_up), yaw=float(res["yaw"]), pitch=float(res.get("pitch", 0.0)),
                raw={"pos": [x, y_up, z], "yaw": res["yaw"], "pitch": res.get("pitch", 0.0)})


class ThreeJSEnv:
    name = "threejs"
    capabilities = ALL_CAPABILITIES
    speed_mps = 5.2          # environments/threejs/runtime/core.js SPEED
    turn_dps = 120.0         # environments/threejs/runtime/core.js turn/look rate

    def __init__(self, gpu: str = "gl-egl", headless: bool = True, size=(960, 600)):
        from agent.vla.bridge import Bridge
        self.bridge = Bridge(gpu=gpu, headless=headless, size=size)
        self._started = False
        self.obs = ObsConfig()
        self._meta: dict = {}

    def reset(self, config: str, seed: int, obs: ObsConfig) -> Observation:
        self.obs = obs
        if not self._started:
            self.bridge.start()
            self._started = True
        extra: Optional[dict] = None
        if obs.mode == "film":
            extra = {"obs": "film", "filmDt": obs.film_dt, "filmMax": obs.film_max,
                     "filmW": obs.capture_w, "filmH": obs.capture_h}
        self._meta = self.bridge.open_env(config, seed=seed, extra=extra)
        url = self.bridge.page.evaluate(
            "() => document.querySelector('canvas').toDataURL('image/jpeg', 0.85)")
        state = self.bridge.state()
        return Observation(action_index=0, frames=[_decode(url, "final", 0.0)], pose=_pose(state),
                           moved=0.0, sim_elapsed=0.0, events={})

    def step(self, action: Action) -> Observation:
        p = action.params
        if action.kind == "move":
            payload = {"action": "forward" if p.get("direction") != "back" else "back",
                       "dist": float(p.get("distance_m", 1.5))}
        elif action.kind == "turn":
            payload = {"action": "turn", "deg": float(p.get("degrees", 45))}
        elif action.kind == "look":
            payload = {"action": "look", "deg": float(p.get("degrees", 20))}
        elif action.kind == "interact":
            payload = {"action": "interact"}
        elif action.kind == "wait":
            payload = {"action": "wait", "ms": int(round(float(p.get("seconds", 1.0)) * 1000))}
        else:
            raise ValueError(f"unknown action kind {action.kind}")
        if p.get("max_sec") is not None:
            payload["maxSec"] = float(p["max_sec"])
        if p.get("hold_sec") is not None:
            payload["holdSec"] = float(p["hold_sec"])
        res = self.bridge.act(payload)
        frames = [_decode(f["url"], "film", f["t"]) for f in (res.get("film") or [])]
        frames.append(_decode(res["frames"][-1], "final", res["frameT"][-1] if res.get("frameT") else res["simElapsed"]))
        events = {"teleported": bool(res.get("teleported")), "respawned": bool(res.get("respawned")),
                  "interacted": bool(res.get("interacted"))}
        return Observation(action_index=-1, frames=frames, pose=_pose(res), moved=float(res["moved"]),
                           sim_elapsed=float(res.get("simElapsed", 0.0)), events=events)

    def meta(self) -> dict:
        return dict(self._meta, page_errors=list(self.bridge.page_errors),
                    console_errors=self.bridge.console_errors()[:20])

    def targets(self) -> dict:
        return self.bridge.targets()

    def close(self) -> None:
        if self._started:
            self.bridge.close()
            self._started = False
