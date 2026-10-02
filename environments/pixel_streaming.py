"""One standalone Unreal viewer session using Epic's UE 5.6 signalling server."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import subprocess
import tempfile
import threading
import time

from environments.unreal_launch import without_hud

ROOT = Path(__file__).resolve().parents[1]


def free_ports(count):
    sockets = []
    try:
        for _ in range(count):
            sock = socket.socket()
            sock.bind(('127.0.0.1', 0))
            sockets.append(sock)
        return [sock.getsockname()[1] for sock in sockets]
    finally:
        for sock in sockets:
            sock.close()


def launch_command(profile, streamer_port, directory, gpu):
    """Use the interactive launch path, not the paused agent capture protocol."""
    excluded = ('-pixelstreaming', '-graphicsadapter', '-auditoripc', '-auditorserve',
                '-auditorreviewipc', '-abslog', '-userdir', '-resx', '-resy')
    args = [arg for arg in profile.get('game_args', []) + profile.get('extra_args', [])
            if not arg.lower().startswith(excluded)]
    return [profile['binary'], profile['runtime_map'],
            '-AuditorSkipSceneMenu', '-AuditorRemoteInput', '-RenderOffscreen',
            '-DefaultViewportMouseCaptureMode=NoCapture',
            '-ini:Input:[/Script/Engine.InputSettings]:bCaptureMouseOnLaunch=False',
            '-ini:Input:[/Script/Engine.InputSettings]:DefaultViewportMouseLockMode=DoNotLock',
            '-ForceRes', '-ResX=1280', '-ResY=720', '-Unattended', '-AudioMixer', '-ForceLogFlush',
            f'-PixelStreamingConnectionURL=ws://127.0.0.1:{streamer_port}',
            '-PixelStreamingID=DefaultStreamer', '-PixelStreamingEncoderCodec=H264',
            '-PixelStreamingWebRTCFps=30', '-PixelStreamingWebRTCMaxFps=30',
            '-PixelStreamingWebRTCMaxBitrate=3000000',
            '-PixelStreamingWebRTCStartBitrate=1000000',
            '-PixelStreamingAllowPixelStreamingCommands=false',
            '-PixelStreamingKeyFilter=' + profile.get('key_filter', 'M,One,Two,Three,Four,Tilde'),
            f'-graphicsadapter={gpu}', '-UserDir=' + str(directory / 'user') + '/',
            '-SaveToUserDir', '-abslog=' + str(directory / 'unreal.log'),
            *without_hud(args)]


class PixelStreaming:
    def __init__(self, infrastructure, state_root, gpu=0, node='node', peer_options=None):
        self.infrastructure = Path(infrastructure).expanduser().resolve()
        self.state_root = Path(state_root)
        self.gpu, self.node = gpu, node
        self.peer_options = peer_options or {'iceServers': []}
        self.processes, self.logs = [], []
        self.session_id = None
        self.player_port = None
        self.directory = None
        self.boundary_lock = threading.Lock()
        self.boundary_offset = 0
        self.boundary_partial = b''
        self.boundary_state = None

    def validate(self, profile):
        for relative in ['SignallingWebServer/dist/index.js', 'SignallingWebServer/www/player.html']:
            if not (self.infrastructure / relative).is_file():
                raise ValueError('Pixel Streaming is not installed. Run python scripts/setup_pixel_streaming.py, '
                                 'or set --pixel-streaming-root to a built UE 5.6 infrastructure checkout.')
        binary = Path(profile['binary'])
        digest = hashlib.sha256()
        with binary.open('rb') as source:
            for block in iter(lambda: source.read(8 * 1024 * 1024), b''):
                digest.update(block)
        if digest.hexdigest() != profile['build_sha256']:
            raise ValueError('Unreal executable checksum differs from the task profile')

    def start(self, profile, timeout=180):
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.directory = Path(tempfile.mkdtemp(prefix='stream-', dir=self.state_root))
        self.session_id = secrets.token_hex(16)
        streamer, self.player_port, sfu = free_ports(3)
        signal_root = self.infrastructure / 'SignallingWebServer'
        config = dict(streamer_port=streamer, player_port=self.player_port, sfu_port=sfu,
                      serve=True, http_root=str(signal_root / 'www'), homepage='player.html',
                      https=False, https_redirect=False, rest_api=False, log_config=False,
                      stdin=False, max_players=1, console_messages='basic',
                      log_folder=str(self.directory / 'signal-logs'),
                      log_level_console='info', log_level_file='info', peer_options=self.peer_options)
        config_file = self.directory / 'signal-config.json'
        config_file.write_text(json.dumps(config))
        config_file.chmod(0o600)
        try:
            self.spawn([self.node, str(signal_root / 'dist/index.js'), '--config_file', str(config_file)],
                       signal_root, 'signalling.log')
            self.spawn(launch_command(profile, streamer, self.directory, self.gpu),
                       Path(profile['binary']).parent, 'unreal-stdout.log')
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if not self.alive():
                    raise RuntimeError('Unreal or signalling exited; inspect ' + str(self.directory))
                result = subprocess.run(
                    [self.node, str(ROOT / 'scripts/probe_streamer.cjs'),
                     str(self.infrastructure), str(self.player_port)],
                    capture_output=True, timeout=7)
                if result.returncode == 0:
                    return {'engine': 'unreal', 'transport': 'pixel-streaming',
                            'url': f'/stream/{self.session_id}/player.html'}
                time.sleep(.5)
            raise TimeoutError('Unreal did not connect to Pixel Streaming; inspect ' + str(self.directory))
        except BaseException:
            self.close()
            raise

    def spawn(self, command, cwd, filename):
        log = (self.directory / filename).open('wb')
        self.logs.append(log)
        self.processes.append(subprocess.Popen(
            command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, start_new_session=True))

    def alive(self):
        return len(self.processes) == 2 and all(p.poll() is None for p in self.processes)

    def boundary(self):
        """Read native boundary transitions without enabling the engine HUD."""
        with self.boundary_lock:
            if not self.alive() or self.directory is None:
                return None
            try:
                with (self.directory / 'unreal.log').open('rb') as source:
                    if source.seek(0, 2) < self.boundary_offset:
                        self.boundary_offset = 0
                        self.boundary_partial = b''
                        self.boundary_state = None
                    source.seek(self.boundary_offset)
                    chunk = source.read(256 * 1024)
                    self.boundary_offset = source.tell()
            except OSError:
                return None
            lines = (self.boundary_partial + chunk).split(b'\n')
            self.boundary_partial = lines.pop()[-4096:]
            for line in lines:
                match = re.search(rb'AUDITOR_BOUNDARY state=([012])\s', line)
                if match:
                    self.boundary_state = int(match[1])
            return self.boundary_state

    def close(self):
        self.session_id = None
        for process in reversed(self.processes):
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    process.wait()
                    continue
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
        self.processes.clear()
        for log in self.logs:
            log.close()
        self.logs.clear()
        self.player_port = None
        with self.boundary_lock:
            self.boundary_offset = 0
            self.boundary_partial = b''
            self.boundary_state = None
