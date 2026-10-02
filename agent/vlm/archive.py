"""Lossless frame archive: every frame the environment returns is written to disk at capture
resolution and indexed by action / frame number, so the model can bring any of them back later.

Refs: "a12" = final frame of action 12, "a12.f3" = film frame 3 of action 12, "a0" = start view;
"a12#c2" = the second crop derived from a12 (what an inspect with a region actually showed the model).
Files: frames/a012.jpg, frames/a012_f03.jpg, frames/a012_c02.jpg; frames/index.jsonl holds one line per frame.
"""
from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image

from agent.vlm.types import Observation


def _mult32(v: int) -> int:
    return max(32, int(round(v / 32)) * 32)


class FrameArchive:
    def __init__(self, run_dir):
        self.dir = Path(run_dir) / "frames"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.dir / "index.jsonl"
        self.index: Dict[str, dict] = {}
        self._ctx_cache: Dict[Tuple[str, Tuple[int, int]], str] = {}
        if self.index_path.exists():
            for line in self.index_path.read_text().splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.index[row["ref"]] = row

    # ------------------------------------------------------------------ write
    def put(self, obs: Observation) -> None:
        """Assign refs and paths to obs.frames, write the JPEGs and index rows."""
        a = obs.action_index
        n_film = 0
        with open(self.index_path, "a") as idx:
            for fr in obs.frames:
                if fr.kind == "film":
                    fr.ref = f"a{a}.f{n_film}"
                    fname = f"a{a:03d}_f{n_film:02d}.jpg"
                    n_film += 1
                else:
                    fr.ref = f"a{a}"
                    fname = f"a{a:03d}.jpg"
                fr.path = self.dir / fname
                fr.path.write_bytes(fr.jpeg)
                row = dict(ref=fr.ref, file=fname, kind=fr.kind, t_sim=fr.t_sim, action=a,
                           w=fr.w, h=fr.h,
                           pose=dict(x=obs.pose.x, y=obs.pose.y, z=obs.pose.z,
                                     yaw=obs.pose.yaw, pitch=obs.pose.pitch))
                self.index[fr.ref] = row
                idx.write(json.dumps(row) + "\n")

    # ------------------------------------------------------------------- read
    def has(self, ref: str) -> bool:
        return ref in self.index

    def info(self, ref: str) -> dict:
        return self.index[ref]

    def refs_for(self, action_index: int) -> List[str]:
        return [r for r, row in self.index.items() if row["action"] == action_index and row["kind"] != "crop"]

    def put_derived(self, parent: str, jpeg: bytes, region: List[float]) -> str:
        """Archive a crop the model was shown (inspect with a region) as `<parent>#c<n>`; the same
        parent+region returns the existing ref."""
        for r, row in self.index.items():
            if row.get("parent") == parent and row.get("region") == list(region):
                return r
        src = self.index[parent]
        n = 1 + sum(1 for row in self.index.values() if row.get("parent") == parent)
        ref = f"{parent}#c{n}"
        fname = f"{Path(src['file']).stem}_c{n:02d}.jpg"
        (self.dir / fname).write_bytes(jpeg)
        w, h = Image.open(io.BytesIO(jpeg)).size
        row = dict(ref=ref, file=fname, kind="crop", parent=parent, region=list(region), t_sim=src["t_sim"],
                   action=src["action"], w=w, h=h, pose=src["pose"])
        self.index[ref] = row
        with open(self.index_path, "a") as idx:
            idx.write(json.dumps(row) + "\n")
        return ref

    def get(self, ref: str, region: Optional[List[float]] = None, max_side: int = 960) -> bytes:
        """JPEG bytes of a frame. Without a region the original bytes are returned untouched.
        `region` = [x0, y0, x1, y1] in 0..1; the crop is scaled so its longer side is `max_side`
        and both sides are multiples of 32 (deterministic image-token counts)."""
        row = self.index[ref]                       # KeyError for unknown refs
        raw = (self.dir / row["file"]).read_bytes()
        if not region:
            return raw
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        x0, y0, x1, y1 = region
        x0, x1 = sorted((min(max(x0, 0.0), 1.0), min(max(x1, 0.0), 1.0)))
        y0, y1 = sorted((min(max(y0, 0.0), 1.0), min(max(y1, 0.0), 1.0)))
        box = (int(x0 * img.width), int(y0 * img.height),
               max(int(x1 * img.width), int(x0 * img.width) + 1),
               max(int(y1 * img.height), int(y0 * img.height) + 1))
        crop = img.crop(box)
        scale = max_side / max(crop.width, crop.height)
        w, h = _mult32(int(crop.width * scale)), _mult32(int(crop.height * scale))
        crop = crop.resize((w, h), Image.LANCZOS)
        return _encode(crop)

    def ctx_image(self, ref: str, size: Tuple[int, int]) -> str:
        """Data URL of the frame resized to `size`, encoded once and cached: the identical
        string is re-sent every turn so the server's prefix cache keeps hitting."""
        key = (ref, tuple(size))
        url = self._ctx_cache.get(key)
        if url is None:
            row = self.index[ref]
            img = Image.open(self.dir / row["file"]).convert("RGB")
            if img.size != tuple(size):
                img = img.resize(tuple(size), Image.LANCZOS)
            url = "data:image/jpeg;base64," + base64.b64encode(_encode(img)).decode()
            self._ctx_cache[key] = url
        return url


def _encode(img: Image.Image, q: int = 85) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=q)
    return buf.getvalue()
