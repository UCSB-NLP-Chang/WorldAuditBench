#!/usr/bin/env python3
"""Restore the per-0.5 s frames of a VLA recording from its video.mp4.

harness/vla_explore.py and harness/vla_ue.py write one full frame every `record_every` ticks (f<tick>.jpg, listed in
meta.json "frames") and assemble them into video.mp4 at fps = 1000 / dt_ms / record_every * 2 (4 fps for 50 ms x 10):
video frame k IS recorded frame k, so decoding the video gives the frame list back (re-encoded through H.264, quality 7,
not the original JPEG bytes).  Copies of the runs that carry only meta.json + poses.jsonl + video.mp4 (../vla-recordings)
get their f*.jpg back so that eval/vla_video_judge.py, eval/vqa_audit.py and eval/judge --images can read them.

usage: .venv/bin/python tools/vla_frames_from_video.py ../vla-recordings/vla-threejs-v2 ../vla-recordings/vla-ue-v1 [--force]
"""
import argparse, json, pathlib, sys

import imageio.v3 as iio
from PIL import Image


def restore(ep: pathlib.Path, force=False):
    meta = json.loads((ep / "meta.json").read_text())
    names = meta.get("frames") or []
    if not names:
        return "no frame list"
    if not force and all((ep / n).exists() for n in names):
        return "present"
    video = ep / "video.mp4"
    if not video.exists():
        return "no video"
    frames = list(iio.imiter(video, plugin="FFMPEG"))
    if len(frames) != len(names):
        return f"MISMATCH video {len(frames)} frames vs meta {len(names)}"
    for n, arr in zip(names, frames):
        Image.fromarray(arr).save(ep / n, "JPEG", quality=90)
    (ep / "frames.restored.json").write_text(json.dumps({"source": "video.mp4", "frames": len(names), "jpeg_quality": 90}) + "\n")
    return f"restored {len(names)}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_bases", nargs="+")
    ap.add_argument("--force", action="store_true", help="rewrite frames that already exist")
    a = ap.parse_args()
    bad = 0
    for base in a.run_bases:
        eps = sorted(p for p in pathlib.Path(base).iterdir() if p.is_dir() and (p / "meta.json").exists())
        counts = {}
        for ep in eps:
            r = restore(ep, a.force)
            key = r.split(" ")[0]
            counts[key] = counts.get(key, 0) + 1
            if key in ("MISMATCH", "no"):
                bad += 1; print(f"  {ep.name}: {r}")
        print(f"{base}: {len(eps)} episodes, {counts}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
