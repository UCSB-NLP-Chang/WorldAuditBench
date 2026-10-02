"""Locate and start downloaded benchmark environments."""
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME = ROOT / 'out/runtime'


def task_catalog():
    return {t['id']: t for t in json.loads((ROOT / 'data/benchmark/paper-tasks.json').read_text())['tasks']}


def package_for(task):
    packages = json.loads((ROOT / 'data/resources/releases.json').read_text())['packages']
    found = [p for p in packages if task in p.get('tasks', [])]
    if len(found) != 1:
        raise ValueError('Unknown or ambiguous task: ' + task)
    return found[0]


def ensure_environment(task, runtime=DEFAULT_RUNTIME, download=False):
    package = package_for(task)
    marker = runtime / package['id'] / '.worldauditbench-release.json'
    if download:
        subprocess.run([sys.executable, str(ROOT / 'scripts/download_resources.py'),
                        '--root', str(runtime), '--package', package['id']], check=True)
    if not marker.is_file() or json.loads(marker.read_text()).get('sha256') != package['sha256']:
        raise ValueError(f"Environment {package['id']} is not installed at this revision; rerun with --download")
    return package


def server_command(task, runtime=DEFAULT_RUNTIME, gpu=0, port=19100):
    return [sys.executable, str(ROOT / 'scripts/serve_unreal.py'), '--task', task,
            '--profiles', str(runtime / 'unreal-profiles.json'), '--gpu', str(gpu), '--port', str(port)]


def wait_ready(process, port, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('Environment process exited before becoming ready')
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, ValueError):
            pass
        time.sleep(.2)
    raise TimeoutError('Environment startup timed out')


def stop(process):
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
