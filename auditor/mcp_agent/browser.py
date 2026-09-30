"""Pinned production Three.js pages with the upstream action/observation adapter.

Playwright runs on a dedicated thread because the MCP server uses asyncio.
Only pixels, player pose and action results reach the agent, never page answers.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import time
from urllib.parse import urlencode

from agent.env.base import ALL_CAPABILITIES


class BrowserEnv:
    name = "threejs"
    capabilities = ALL_CAPABILITIES
    speed_mps = 5.2
    turn_dps = 120.0

    def __init__(self, config):
        self.config = config
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.impl = None
        self.failed = False
        self.closed = False
        self.info = {"engine": "threejs", "task_id": config["task"],
                     "page_sha256": config["page_sha256"], "renderer_host": "local",
                     "clock": "native page realtime; animations may advance between actions"}

    def _reset(self, task, seed, obs):
        from agent.env.threejs import ThreeJSEnv, _decode, _pose
        from agent.types import Observation
        from harness.bridge import Bridge
        cfg = self.config
        if task != cfg["task"] or seed != 5:
            raise ValueError("Production browser tasks are pinned to their assigned task and seed 5")
        root = Path(cfg["browser_root"]).resolve()
        filename = cfg["browser_page"]
        if Path(filename).name != filename:
            raise ValueError("Expected a standalone page filename")
        page = root / filename
        if hashlib.sha256(page.read_bytes()).hexdigest() != cfg["page_sha256"]:
            raise ValueError("Browser page differs from accepted production version")

        class ProductionBridge(Bridge):
            def open_env(bridge, config, seed=None, agent=True, timeout=240000, extra=None):
                query = {"bug": cfg["browser_case"], "config": cfg["browser_case"],
                         "noui": 1, "harness": 1, "seed": seed, **(extra or {})}
                started = time.monotonic()
                bridge.page.goto(f"http://127.0.0.1:{bridge.port}/{filename}?{urlencode(query)}", timeout=timeout)
                bridge.page.wait_for_function("window.__env?.ready === true || window.__initError", timeout=timeout)
                if bridge.page.evaluate("() => Boolean(window.__initError)"):
                    raise RuntimeError("Browser environment initialization failed")
                bridge.page.evaluate("() => window.__env.enable()")
                renderer = bridge.page.evaluate("""() => {
                    const candidates = [...document.querySelectorAll('canvas')]
                        .filter(c => c.clientWidth && c.clientHeight)
                        .sort((a,b) => b.clientWidth*b.clientHeight-a.clientWidth*a.clientHeight);
                    let gl;
                    for (const canvas of candidates) {
                        gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
                        if (gl) { window.__auditCaptureCanvas = canvas; break; }
                    }
                    if (!gl) throw Error('No visible WebGL canvas');
                    const e = gl.getExtension('WEBGL_debug_renderer_info');
                    return e ? gl.getParameter(e.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
                }""")
                return {"renderer": renderer, "load_time_s": time.monotonic()-started, "seed": seed}

        self.impl = ThreeJSEnv(gpu="native", size=(960, 540))
        self.impl.bridge = ProductionBridge(gpu="native", size=(960, 540), serve_dir=root)
        self.impl.obs = obs
        self.impl.bridge.start()
        self.impl._started = True
        extra = ({"obs": "film", "filmDt": obs.film_dt, "filmMax": obs.film_max,
                  "filmW": obs.capture_w, "filmH": obs.capture_h} if obs.mode == "film" else {})
        self.impl._meta = self.impl.bridge.open_env(task, seed=seed, extra=extra)
        # Read after rendering, before WebGL discards its drawing buffer.
        # This matches the production grabFrame() without performing an action.
        url = self.impl.bridge.page.evaluate("""() => new Promise(resolve => {
            const grab = n => requestAnimationFrame(() => n > 1 ? grab(n-1) :
                resolve(window.__auditCaptureCanvas.toDataURL('image/jpeg', .85)));
            grab(4);
        })""")
        result = Observation(action_index=0, frames=[_decode(url, "final", 0)],
                             pose=_pose(self.impl.bridge.state()), moved=0, sim_elapsed=0, events={})
        self.info.update(self.impl._meta)
        return result

    def _call(self, fn, *args):
        if self.closed or self.failed:
            raise RuntimeError("Browser episode is closed or failed")
        try:
            return self.pool.submit(fn, *args).result()
        except Exception:
            self.failed = True
            raise

    def reset(self, task, seed, obs):
        return self._call(self._reset, task, seed, obs)

    def step(self, action):
        return self._call(self.impl.step, action)

    def meta(self):
        return {**self.info, "failed": self.failed}

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            if self.impl:
                self.pool.submit(self.impl.close).result()
        finally:
            self.pool.shutdown(wait=True)
