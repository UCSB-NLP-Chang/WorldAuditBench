"""One isolated Unreal process. No connection to the private evaluation services."""
import ctypes, hashlib, json, os, signal, subprocess, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

class UnrealRuntime:
    def __init__(self):
        self.process = None
        self.log = None
        self.config = None
        self.error = 'The interactive environment is being prepared. Please check back soon.'
        path = os.environ.get('WAB_RUNTIME_CONFIG', str(ROOT / 'runtime.json'))
        if not Path(path).is_file():
            print('Runtime unavailable: set WAB_RUNTIME_CONFIG after restoring the Unreal Linux package.', flush=True)
            return
        try:
            self.config = json.loads(Path(path).read_text())
            binary = Path(self.config['binary'])
            if not binary.is_file() or not os.access(binary, os.X_OK):
                raise ValueError('Unreal binary is missing or not executable')
            expected = self.config['sha256']
            if len(expected) != 64 or hashlib.file_digest(binary.open('rb'),'sha256').hexdigest() != expected:
                raise ValueError('Unreal binary hash does not match the configured release')
            gpu=subprocess.run(['nvidia-smi','--query-gpu=name,driver_version','--format=csv,noheader'], check=True, capture_output=True, text=True, timeout=10)
            ctypes.CDLL('libvulkan.so.1')
            ctypes.CDLL('libnvidia-encode.so.1')
            subprocess.run(['vulkaninfo', '--summary'], check=True, capture_output=True, timeout=20)
            print('Runtime GPU ready: '+gpu.stdout.strip(),flush=True)
            self.error = None
        except Exception as exc:
            print(f'Runtime preflight failed: {exc}', flush=True)
            self.error = 'The interactive environment is temporarily unavailable.'

    def start(self, case, session_id):
        if self.error: raise RuntimeError(self.error)
        self.stop()
        folder = Path('/tmp/worldauditbench-sessions') / session_id
        folder.mkdir(parents=True, exist_ok=True)
        binary = Path(self.config['binary'])
        args = [str(binary), case['map'], '-RenderOffscreen', '-vulkan', '-sm5',
                '-AuditorSkipSceneMenu', '-AuditorRemoteInput',
                '-DefaultViewportMouseCaptureMode=NoCapture',
                '-ini:Input:[/Script/Engine.InputSettings]:bCaptureMouseOnLaunch=False',
                '-ini:Input:[/Script/Engine.InputSettings]:DefaultViewportMouseLockMode=DoNotLock',
                '-ForceRes', '-ResX=1920', '-ResY=1080', '-Unattended', '-AudioMixer',
                '-PixelStreamingConnectionURL=ws://127.0.0.1:8888', '-PixelStreamingID=DefaultStreamer',
                '-PixelStreamingEncoderCodec=H264', '-PixelStreamingWebRTCFps=30',
                '-PixelStreamingWebRTCMaxBitrate=12000000', '-PixelStreamingWebRTCStartBitrate=5000000',
                '-PixelStreamingAllowPixelStreamingCommands=false',
                '-PixelStreamingKeyFilter="M,One,Two,Three,Four,Tilde"',
                '-ExecCmds=t.MaxFPS 30,set HUD bShowHUD false', '-SaveToUserDir', f'-UserDir={folder}/user/',
                f'-AuditorReviewIPC={folder}/ipc', '-log', f'-abslog={folder}/unreal.log']
        policy = self.config.get('policy')
        if policy:
            args += [f'-AuditorExplorationPolicy={policy}', f'-AuditorExplorationTask={case["id"]}']
        args += self.config.get('extra_args', [])
        self.log = (folder/'stdout.log').open('ab')
        # libwebsockets allocates an entry per allowed fd; Docker may advertise billions.
        self.process = subprocess.Popen(['/bin/sh', '-c', 'ulimit -n 4096; exec "$@"', 'unreal', *args], cwd=binary.parent, stdout=self.log,
                stderr=subprocess.STDOUT, start_new_session=True)

    def alive(self):
        return self.process is not None and self.process.poll() is None

    def ready(self, case, session_id):
        try:
            ack=json.loads((Path('/tmp/worldauditbench-sessions')/session_id/'ipc/response.json').read_text())
            return (self.alive() and ack.get('status')=='ready' and
                    ack.get('pid')==self.process.pid and ack.get('task')==case['id'] and
                    ack.get('map')==case['map'].partition('?')[0])
        except (OSError,ValueError):return False

    def stop(self):
        if self.process is not None:
            if self.process.poll() is None:
                os.killpg(self.process.pid, signal.SIGTERM)
                try: self.process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait(timeout=5)
            self.process = None
        if self.log: self.log.close(); self.log=None
