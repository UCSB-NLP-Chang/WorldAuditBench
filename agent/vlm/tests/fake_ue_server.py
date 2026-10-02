"""In-process stand-in for the simworld_server endpoints the UE adapter assumes (see
agent/vlm/env/ue.py docstring for the contract). Walks a point on a plane in centimetres."""
import base64
import io
import json
import math
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from PIL import Image, ImageDraw


def _rgb(w, h, label):
    img = Image.new("RGB", (w, h), (30, 60, 90))
    ImageDraw.Draw(img).text((10, 10), label, fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


class FakeUEServer:
    def __init__(self, speed=200.0):
        self.requests = []
        self.state = dict(x=0.0, y=0.0, z=90.0, yaw=0.0, t=0.0)
        self.envs = {}
        self.deleted = []
        srv = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, status, body):
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
                srv.requests.append(dict(method="POST", path=self.path, body=body))
                if self.path == "/envs":
                    eid = f"env-{len(srv.envs) + 1}"
                    srv.envs[eid] = body
                    return self._send(200, {"env_id": eid, "port": 9000, "status": "ready",
                                            "map_path": body.get("map_path") or "/Game/Maps/demo_1"})
                if self.path.endswith("/reset"):
                    srv.state.update(x=0.0, y=0.0, yaw=0.0, t=0.0)
                    return self._send(200, {"observations": [srv.observe(body["observe"])]})
                if self.path.endswith("/step"):
                    return self._send(200, srv.step(body))
                return self._send(404, {"detail": "no such route"})

            def do_DELETE(self):
                srv.requests.append(dict(method="DELETE", path=self.path))
                srv.deleted.append(self.path.rsplit("/", 1)[1])
                self._send(200, {"deleted": self.path})

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.speed = speed
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def observe(self, spec, t=None):
        s = self.state
        w, h = spec.get("width", 640), spec.get("height", 480)
        return {"position": [s["x"], s["y"], s["z"]], "rotation": [0.0, s["yaw"], 0.0],
                "rgb": _rgb(w, h, f"t={s['t'] if t is None else t}"), "rgb_mime": "image/jpeg",
                "action_ok": True, "action_message": "ok"}

    def step(self, body):
        a, spec = body["action"], body["observe"]
        s = self.state
        x0, y0 = s["x"], s["y"]
        if a["choice"] == 1:
            d = self.speed * a["duration"] * (-1 if a.get("direction") == 1 else 1)
            s["x"] += math.cos(math.radians(s["yaw"])) * d
            s["y"] += math.sin(math.radians(s["yaw"])) * d
            elapsed = a["duration"]
        elif a["choice"] == 2:
            s["yaw"] = (s["yaw"] + (a["angle"] if a.get("clockwise", True) else -a["angle"])) % 360
            elapsed = a.get("duration", 0.5)
        else:
            elapsed = a.get("duration", 0.5)
        frames = []
        film = body.get("film")
        if film:
            t = 0.0
            while t <= elapsed + 1e-9 and len(frames) < film["max_frames"]:
                frames.append({"t": t, "rgb": _rgb(spec.get("width", 640), spec.get("height", 480), f"film t={t}")})
                t += film["dt"]
        s["t"] += elapsed
        out = self.observe(spec)
        out.update(moved=math.hypot(s["x"] - x0, s["y"] - y0), sim_elapsed=elapsed, frames=frames,
                   clock=body.get("clock", "realtime"))
        return out

    def close(self):
        self.httpd.shutdown()
