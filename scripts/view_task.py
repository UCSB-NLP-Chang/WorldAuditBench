#!/usr/bin/env python3
"""Browse task inputs, rubrics and interactive environments locally."""
import argparse
import functools
import hashlib
import http.server
import json
from pathlib import Path
import socket
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from urllib.parse import urlencode, urlparse
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from data.tasks import ensure_dataset, load_task
from scripts.runtime import DEFAULT_RUNTIME, ensure_environment, server_command, stop, task_catalog, wait_ready


def load_rows(dataset=None):
    path = dataset or ensure_dataset()
    return [load_task(tid, path) for tid in task_catalog()]


class Viewer:
    def __init__(self, rows, runtime, download=False, gpu=0):
        self.rows = rows
        self.tasks = {row['task_id']: row for row in rows}
        self.runtime, self.download, self.gpu = runtime, download, gpu
        self.process = self.static = self.log = None
        self.port = None
        self.task = None
        self.lock = threading.Lock()

    def close(self):
        stop(self.process)
        self.process = None
        if self.static:
            self.static.shutdown()
            self.static.server_close()
            self.static = None
        if self.log:
            self.log.close()
            self.log = None
        self.task = None
        self.port = None

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
            package = ensure_environment(task, self.runtime, self.download)
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
            with socket.socket() as sock:
                sock.bind(('127.0.0.1',0))
                self.port = sock.getsockname()[1]
            logs = ROOT / 'out/viewer';logs.mkdir(parents=True,exist_ok=True)
            self.log = (logs/(task+'.log')).open('wb')
            self.process = subprocess.Popen(server_command(task,self.runtime,self.gpu,self.port),
                                            stdout=self.log,stderr=subprocess.STDOUT)
            wait_ready(self.process,self.port)
            self.task = task
            return {'engine':'unreal','task_id':task}
        except Exception:
            self.close()
            raise
        finally:
            self.lock.release()

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
            elif path=='/api/tasks':
                self.reply(200,viewer.rows)
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
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<65536:raise ValueError('Invalid request size')
                raw=self.rfile.read(length)
                data=json.loads(raw)
                if self.path=='/api/open':
                    self.reply(200,viewer.open(data['task_id']))
                elif self.path in {'/api/reset','/api/step','/api/observe'}:
                    status,kind,body=viewer.request(self.path.removeprefix('/api'),raw)
                    self.reply(status,body,kind)
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
    args=parser.parse_args(argv)
    catalog=task_catalog()
    if args.list:
        for tid,task in catalog.items():print(f"{tid:10} {task['family']:20} {task['paper_subcategory']}")
        return 0
    if args.task and args.task not in catalog:parser.error('Unknown task ID')
    viewer=Viewer(load_rows(args.dataset),args.runtime_root.expanduser().resolve(),args.download,args.gpu)
    server=http.server.ThreadingHTTPServer(('127.0.0.1',args.port),make_handler(viewer))
    url=f'http://127.0.0.1:{server.server_port}/'+('?' + urlencode({'task':args.task}) if args.task else '')
    print(url,flush=True)
    if not args.no_browser:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        server.server_close();viewer.close()
    return 0


if __name__=='__main__':
    raise SystemExit(main())
