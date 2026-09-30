"""Serve one rendered Unreal episode over loopback HTTP; no agent inference code."""
import argparse
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class APIError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class UnrealBackend:
    def __init__(self, binary, root):
        self.root = Path(tempfile.mkdtemp(prefix='episode-', dir=root))
        self.log = (self.root / 'unreal.log').open('wb')
        self.process = subprocess.Popen([
            str(binary), '/Game/Auditor/Regions/LivingRoom', '-RenderOffscreen',
            '-windowed', '-ResX=960', '-ResY=540', '-unattended', '-nosound',
            '-AuditorServe', '-AuditorIPC=' + str(self.root),
        ], stdout=self.log, stderr=subprocess.STDOUT, start_new_session=True)

    def alive(self):
        return self.process.poll() is None

    def exchange(self, action, **fields):
        request_id = uuid.uuid4().hex
        command = dict(request_id=request_id, action=action, **fields)
        temporary = self.root / 'command.json.tmp'
        temporary.write_text(json.dumps(command))
        temporary.replace(self.root / 'command.json')
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            if not self.alive():
                raise APIError(503, 'Unreal process exited; check the environment log')
            try:
                response = json.loads((self.root / 'response.json').read_text())
            except FileNotFoundError:
                response = {}
            if response.get('request_id') == request_id:
                if response.get('result') in {'capture_failed', 'capture_timeout', 'not_ready'}:
                    self.close()
                    raise APIError(503, response['result'])
                return response
            time.sleep(0.02)
        # Fail closed: a later action must not race a command that timed out.
        self.close()
        raise APIError(504, 'Unreal response timed out; environment process stopped')

    def image(self, filename='observation.png'):
        if Path(filename).name != filename:
            raise APIError(503, 'Invalid frame filename from Unreal')
        try:
            data = (self.root / filename).read_bytes()
        except FileNotFoundError:
            raise APIError(503, 'Unreal has not produced an image')
        if not data.startswith(b'\x89PNG\r\n\x1a\n'):
            raise APIError(503, 'Invalid PNG produced by Unreal')
        return dict(mime_type='image/png', base64=base64.b64encode(data).decode(), sha256=hashlib.sha256(data).hexdigest())

    def close(self):
        if self.alive():
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait()
        self.log.close()


class Environment:
    def __init__(self, backend, regions, tasks, diagnostics=False):
        self.backend = backend
        self.diagnostics = diagnostics
        self.regions = {r['id']: r['map'] for r in regions['regions']}
        self.tasks = {t['id']: t['region'] for t in tasks['tasks']}
        self.lock = threading.Lock()
        self.episode_id = None
        self.observation = None
        self.flags = []
        self.finished = False
        self.cache = {}
        self.expired_requests = set()

    def health(self):
        return {'engine_alive': self.backend.alive(), 'busy': self.lock.locked(),
                'episode_started': self.episode_id is not None,
                'observation_available': self.observation is not None}

    def observe(self, body):
        if self.lock.locked():
            raise APIError(409, 'An action is in progress; wait for its observation')
        if not self.episode_id or body.get('episode_id') != self.episode_id:
            raise APIError(409, 'episode_id does not match the active episode')
        if not self.observation:
            raise APIError(503, 'No observation is ready')
        return self.observation

    def convert(self, state):
        state = dict(state)
        state.pop('request_id', None)
        state.pop('actor_state_digest', None)
        frames = []
        for source in state.pop('frames', []):
            sample = dict(source)
            filename = sample.pop('file')
            sample.pop('request_id', None)
            sample.pop('actor_state_digest', None)
            sample['rgb'] = self.backend.image(filename)
            frames.append(sample)
            (self.backend.root / filename).unlink(missing_ok=True)
        return dict(episode_id=self.episode_id, observation_id=uuid.uuid4().hex,
                    rgb=self.backend.image(), frames=frames, **state)

    def mutate(self, endpoint, body):
        request_id = body.get('request_id')
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128:
            raise APIError(400, 'Provide a request_id string of 1 to 128 characters')
        canonical = json.dumps([endpoint, body], sort_keys=True, separators=(',', ':'), allow_nan=False)
        key = (body.get('episode_id'), request_id)
        if not self.lock.acquire(blocking=False):
            raise APIError(409, 'An action is in progress; retry the same request_id later')
        try:
            if key in self.cache:
                previous, response = self.cache[key]
                if previous != canonical:
                    raise APIError(409, 'request_id was already used for a different request')
                return response
            if key in self.expired_requests:
                raise APIError(410, 'This request was already executed and its cached image expired')
            if self.episode_id and body.get('episode_id') != self.episode_id:
                raise APIError(409, 'episode_id does not match the active episode')
            if endpoint == '/reset':
                task_id = body.get('task_id', 'living_room')
                if task_id in self.regions:
                    region, task = task_id, 'baseline'
                elif task_id in self.tasks:
                    region, task = self.tasks[task_id], task_id
                else:
                    raise APIError(400, 'Unknown task_id')
                seed = body.get('seed', 0)
                if type(seed) is not int or not 0 <= seed <= 2147483647:
                    raise APIError(400, 'seed must be an integer between 0 and 2147483647')
                state = self.backend.exchange('reset', map=self.regions[region], task=task, seed=seed)
                self.episode_id = uuid.uuid4().hex
                self.flags = []
                self.finished = False
                self.observation = self.convert(state)
                response = self.observation
            elif endpoint == '/step':
                if not self.episode_id:
                    raise APIError(409, 'Reset an episode first')
                if self.finished:
                    raise APIError(409, 'Episode is done; reset before taking another action')
                action = body.get('action')
                if not isinstance(action, dict):
                    raise APIError(400, 'action must be an object')
                name = action.get('name')
                if name in {'move_up', 'move_down', 'turn', 'look'}:
                    field = 'distance' if name.startswith('move_') else 'degree'
                    value = action.get(field)
                    if type(value) is not int:
                        raise APIError(400, field + ' must be an integer')
                    if name.startswith('move_') and not 1 <= value <= 2000:
                        raise APIError(400, 'distance must be 1 to 2000 cm')
                    if not name.startswith('move_') and not -360 <= value <= 360:
                        raise APIError(400, 'degree must be between -360 and 360')
                    state = self.backend.exchange(name, value=value)
                    self.observation = self.convert(state)
                    response = self.observation
                elif name in {'idle', 'interact'}:
                    value = 0
                    if name == 'idle':
                        duration = action.get('time')
                        if not isinstance(duration, str) or not re.fullmatch(r'\d+(?:\.\d+)?s', duration):
                            raise APIError(400, 'time must be a seconds string such as 1s or 0.5s')
                        value = float(duration[:-1])
                        if not math.isfinite(value) or not 1/30 <= value <= 10:
                            raise APIError(400, 'idle duration must be between 1/30 and 10 seconds')
                    state = self.backend.exchange(name, value=value)
                    self.observation = self.convert(state)
                    response = self.observation
                elif name == 'flag':
                    bug = action.get('bug')
                    if not isinstance(bug, str) or not 1 <= len(bug) <= 8192:
                        raise APIError(400, 'bug must be text of 1 to 8192 characters')
                    flag = dict(bug=bug, observation_id=self.observation['observation_id'],
                                position_cm=self.observation['position_cm'])
                    self.flags.append(flag)
                    response = dict(self.observation, flag_recorded=True, flags=list(self.flags))
                elif name == 'done':
                    self.finished = True
                    response = dict(self.observation, done=True, flags=list(self.flags))
                else:
                    raise APIError(400, 'Unknown action name')
            elif endpoint == '/state':
                if not self.diagnostics:
                    raise APIError(403, 'Operator diagnostics are disabled')
                if not self.episode_id:
                    raise APIError(409, 'Reset an episode first')
                response = dict(self.backend.exchange('snapshot'), episode_id=self.episode_id)
                response.pop('request_id', None)
            else:
                raise APIError(404, 'Unknown endpoint')
            self.cache[key] = (canonical, response)
            if len(self.cache) > 256:
                oldest = next(iter(self.cache))
                self.expired_requests.add(oldest)
                del self.cache[oldest]
            return response
        finally:
            self.lock.release()


