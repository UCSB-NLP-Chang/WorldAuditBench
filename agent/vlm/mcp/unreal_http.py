"""Adapter for this repo's /reset and /step API, not the public review website."""
import base64
import io
import math
import uuid

from PIL import Image
import requests
from agent.vlm.types import Frame, Observation, Pose


class UnrealHTTP:
    name = "unreal-http"
    capabilities = frozenset({"move", "turn", "look", "interact", "wait"})
    speed_mps = 2.2
    turn_dps = 90.0

    def __init__(self, url):
        self.url = url.rstrip("/")
        self.session = requests.Session()
        self.episode = None
        self.sim_time = None
        self.finished = False
        self.failed = False
        self.identity = {}

    def _call(self, endpoint, body):
        # Never retry an uncertain mutation with a new request_id.
        try:
            response = self.session.post(self.url + endpoint, json=body, timeout=(10, 200))
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as e:
            self.failed = True
            raise RuntimeError(f"Unreal request failed ({endpoint}); episode stopped: {type(e).__name__}") from e

    def reset(self, config, seed, obs):
        self.obs = obs
        response = self.session.get(self.url + "/health", timeout=(10, 15))
        response.raise_for_status()
        health = response.json()
        self.identity = {k: health[k] for k in ["task_id", "build_sha256", "sampling_interval_seconds", "startup_rng_seeded"] if k in health}
        if health.get("task_id", config) != config:
            raise ValueError("Environment endpoint is assigned to another task")
        if health.get("episode_started"):
            raise ValueError("Endpoint already has an episode; start a fresh server for this model")
        data = self._call("/reset", {"request_id": uuid.uuid4().hex, "task_id": config, "seed": seed})
        self.episode = data["episode_id"]
        if data.get("task_id") not in (None, config):
            self.failed = True
            raise ValueError("Backend returned a different task")
        return self._convert(data, initial=True)

    def _frame(self, rgb, kind, elapsed):
        raw = base64.b64decode(rgb["base64"], validate=True)
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=self.obs.jpeg_q)
        return Frame("", kind, elapsed, buf.getvalue(), *img.size)

    def _convert(self, data, initial=False):
        if data.get("paused") is not True:
            self.failed = True
            raise ValueError("Expected a paused Unreal observation")
        now = float(data["simulation_time"])
        elapsed = 0.0 if initial else now - self.sim_time
        if not math.isfinite(elapsed) or elapsed < -0.001:
            self.failed = True
            raise ValueError("Invalid simulation clock")
        previous = now if initial else self.sim_time
        self.sim_time = now
        frames = []
        if not initial and self.obs.mode == "film":
            for source in data.get("frames", [])[:self.obs.film_max]:
                # Native captures record absolute simulation_time, not wall time.
                t = float(source["simulation_time"]) - previous
                frames.append(self._frame(source["rgb"], "film", max(0.0, t)))
        frames.append(self._frame(data["rgb"], "final", elapsed))
        pos = data["position_cm"]
        if len(pos) != 3 or not all(math.isfinite(float(x)) for x in pos):
            self.failed = True
            raise ValueError("Invalid position in observation")
        pose = Pose(*(float(v) / 100 for v in pos), float(data["yaw_degree"]),
                    float(data["look_degree"]), raw={"position_cm": pos})
        note = data.get("result", "")
        clearance = data.get("boundary_clearance_cm")
        if clearance is not None and float(clearance) < 3:
            note += "; Task boundary reached: movement is limited to the exploration area."
        return Observation(0 if initial else -1, frames, pose,
                           float(data.get("actual_distance_cm", 0)) / 100, elapsed,
                           {"env_note": note})

    def step(self, action):
        if self.failed or self.finished:
            raise RuntimeError("Episode is no longer available")
        p = action.params
        if action.kind == "move":
            native = {"name": "move_up" if p["direction"] == "forward" else "move_down",
                      "distance": round(p["distance_m"] * 100)}
        elif action.kind in {"turn", "look"}:
            native = {"name": action.kind, "degree": round(p["degrees"])}
        elif action.kind == "wait":
            native = {"name": "idle", "time": f"{p['seconds']:g}s"}
        elif action.kind == "interact":
            native = {"name": "interact"}
        else:
            raise ValueError("Unsupported action")
        data = self._call("/step", {"episode_id": self.episode,
                                  "request_id": uuid.uuid4().hex, "action": native})
        try:
            return self._convert(data)
        except Exception:
            self.failed = True
            raise

    def meta(self):
        return {"backend": self.name, "endpoint": self.url,
                "sampling": "native 0.5 simulated seconds", "seed_verified": False,
                "note": "Pinned legacy binaries accept seed slot 0 but do not seed startup RNG.",
                **self.identity}

    def close(self):
        # Finish only our own episode. Never shut down somebody else's server/process.
        try:
            if self.episode and not self.finished and not self.failed:
                self._call("/step", {"episode_id": self.episode,
                                    "request_id": uuid.uuid4().hex, "action": {"name": "done"}})
                self.finished = True
        finally:
            self.session.close()
