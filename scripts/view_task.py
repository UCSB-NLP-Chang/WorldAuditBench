#!/usr/bin/env python3
"""Browse task inputs, rubrics and interactive environments locally."""
import argparse
import functools
import hashlib
import http.server
import json
from pathlib import Path
import signal
import sys
import threading
import urllib.error
import urllib.request
from urllib.parse import urlencode, urlparse
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from data.tasks import ensure_dataset, load_task
from scripts.runtime import DEFAULT_RUNTIME, ensure_environment, task_catalog
from environments.pixel_streaming import PixelStreaming
from environments.package_profiles import load_profiles as load_package_profiles
from environments.stream_proxy import proxy as proxy_stream


def load_rows(dataset=None):
    path = dataset or ensure_dataset()
    return [load_task(tid, path) for tid in task_catalog()]


class Viewer:
    def __init__(self, rows, runtime, download=False, gpu=0, *,
                 streaming_root=ROOT / 'out/pixel-streaming', profiles=None,
                 node='node', peer_options=None, packages=None):
        self.rows = rows
        self.tasks = {row['task_id']: row for row in rows}
        self.runtime, self.download, self.gpu = runtime, download, gpu
        self.static = None
        self.streaming = PixelStreaming(streaming_root, ROOT / 'out/viewer', gpu, node, peer_options)
        self.profiles = profiles
        self.packages = packages
        self.build = None
        self.port = None
        self.task = None
        self.lock = threading.Lock()

    def close(self):
        self.streaming.close()
        if self.static:
            self.static.shutdown()
            self.static.server_close()
            self.static = None
        self.task = None
        self.port = None
        self.build = None

    def open(self, task):
        if task not in self.tasks:
            raise ValueError('Unknown task: ' + task)
        if not self.lock.acquire(blocking=False):
            raise ValueError('An environment is starting; please wait')
        try:
            row = self.tasks[task]
            browser = row['engine'] in {'threejs', 'three.js'}
            if not browser and sys.platform != 'linux':
                raise ValueError('Unreal requires a Linux GPU host. You can browse its task details here.')
            if browser or (self.profiles is None and self.packages is None):
                package = ensure_environment(task, self.runtime, self.download)
            if not browser:
                profiles = (load_package_profiles(self.packages) if self.packages else
                            json.loads(Path(self.profiles or self.runtime / 'unreal-profiles.json').read_text())['tasks'])
                profile = profiles.get(task)
                if profile is None:
                    raise ValueError('Task is not installed in the Unreal profiles: ' + task)
                self.streaming.validate(profile)
            self.close()
            if browser:
                root = self.runtime / package['id'] / package['runtime_root']
                page = root / package['page']
                if hashlib.sha256(page.read_bytes()).hexdigest() != task_catalog()[task]['page_sha256']:
                    raise ValueError('Environment page checksum mismatch')
                handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
                self.static = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
                self.port = self.static.server_port
                threading.Thread(target=self.static.serve_forever, daemon=True).start()
                query = urlencode({'bug': task_catalog()[task]['source_case'], 'noui':1, 'seed':5})
                self.task = task
                return {'engine':'threejs','url':f'/environment/{package["page"]}?{query}'}
            result = self.streaming.start(profile)
            self.task = task
            self.build = result.get('build')
            return result
        except Exception:
            self.close()
            raise
        finally:
            self.lock.release()

    def stop(self):
        if not self.lock.acquire(blocking=False):
            raise ValueError('An environment is starting; please wait')
        try:
            self.close()
            return {'stopped': True}
        finally:
            self.lock.release()

    def status(self):
        running = self.task is not None and (self.static is not None or self.streaming.alive())
        return {'task_id': self.task, 'running': running,
                'unreal_available': sys.platform == 'linux',
                'boundary_state': self.streaming.boundary() if running else None,
                'build': self.build if running else None,
                'transport': 'pixel-streaming' if self.streaming.session_id else None}

    def request(self, path, data=None):
        if self.port is None:
            raise ValueError('Open an environment first')
        request = urllib.request.Request(f'http://127.0.0.1:{self.port}{path}', data=data,
                                         headers={'Content-Type':'application/json'} if data else {})
        try:
            response = urllib.request.urlopen(request,timeout=200)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status, response.headers.get('Content-Type','application/octet-stream'), response.read()