def serve(environment, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass  # Do not log agent reports or episode identifiers in URLs.

        def send(self, status, result):
            data = json.dumps(result, allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass  # The result remains cached after a client disconnects.

        def do_GET(self):
            if self.path in {'/', '/index.html'}:
                data = Path(__file__).with_name('environment_viewer.html').read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass
            elif self.path == '/health':
                self.send(200, environment.health())
            elif self.path == '/tasks':
                self.send(200, {'baselines': list(environment.regions), 'tasks': [
                    {'id': k, 'region': v} for k, v in environment.tasks.items()]})
            else:
                self.send(404, {'error': 'Unknown endpoint'})

        def do_POST(self):
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 1 <= size <= 1048576:
                    raise APIError(400, 'Request body must be between 1 byte and 1 MiB')
                body = json.loads(self.rfile.read(size), parse_constant=lambda s: (_ for _ in ()).throw(ValueError('Non-finite number')))
                if not isinstance(body, dict):
                    raise APIError(400, 'Request body must be a JSON object')
                if self.path == '/observe':
                    response = environment.observe(body)
                else:
                    response = environment.mutate(self.path, body)
                self.send(200, response)
            except APIError as exc:
                self.send(exc.status, {'error': exc.message})
            except (ValueError, TypeError):
                self.send(400, {'error': 'Invalid JSON request'})
            except Exception:
                self.send(500, {'error': 'Environment service error; inspect the server log'})
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    def monitor_engine():
        environment.backend.process.wait()
        server.shutdown()
    threading.Thread(target=monitor_engine, daemon=True).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', required=True, type=Path)
    parser.add_argument('--regions', required=True, type=Path)
    parser.add_argument('--tasks', required=True, type=Path)
    parser.add_argument('--state-directory', required=True, type=Path)
    parser.add_argument('--port', default=9100, type=int)
    parser.add_argument('--enable-diagnostics', action='store_true')
    args = parser.parse_args()
    if not args.binary.is_file():
        parser.error('The packaged Linux executable/launcher is missing')
    args.state_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    backend = UnrealBackend(args.binary.resolve(), args.state_directory.resolve())
    environment = Environment(backend, json.loads(args.regions.read_text()), json.loads(args.tasks.read_text()), args.enable_diagnostics)
    def terminate(*unused):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, terminate)
    stopping = False
    try:
        serve(environment, args.port)
    except KeyboardInterrupt:
        stopping = True
    finally:
        backend.close()
    if not stopping:
        raise SystemExit(1)  # Let the service manager restart after an engine failure.


if __name__ == '__main__':
    main()
