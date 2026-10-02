"""VLA-recording playback environment for the native MCP harness (the VLA arm's audit stage).

The recording is an episode of agent/vla/vla_explore.py (three.js) or agent/vla/vla_ue.py (Unreal): meta.json, poses.jsonl
(one line per 50 ms tick) and one full frame every 0.5 s of simulated time (f<tick>.jpg, listed in meta "frames").  The
model does not control the camera.  Its only environment action is the playback of a segment: the MCP server exposes it
as `play(from_s, to_s)` and translates it into a `seek` plus an upstream `wait` action, so the pinned upstream
dispatcher, archive, ledger, notes, inspect and history are used unchanged and every frame keeps an archive ref
(a<N>, a<N>.f<k>) the model can inspect, crop and cite as evidence exactly like in the embodied setting.

Observation of a play(from_s, to_s): film frames every 0.5 s after from_s (kind "film", at most film_max) and the frame
at to_s (kind "final"); pose = the explorer's recorded pose at to_s, moved = the explorer's path length over the segment,
env_note = the recording times plus what the explorer's controller was pressing (forward / back held seconds), which is
the playback counterpart of the commanded distance the embodied agent sees next to its own displacement.

reset() returns frame 0 as a0 plus a preview strip (film frames every `preview_every` s) so the model can decide where
to look first; segments may be played in any order and repeatedly.
"""
from __future__ import annotations

import json
from pathlib import Path

from agent.vlm.types import Action, Frame, Observation, ObsConfig, Pose

FORWARD_KEYS = {"KeyW", "w"}
BACK_KEYS = {"KeyS", "s"}


