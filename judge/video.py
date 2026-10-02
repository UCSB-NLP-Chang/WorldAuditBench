"""Assemble an episode's frame sequence into an annotated mp4 (for human review).

Usage (library): make_video(run_dir, fps=3)
Usage (CLI): python -m judge.video runs/xxx/episode-yyy [fps]
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BAR_H = 56


def _font(size=15):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _annotate(img, lines):
    w, h = img.size
    out = Image.new("RGB", (w, h + BAR_H), (12, 14, 18))
    out.paste(img, (0, 0))
    d = ImageDraw.Draw(out)
    f = _font()
    for i, ln in enumerate(lines[:3]):
        d.text((8, h + 4 + i * 17), ln[:130], fill=(230, 230, 230), font=f)
    # prominent red BLOCKED badge (top-right), viewer-facing only - the agent never sees it
    if any("BLOCKED" in ln for ln in lines[:1]):
        bf = _font(30)
        tw = d.textlength("BLOCKED", font=bf)
        d.rectangle([w - tw - 34, 12, w - 10, 56], fill=(180, 24, 24))
        d.text((w - tw - 22, 18), "BLOCKED", fill=(255, 255, 255), font=bf)
    return out


def make_video(run_dir, fps=3, out_name="video.mp4"):
    import imageio.v2 as imageio
    run_dir = Path(run_dir)
    frames_meta = run_dir / "frames.jsonl"
    entries = []
    if frames_meta.exists():
        entries = [json.loads(l) for l in frames_meta.read_text().splitlines() if l.strip()]
    else:  # fallback: jpgs in the directory sorted by name
        entries = [{"file": p.name, "caption": [p.stem]} for p in sorted(run_dir.glob("f*.jpg"))]
    if not entries:
        return None
    out = run_dir / out_name
    wr = imageio.get_writer(out, fps=fps, codec="libx264", quality=7,
                            pixelformat="yuv420p", macro_block_size=8)
    for e in entries:
        p = run_dir / e["file"]
        if not p.exists():
            continue
        img = Image.open(p).convert("RGB")
        if img.width != 960:                      # upscale film frames (480x300) to a uniform size
            img = img.resize((960, round(img.height * 960 / img.width)))
        wr.append_data(__import__("numpy").asarray(_annotate(img, e.get("caption", []))))
    wr.close()
    return out


if __name__ == "__main__":
    d = sys.argv[1]
    fps = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    print(make_video(d, fps))
