#!/usr/bin/env python3
"""Serve one downloaded WorldAuditBench task over loopback HTTP."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from auditor.environment_server import APIError, Environment, UnrealBackend, serve


class ReleasedBackend(UnrealBackend):
    def __init__(self, task_id, profile, state_root, gpu):
        self.task_id = task_id
        self.map_name = profile['runtime_map'].split('?', 1)[0]
        self.consumed = False
        self.root = Path(tempfile.mkdtemp(prefix=task_id + '-', dir=state_root))
        self.log = (self.root / 'unreal.log').open('wb')
        remote = profile.get('remote_task')
        launch = profile.get('launch_map', self.map_name) if remote else self.map_name + '?Task=' + task_id
        args = [a for a in profile.get('game_args', []) + profile.get('extra_args', [])
                if not a.lower().startswith(('-pixelstreaming', '-graphicsadapter', '-auditoripc', '-abslog'))]
        command = [profile['binary'], launch, '-RenderOffscreen', '-windowed',
                   '-ResX=960', '-ResY=540', '-unattended', '-nosound', '-AuditorServe',
                   '-AuditorIPC=' + str(self.root), '-abslog=' + str(self.root / 'native.log'),
                   '-forcelogflush', f'-graphicsadapter={gpu}', *args]
        if remote:
            command.append('-AuditorRemoteTask=' + remote)
        self.process = subprocess.Popen(command, stdout=self.log, stderr=subprocess.STDOUT,
                                        start_new_session=True,
                                        env={**os.environ, 'XDG_CACHE_HOME': str(state_root / 'cache')})

    def exchange(self, action, **fields):
        if action != 'reset':
            return super().exchange(action, **fields)
        if self.consumed:
            raise APIError(409, 'Start a fresh server for each benchmark episode')
        if fields != {'map': self.map_name, 'task': self.task_id, 'seed': 0}:
            raise APIError(400, 'This server supports its assigned task and seed slot 0')
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if not self.alive():
                raise APIError(503, 'Unreal exited; inspect ' + str(self.root / 'unreal.log'))
            try:
                state = json.loads((self.root / 'response.json').read_text())
            except (FileNotFoundError, json.JSONDecodeError):
                state = {}
            if state.get('result') == 'ready':
                if not state.get('paused') or state.get('task_id') != self.task_id:
                    raise APIError(503, 'Unreal did not load the assigned paused task')
                if state.get('map') != self.map_name.rsplit('/', 1)[-1]:
                    raise APIError(503, 'Unreal loaded an unexpected map')
                self.consumed = True
                return state
            time.sleep(0.1)
        raise APIError(504, 'Unreal startup timed out')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profiles', type=Path, default=ROOT / 'out/runtime/unreal-profiles.json')
    parser.add_argument('--task', required=True)
    parser.add_argument('--port', type=int, default=19100)
    parser.add_argument('--gpu', type=int, default=0)
    parser.add_argument('--state-root', type=Path, default=ROOT / 'out/episodes')
    args = parser.parse_args()
    profiles = json.loads(args.profiles.read_text())['tasks']
    if args.task not in profiles:
        parser.error('Task is not installed; run scripts/download_resources.py first')
    profile = profiles[args.task]
    binary = Path(profile['binary'])
    checksum = hashlib.sha256()
    with binary.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            checksum.update(block)
    actual = checksum.hexdigest()
    if actual != profile['build_sha256']:
        parser.error('Executable checksum differs from the experiment profile')
    if sys.platform != 'linux':
        parser.error('Packaged environments require a Linux x86_64 host with a compatible GPU')
    args.state_root = args.state_root.resolve()
    args.state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    # UE's bundled networking code assumes a bounded descriptor limit.
    import resource
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft == resource.RLIM_INFINITY or soft > 4096:
        resource.setrlimit(resource.RLIMIT_NOFILE, (4096, hard))
    backend = ReleasedBackend(args.task, profile, args.state_root, args.gpu)
    class IdentifiedEnvironment(Environment):
        def health(self):
            return {**super().health(), 'task_id': args.task, 'build_sha256': actual,
                    'sampling_interval_seconds': 0.5, 'startup_rng_seeded': False}
    environment = IdentifiedEnvironment(backend, {'regions': [{'id': 'scene', 'map': backend.map_name}]},
                                       {'tasks': [{'id': args.task, 'region': 'scene'}]})
    def stop(*unused):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print(f'Serving {args.task} at http://127.0.0.1:{args.port}; state: {backend.root}', flush=True)
    try:
        serve(environment, args.port)
    except KeyboardInterrupt:
        pass
    finally:
        backend.close()


if __name__ == '__main__':
    main()