class ReplayEnv:
    name = "vla-replay"
    capabilities = frozenset({"wait"})
    speed_mps = 2.2
    turn_dps = 90.0
    MAX_SEGMENT = 4.0          # seconds per play: 7 film frames + the final frame cover it without gaps at film_max 8

    def __init__(self, replay_dir, preview_every=5.0, mode="play"):
        """mode "play": the model plays segments (play tool, 40 actions).  mode "all": observe delivers the whole recording
        at once as film frames a0.f0.. (every recorded frame, film resolution) plus the explorer's track as text - the
        context an embodied agent would have accumulated before flagging - and there is no environment action at all;
        the model only inspects, takes notes, flags and finishes."""
        if mode not in {"play", "all"}:
            raise ValueError("replay mode must be play or all")
        self.mode = mode
        self.capabilities = frozenset({"wait"}) if mode == "play" else frozenset()
        self.dir = Path(replay_dir)
        self.recording = json.loads((self.dir / "meta.json").read_text())
        if self.recording.get("kind") not in {"vla_explore", "vla_explore_ue"}:
            raise ValueError("Not a VLA recording (meta.kind)")
        self.engine = "ue" if self.recording["kind"] == "vla_explore_ue" else "threejs"
        self.dt = self.recording["dt_ms"] / 1000.0                       # tick length, 0.05 s
        self.record_every = int(self.recording["record_every"])          # ticks per frame, 10
        self.frame_dt = self.dt * self.record_every                 # 0.5 s
        self.frames = list(self.recording["frames"])
        missing = [f for f in self.frames if not (self.dir / f).exists()]
        if missing:
            raise ValueError(f"{len(missing)} recorded frames missing (restore them with scripts/tools/vla_frames_from_video.py)")
        self.poses = [json.loads(l) for l in (self.dir / "poses.jsonl").read_text().splitlines() if l.strip()]
        self.by_tick = {p["t"]: p for p in self.poses}
        self.last_t = round((len(self.frames) - 1) * self.frame_dt, 3)   # 59.5 s for 120 frames
        self.preview_every = preview_every
        self.obs = ObsConfig()
        self.playhead = 0.0
        self.failed = False
        self.n_plays = 0
        self.played = []                                             # [from, to] per play, for meta.json

    # ------------------------------------------------------------ recording
    def frame_index(self, t):
        k = int(round(t / self.frame_dt))
        if abs(k * self.frame_dt - t) > 1e-6 or not 0 <= k < len(self.frames):
            raise ValueError(f"no frame at t={t:g}s (frames every {self.frame_dt:g}s from 0 to {self.last_t:g}s)")
        return k

    def _frame(self, t, kind, t_sim):
        from PIL import Image
        import io
        path = self.dir / self.frames[self.frame_index(t)]
        raw = path.read_bytes()
        w, h = Image.open(io.BytesIO(raw)).size
        return Frame("", kind, t_sim, raw, w, h)

    def _tick(self, t):
        return min(int(round(t / self.dt)), len(self.poses) - 1)

    def pose_at(self, t):
        p = self.by_tick.get(self._tick(t)) or self.poses[self._tick(t)]
        if self.engine == "ue":
            x, y, z = (float(v) / 100.0 for v in p["pos_cm"])
            return Pose(x=x, y=y, z=z, yaw=float(p["yaw"]), pitch=float(p.get("pitch", 0.0)),
                        raw={"position_cm": p["pos_cm"], "tick": p["t"]})
        x, y_up, z = p["pos"]
        return Pose(x=float(x), y=float(z), z=float(y_up), yaw=float(p["yaw"]), pitch=float(p.get("pitch", 0.0)),
                    raw={"pos": p["pos"], "tick": p["t"]})

    def segment_stats(self, t0, t1):
        """Path length (m) and controller input over the ticks in (t0, t1]."""
        a, b = self._tick(t0), self._tick(t1)
        moved = fwd = back = 0.0
        respawned = False
        for p in self.poses[a + 1:b + 1]:
            moved += float(p.get("moved_cm", 0.0)) / 100.0 if self.engine == "ue" else float(p.get("moved", 0.0))
            keys = set(p.get("keys") or [])
            fwd += self.dt if keys & FORWARD_KEYS else 0.0
            back += self.dt if keys & BACK_KEYS else 0.0
            respawned = respawned or bool(p.get("respawned"))
        return moved, fwd, back, respawned

    # ------------------------------------------------------------------ api
    def reset(self, config, seed, obs):
        self.obs = obs
        self.playhead = 0.0
        frames = []
        step = self.frame_dt if self.mode == "all" else self.preview_every
        t = step
        while t <= self.last_t + 1e-6:
            frames.append(self._frame(round(t, 3), "film", round(t, 3)))
            t += step
        frames.append(self._frame(0.0, "final", 0.0))
        note = (f"recording 0.0-{self.last_t:g} s, every recorded frame ({self.frame_dt:g} s apart) archived, inline every {self.preview_every:g} s" if self.mode == "all"
                else f"recording 0.0-{self.last_t:g} s, frames every {self.frame_dt:g} s; preview frames every {self.preview_every:g} s")
        return Observation(action_index=0, frames=frames, pose=self.pose_at(0.0), moved=0.0, sim_elapsed=0.0, events={"env_note": note})

    def track_text(self, every=None):
        """The explorer's track, one line per recorded frame (or every `every` seconds): recording time, frame ref, pose,
        path length since the previous line and the controller input - the playback counterpart of the per-action pose
        and displacement lines an embodied agent reads."""
        every = every or self.frame_dt
        lines = [f"Explorer track (pos in metres, yaw/pitch in degrees, moved = path length since the previous line, "
                 f"input = seconds the explorer held forward / back):"]
        t, prev = 0.0, 0.0
        k = 0
        while t <= self.last_t + 1e-6:
            p = self.pose_at(t)
            moved, fwd, back, resp = self.segment_stats(prev, t) if t > 0 else (0.0, 0.0, 0.0, False)
            ref = "a0" if t == 0 else f"a0.f{self.frame_index(t) - 1}"
            lines.append(f"t={t:.1f}s {ref}: pos ({p.x:.2f}, {p.y:.2f}) yaw {p.yaw:.0f} pitch {p.pitch:.0f} | moved {moved:.2f} m | "
                         f"input fwd {fwd:.1f} s back {back:.1f} s" + (" RESPAWNED" if resp else ""))
            prev, t = t, round(t + every, 3)
            k += 1
        return "\n".join(lines)

    def inline(self, ref):
        """mode all: whether an archived start frame a0.f<k> is delivered inline with observe (every preview_every seconds);
        mode play: every preview frame is delivered."""
        if self.mode != "all" or not ref.startswith("a0.f"):
            return True
        t = (int(ref[4:].split("#")[0]) + 1) * self.frame_dt
        q = t / self.preview_every
        return abs(q - round(q)) < 1e-6

    def inline_size(self, full, budget_bytes=4_000_000, quality=85):
        """mode all: the largest context size (multiples of 32, from `full` down to 480x288) at which the inline frames'
        JPEG bytes fit the budget; estimated on five sample frames."""
        import io
        from PIL import Image
        refs = [f"a0.f{k}" for k in range(len(self.frames) - 1)]
        inline = [k for k, r in enumerate(refs) if self.inline(r)]
        if not inline:
            return full
        sample = [self.frames[k + 1] for k in inline[:: max(1, len(inline) // 5)]][:5]
        sizes = [full, (800, 480), (640, 384), (480, 288)]
        for size in sizes:
            total = 0
            for name in sample:
                img = Image.open(self.dir / name).convert("RGB").resize(size, Image.LANCZOS)
                buf = io.BytesIO(); img.save(buf, "JPEG", quality=quality); total += len(buf.getvalue())
            if total / len(sample) * len(inline) <= budget_bytes:
                return size
        return sizes[-1]

    def seek(self, t):
        self.frame_index(t)
        self.playhead = round(float(t), 3)

    def step(self, action: Action) -> Observation:
        if action.kind != "wait" or self.mode != "play":
            raise ValueError("The recording only supports playback")
        t0 = self.playhead
        t1 = round(t0 + float(action.params.get("seconds", 1.0)), 3)
        if t1 > self.last_t + 1e-6:
            raise ValueError(f"the recording ends at t={self.last_t:g}s")
        if t1 - t0 > self.MAX_SEGMENT + 1e-6:
            raise ValueError(f"a segment is at most {self.MAX_SEGMENT:g} s long")
        self.frame_index(t0); self.frame_index(t1)
        frames = []
        t = round(t0 + self.frame_dt, 3)
        while t < t1 - 1e-6 and len(frames) < self.obs.film_max:
            frames.append(self._frame(t, "film", round(t - t0, 3)))
            t = round(t + self.frame_dt, 3)
        frames.append(self._frame(t1, "final", round(t1 - t0, 3)))
        moved, fwd, back, respawned = self.segment_stats(t0, t1)
        note = f"recording {t0:.1f}-{t1:.1f} s | explorer input: forward {fwd:.1f} s, back {back:.1f} s"
        self.playhead = t1
        self.n_plays += 1
        self.played.append([t0, t1])
        return Observation(action_index=-1, frames=frames, pose=self.pose_at(t1), moved=moved,
                           sim_elapsed=round(t1 - t0, 3), events={"env_note": note, "respawned": respawned})

    def meta(self):
        played = sorted(self.played)
        covered = set()
        for a, b in played:
            k = a
            while k <= b + 1e-6:
                covered.add(round(k, 1)); k = round(k + self.frame_dt, 3)
        return {"backend": self.name, "mode": self.mode, "recording": str(self.dir), "engine": self.engine,
                "explorer": self.recording.get("model"), "explorer_text": self.recording.get("text"),
                "recording_seconds": self.recording.get("sim_seconds"), "frames": len(self.frames),
                "frame_source": "restored from video.mp4" if (self.dir / "frames.restored.json").exists() else "recorded jpeg",
                "plays": len(played), "played_segments": played,
                "frames_covered": len(covered), "frames_coverage": round(len(covered) / len(self.frames), 3)}

    def close(self):
        pass
