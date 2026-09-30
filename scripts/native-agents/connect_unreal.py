#!/usr/bin/env python3
"""Start an isolated AWS Unreal episode and keep its SSH tunnel open in this terminal."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import signal
import socket
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def main():
    local_profile = ROOT / "out/native-agents/aws-connection.json"
    defaults = json.loads(local_profile.read_text()) if local_profile.exists() else {}
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default=defaults.get("host", "ec2-user@98.84.22.147"))
    p.add_argument("--identity", type=Path, default=defaults.get("identity"), help="SSH private key; never copied to the server")
    p.add_argument("--task", required=True)
    p.add_argument("--gpu", type=int, default=2)
    p.add_argument("--local-port", type=int, default=19100)
    p.add_argument("--remote-port", type=int, default=49100)
    p.add_argument("--gpu-slot", type=int, default=0)
    p.add_argument("--gpu-slots", type=int, choices=[1, 2], default=1)
    args = p.parse_args()
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", args.local_port))
    ssh = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=20", "-o", "ServerAliveCountMax=3"]
    if args.identity:
        ssh += ["-o", "IdentitiesOnly=yes", "-i", str(args.identity.expanduser().resolve())]
    files = {
        "environment_server.py": (ROOT / "auditor/environment_server.py").read_text(),
        "environment_viewer.html": (ROOT / "auditor/environment_viewer.html").read_text(),
        "remote_unreal.py": (ROOT / "scripts/native-agents/remote_unreal.py").read_text(),
    }
    revision = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:16]
    upload = (
        "import json,sys; from pathlib import Path; data=json.load(sys.stdin); "
        f"root=Path.home()/'native-agent-mcp'/'code-{revision}'; root.mkdir(parents=True,exist_ok=True); "
        "[(root/name).write_text(content) for name,content in data.items()]; print(root)"
    )
    remote_root = subprocess.check_output(ssh + [args.host, shlex.join(["python3", "-c", upload])],
                                          input=json.dumps(files), text=True).strip()
    remote_command = ["python3", "-u", remote_root + "/remote_unreal.py", "--task", args.task,
                      "--port", str(args.remote_port), "--gpu", str(args.gpu),
                      "--gpu-slot", str(args.gpu_slot), "--gpu-slots", str(args.gpu_slots),
                      "--state-root", str(Path(remote_root).parent / "episodes")]
    tunnel = None
    process = None
    def stop(*unused):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        tunnel = subprocess.Popen(ssh + ["-N", "-o", "ExitOnForwardFailure=yes", "-L",
                                         f"127.0.0.1:{args.local_port}:127.0.0.1:{args.remote_port}", args.host])
        # PTY hangup stops the remote runner, which reaps only its own Unreal process.
        process = subprocess.Popen(ssh + ["-tt", args.host, shlex.join(remote_command)])
        url = f"http://127.0.0.1:{args.local_port}"
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if tunnel.poll() is not None or process.poll() is not None:
                raise RuntimeError("SSH tunnel or remote environment exited")
            try:
                with urllib.request.urlopen(url + "/health", timeout=2) as r:
                    if json.load(r).get("engine_alive"):
                        break
            except Exception:
                time.sleep(.5)
        else:
            raise RuntimeError("Environment startup timed out")
        print(f"Ready: --environment unreal-http --env-url {url} --task {args.task}", flush=True)
        print("Use a separate terminal to start ONE model. Keep this terminal open; Ctrl-C stops this episode.", flush=True)
        while process.poll() is None and tunnel.poll() is None:
            time.sleep(1)
        if process.returncode not in (None, 0) or tunnel.returncode not in (None, 0):
            raise RuntimeError("Environment connection ended unexpectedly")
    except KeyboardInterrupt:
        print("Stopping private episode and tunnel.", flush=True)
    finally:
        for proc in [process, tunnel]:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()


if __name__ == "__main__":
    main()
