"""Shared test helpers: synthetic frames, poses, observations."""
import io

from PIL import Image, ImageDraw

from agent.vlm.types import Frame, Observation, Pose


def jpeg_bytes(w=960, h=600, color=(40, 80, 120), text=""):
    img = Image.new("RGB", (w, h), color)
    if text:
        ImageDraw.Draw(img).text((10, 10), text, fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def pose(x=0.0, y=0.0, z=1.7, yaw=90.0, pitch=0.0):
    return Pose(x=x, y=y, z=z, yaw=yaw, pitch=pitch, raw={"pos": [x, z, y], "yaw": yaw, "pitch": pitch})


def observation(action_index, n_film=0, moved=0.0, w=960, h=600, **events):
    frames = [Frame(ref="", kind="film", t_sim=0.5 * i, jpeg=jpeg_bytes(w, h, text=f"film{i}"), w=w, h=h)
              for i in range(n_film)]
    frames.append(Frame(ref="", kind="final", t_sim=0.5 * n_film, jpeg=jpeg_bytes(w, h, text="final"), w=w, h=h))
    return Observation(action_index=action_index, frames=frames, pose=pose(x=float(action_index)),
                       moved=moved, sim_elapsed=0.5 * n_film, events=dict(events))