def make_handler(viewer):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*unused):
            pass

        def reply(self,status,data,content_type='application/json'):
            if not isinstance(data,bytes):
                data = json.dumps(data).encode()
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.end_headers()
            try:self.wfile.write(data)
            except (BrokenPipeError,ConnectionResetError):pass

        def do_GET(self):
            path=urlparse(self.path).path
            if path=='/':
                self.reply(200,(ROOT/'environments/task_viewer.html').read_bytes(),'text/html; charset=utf-8')
            elif path=='/task_viewer.js':
                self.reply(200,(ROOT/'environments/task_viewer.js').read_bytes(),'text/javascript; charset=utf-8')
            elif path=='/api/tasks':
                self.reply(200,viewer.rows)
            elif path=='/api/status':
                self.reply(200,viewer.status())
            elif path.startswith('/stream/'):
                try:
                    proxy_stream(self, viewer.streaming)
                except OSError:
                    if not getattr(self, 'stream_upgraded', False):
                        self.reply(502, {'error': 'Streaming connection closed'})
            elif self.path.startswith('/environment/'):
                try:
                    status,kind,data=viewer.request(self.path[len('/environment'):])
                    self.reply(status,data,kind)
                except Exception as exc:self.reply(502,{'error':str(exc)})
            else:self.reply(404,{'error':'Unknown route'})

        def do_POST(self):
            # Loopback UI writes must originate from this viewer, not another website.
            origin=self.headers.get('Origin')
            if origin and origin != 'http://'+self.headers.get('Host',''):
                self.reply(403,{'error':'Origin mismatch'});return
            if self.headers.get('Content-Type','').split(';')[0] != 'application/json':
                self.reply(415,{'error':'Use application/json'});return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<65536:raise ValueError('Invalid request size')
                raw=self.rfile.read(length)
                data=json.loads(raw)
                if self.path=='/api/open':
                    self.reply(200,viewer.open(data['task_id']))
                elif self.path=='/api/stop':
                    self.reply(200,viewer.stop())
                else:self.reply(404,{'error':'Unknown route'})
            except Exception as exc:self.reply(400,{'error':str(exc)})
    return Handler


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task',nargs='?',help='Initially selected task')
    parser.add_argument('--list',action='store_true')
    parser.add_argument('--dataset',type=Path)
    parser.add_argument('--download',action='store_true',help='Download selected environments when opened')
    parser.add_argument('--runtime-root',type=Path,default=DEFAULT_RUNTIME)
    parser.add_argument('--gpu',type=int,default=0)
    parser.add_argument('--port',type=int,default=19100)
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--pixel-streaming-root',type=Path,default=ROOT/'out/pixel-streaming',
                        help='Built Epic UE 5.6 PixelStreamingInfrastructure checkout')
    native = parser.add_mutually_exclusive_group()
    native.add_argument('--unreal-profiles',type=Path,help='Use existing verified Unreal launch profiles')
    native.add_argument('--unreal-packages',type=Path,help='A self-contained environment package or directory of packages with launch.json')
    parser.add_argument('--node',default='node',help='Node.js 22+ executable')
    parser.add_argument('--ice-config',type=Path,help='Private JSON RTCConfiguration with STUN/TURN iceServers')
    args=parser.parse_args(argv)
    if sys.platform == 'linux':
        # Packaged UE networking expects a bounded descriptor limit.
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        if soft == resource.RLIM_INFINITY or soft > 4096:
            resource.setrlimit(resource.RLIMIT_NOFILE, (4096, hard))
    catalog=task_catalog()
    if args.list:
        for tid,task in catalog.items():print(f"{tid:10} {task['family']:20} {task['paper_subcategory']}")
        return 0
    if args.task and args.task not in catalog:parser.error('Unknown task ID')
    peer_options = json.loads(args.ice_config.expanduser().read_text()) if args.ice_config else None
    if peer_options is not None and (not isinstance(peer_options, dict) or not isinstance(peer_options.get('iceServers'), list)):
        parser.error('--ice-config must contain a JSON object with an iceServers array')
    viewer=Viewer(load_rows(args.dataset),args.runtime_root.expanduser().resolve(),args.download,args.gpu,
                  streaming_root=args.pixel_streaming_root, profiles=args.unreal_profiles,
                  node=args.node, peer_options=peer_options, packages=args.unreal_packages)
    server=http.server.ThreadingHTTPServer(('127.0.0.1',args.port),make_handler(viewer))
    url=f'http://127.0.0.1:{server.server_port}/'+('?' + urlencode({'task':args.task}) if args.task else '')
    print(url,flush=True)
    if not args.no_browser:webbrowser.open(url)
    def terminate(*unused):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, terminate)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        # Wait for an in-flight startup before releasing its owned processes.
        with viewer.lock:
            viewer.close()
        server.server_close()
    return 0


if __name__=='__main__':
    raise SystemExit(main())
