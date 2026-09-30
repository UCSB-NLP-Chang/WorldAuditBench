"""Playwright bridge: static server + headless Chromium + window.__env wrapper + GPU detection.

Usage (library):
    from harness.bridge import Bridge
    with Bridge(gpu="gl-egl") as br:
        meta = br.open_env("env0-corridor", seed=1)
        res = br.act({"action": "forward", "dist": 1.5})

Usage (GPU self-check):
    python -m harness.bridge --check-gpu
"""
import argparse
import functools
import http.server
import json
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

COMMON_ARGS = ["--no-sandbox", "--disable-dev-shm-usage", "--enable-webgl", "--ignore-gpu-blocklist"]
GPU_FLAGSETS = {
    "vulkan": COMMON_ARGS + ["--use-angle=vulkan", "--enable-features=Vulkan,DefaultANGLEVulkan,VulkanFromANGLE"],
    "gl-egl": COMMON_ARGS + ["--use-angle=gl-egl"],
    "swiftshader": COMMON_ARGS + ["--use-angle=swiftshader-webgl"],
    # "native": the full Chromium binary in the new headless mode, which keeps GPU access (Playwright's
    # headless_shell used by headless=True is software-only on macOS). On an Apple-silicon Mac this is
    # ANGLE Metal at ~120 fps for Sponza vs SwiftShader's ~7x-slower-than-realtime; on Linux/NVIDIA it
    # picks whatever ANGLE backend Chromium selects (prefer gl-egl there).
    "native": COMMON_ARGS + ["--headless=new"],
}


class _SilentHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


class _StaticServer(http.server.ThreadingHTTPServer):
    # A page load opens dozens of module/asset connections at once; with several Chromium instances
    # starting simultaneously (CPU-saturated by SwiftShader) the default backlog of 5 overflows and
    # macOS answers the surplus SYNs with RST (net::ERR_CONNECTION_RESET, page never ready).
    request_queue_size = 256

    def handle_error(self, request, client_address):
        # Chromium aborts asset downloads it no longer needs (BrokenPipe / ConnectionReset); the
        # default handler prints a full traceback for each - keep the run logs readable.
        import sys
        exc = sys.exc_info()[1]
        if not isinstance(exc, (BrokenPipeError, ConnectionResetError)):
            super().handle_error(request, client_address)


class Bridge:
    def __init__(self, gpu="gl-egl", headless=True, size=(960, 600), serve_dir=REPO):
        self.gpu, self.headless, self.size, self.serve_dir = gpu, headless, size, Path(serve_dir)
        # headless_shell (headless=True) cannot use the GPU; "native" launches full Chromium with --headless=new instead
        self.launch_headless = headless and gpu != "native"
        self.console = []       # (type, text)
        self.page_errors = []
        self._httpd = self._pw = self.browser = self.page = None
        self.port = None

    # ── lifecycle ──
    def start(self):
        handler = functools.partial(_SilentHandler, directory=str(self.serve_dir))
        self._httpd = _StaticServer(("127.0.0.1", 0), handler)
        self.port = self._httpd.server_address[1]
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()

        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self.browser = self._pw.chromium.launch(
            headless=self.launch_headless, args=GPU_FLAGSETS[self.gpu])
        self.page = self.browser.new_page(viewport={"width": self.size[0], "height": self.size[1]})
        self.page.on("console", lambda m: self.console.append((m.type, m.text)))
        self.page.on("pageerror", lambda e: self.page_errors.append(str(e)))
        return self

    def close(self):
        for fn in (lambda: self.browser.close(), lambda: self._pw.stop(),
                   lambda: self._httpd.shutdown()):
            try:
                fn()
            except Exception:
                pass

    def __enter__(self):
        return self.start()

    def __exit__(self, *a):
        self.close()

    # ── env ──
    def open_env(self, config, seed=None, agent=True, timeout=240_000, extra=None):
        entry = "agent" if agent else "human"
        url = f"http://127.0.0.1:{self.port}/env/{entry}.html?config={config}"
        # standalone page environments (e.g. the reef): the config names the page; it implements window.__env itself
        cfg_path = self.serve_dir / "env" / "configs" / f"{config}.json"
        if cfg_path.exists():
            try:
                page = json.loads(cfg_path.read_text()).get("page")
            except Exception:
                page = None
            if page:
                url = f"http://127.0.0.1:{self.port}/{page}?harness=1&config={config}"
        if seed is not None:
            url += f"&seed={seed}"
        for k, v in (extra or {}).items():
            url += f"&{k}={v}"
        t0 = time.time()
        self.page.goto(url)
        self.page.wait_for_function(
            "(window.__env && window.__env.ready === true) || window.__initError", timeout=timeout)
        err = self.page.evaluate("() => window.__initError || null")
        if err:
            raise RuntimeError(f"env init failed: {err}")
        meta = self.page.evaluate("() => window.__env.meta")
        meta["load_time_s"] = round(time.time() - t0, 2)
        if agent:
            self.page.evaluate("() => window.__env.enable()")
        return meta

    def act(self, action):
        return self.page.evaluate("a => window.__env.act(a)", action)

    def state(self):
        return self.page.evaluate("() => window.__env.state()")

    def targets(self):
        return self.page.evaluate("() => window.__env.targets()")

    def flags(self):
        return self.page.evaluate("() => window.__env.flags()")

    def probe(self):
        return self.page.evaluate("() => window.__env.probe()")

    def console_errors(self):
        return [t for typ, t in self.console if typ == "error"]

    def measure_fps(self, seconds=1.0):
        return self.page.evaluate(
            """(sec) => new Promise(res => {
                 let n = 0; const t0 = performance.now();
                 const tick = () => {
                   n++;
                   if (performance.now() - t0 >= sec * 1000) res(+(n / sec).toFixed(1));
                   else requestAnimationFrame(tick);
                 };
                 requestAnimationFrame(tick);
               })""", seconds)


def check_gpu():
    print(f"{'mode':<12} {'renderer':<60} {'env0 load':<10} fps")
    best = None
    for mode in GPU_FLAGSETS:
        try:
            with Bridge(gpu=mode) as br:
                meta = br.open_env("env0-corridor", seed=1)
                fps = br.measure_fps(1.5)
                soft = ("SwiftShader" in meta["renderer"]) or ("llvmpipe" in meta["renderer"])
                print(f"{mode:<12} {meta['renderer']:<60} {meta['load_time_s']:<10} {fps}"
                      + ("   [software]" if soft else "   [real GPU]"))
                if not soft and best is None:
                    best = mode
        except Exception as e:
            print(f"{mode:<12} FAILED: {str(e).splitlines()[0][:90]}")
    print(f"\nsuggested --gpu {best or 'swiftshader'}"
          + (" (no real GPU; software rendering works - VLM inference is the bottleneck - but it is recorded in run logs)" if best is None else ""))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-gpu", action="store_true")
    args = ap.parse_args()
    if args.check_gpu:
        check_gpu()
