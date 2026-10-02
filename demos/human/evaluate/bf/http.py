"""Transport layer. Explicit per-app routes keep private evaluation data unreachable."""
import hmac
import http.cookies
import json
import pathlib
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

from .common import Problem, canonical, require
from .delivery import evidence_fetcher
from .stream import proxy

WEB = pathlib.Path(__file__).resolve().parents[1] / 'web'


class Handler(BaseHTTPRequestHandler):
    server_version = 'BugFinding/1'

    def log_message(self, *args):
        pass

    def token(self):
        cookie = http.cookies.SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
            return cookie[self.server.cookie].value if self.server.cookie in cookie else ''
        except http.cookies.CookieError:
            return ''

    def user(self):
        return self.server.store.authenticate(self.token())

    def reply(self, status, data, mime='application/json; charset=utf-8', headers=None, stream=False):
        body = data if isinstance(data, bytes) else canonical(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        csp = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'"
        if stream:
            csp = "default-src 'self' blob: data:; script-src 'self' blob: 'unsafe-inline' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; connect-src 'self' blob: data:; worker-src 'self' blob:; object-src 'none'; frame-ancestors 'self'"
        self.send_header('Content-Security-Policy', csp)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        require(self.headers.get('Content-Type', '').split(';')[0] == 'application/json', 'JSON required', 415)
        n = int(self.headers.get('Content-Length', '0'))
        require(0 < n <= 8 * 1024 * 1024, 'Request too large', 413)
        data = json.loads(self.rfile.read(n))
        require(isinstance(data, dict), 'JSON object required')
        return data

    def internal(self):
        expected = 'Bearer ' + self.server.config['transfer_secret']
        require(self.headers.get('Host', '') in ('127.0.0.1:' + str(self.server.server_port), 'localhost:' + str(self.server.server_port)), 'Internal endpoint', 403)
        require(hmac.compare_digest(self.headers.get('Authorization', ''), expected), 'Unauthorized', 403)

    def do_GET(self):
        self.handle_request('GET')

    def do_POST(self):
        self.handle_request('POST')

    def handle_request(self, method):
        try:
            path = urlsplit(self.path).path
            app, store = self.server.app, self.server.store
            if path.startswith('/internal/'):
                self.internal()
                if path == '/internal/progress' and method == 'POST':
                    from .group_progress import local_metrics
                    return self.reply(200, {'cases':local_metrics(store, app, self.read_json().get('cohort'))})
                if app == 'evaluation' and path == '/internal/submissions' and method == 'POST':
                    return self.reply(200, store.import_submission(self.read_json(), evidence_fetcher(self.server.config)))
                match = re.fullmatch('/internal/submissions/([a-f0-9]{32})/evidence/([a-f0-9]{32})', path)
                if app == 'exploration' and method == 'GET' and match:
                    return self.reply(200, store.evidence(match[2], submission_id=match[1]), mime='image/png')
                raise Problem(404, 'Not found')
            if method == 'GET' and path == '/api/login-users':
                with store.lock:
                    names = [row['name'] for row in store.db.execute('SELECT name FROM users ORDER BY name COLLATE NOCASE')]
                return self.reply(200, {'users': names})
            if method == 'GET' and path == '/health':
                if app == 'exploration' and self.server.runtime:
                    from .runtime import listening
                    require(listening(int(urlsplit(self.server.runtime.c['supervisor_url']).port)), 'Runtime supervisor unavailable', 503)
                return self.reply(200, {'ok': True, 'service': app, 'schema_version': 1})
            if method == 'GET' and path == '/':
                return self.reply(200, (WEB / app / 'index.html').read_bytes(), mime='text/html; charset=utf-8')
            if method == 'GET' and path.startswith('/static/'):
                name = path.removeprefix('/static/')
                shared = {'style.css', 'common.js', 'progress.js', 'case-progress.js', 'example.js', 'example.css'}
                allowed = shared | {'app.js'} | ({'input-bridge.js', 'capture-bridge.js', 'browser-native.js'} if app == 'exploration' else set())
                require(name in allowed, 'Not found', 404)
                file = WEB / ('shared' if name in shared else app) / name
                return self.reply(200, file.read_bytes(), mime='text/css' if name.endswith('.css') else 'text/javascript')
            if method == 'POST':
                require(self.headers.get('Origin') == self.server.config['origin'], '来源不匹配', 403)
                data = self.read_json()
                if path == '/api/login':
                    key = (self.client_address[0], str(data.get('name', ''))[:80])
                    with self.server.auth_lock:
                        now = time.time()
                        recent = [t for t in self.server.login_attempts.get(key, []) if t > now - 60]
                        require(len(recent) < 10, '尝试过于频繁，请稍后再试', 429)
                        self.server.login_attempts[key] = recent + [now]
                    token = store.login(data.get('name'), data.get('password'))
                    secure = '; Secure' if self.server.config['origin'].startswith('https://') else ''
                    return self.reply(200, {'ok': True}, headers={'Set-Cookie': self.server.cookie + '=' + token + '; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200' + secure})
            user = self.user()
            if method == 'GET' and re.fullmatch('/api/examples/[a-f0-9]{32}', path):
                from .examples import example_for
                task_id = path.rsplit('/', 1)[1]
                store.require_access(user, task_id, 'explorer' if app == 'exploration' else 'reviewer')
                return self.reply(200, example_for(task_id))
            if method == 'GET' and path.startswith('/example-images/'):
                from .examples import image
                return self.reply(200, image(path.removeprefix('/example-images/')), mime='image/png')
            if method == 'GET' and path.startswith('/browser/') and app == 'exploration':
                from .browser import serve
                return serve(self, user)
            if method == 'GET' and path.startswith('/stream/') and app == 'exploration':
                return proxy(self, user)
            if method == 'GET' and path == '/api/instructions':
                from .instructions import INSTRUCTIONS
                return self.reply(200, INSTRUCTIONS)
            match = re.fullmatch('/api/instructions/(zh|en)\.md', path)
            if method == 'GET' and match:
                from .instructions import markdown
                return self.reply(200, markdown(match[1]).encode(), mime='text/markdown; charset=utf-8')
            if method == 'GET' and path == '/api/taxonomy':
                from .taxonomy import TAXONOMY
                return self.reply(200, TAXONOMY)
            if method == 'GET' and path == '/api/me':
                return self.reply(200, {'name': user['name'], 'is_admin': bool(user.get('is_admin')), 'is_test': bool(user.get('is_test'))})
            if method == 'GET' and path == '/api/progress':
                from .progress import progress
                query = parse_qs(urlsplit(self.path).query)
                from .group_progress import add_group_progress, peer_metrics
                data = progress(store, app, user, query.get('scope', ['assigned'])[0], query.get('cohort', [None])[0])
                data = add_group_progress(store, app, user, data, peer_metrics(self.server, data['cohort']))
                if app == 'exploration' and self.server.runtime:
                    data['runtime_capacity'] = self.server.runtime.capacity()
                return self.reply(200, data)
            if method == 'POST' and path == '/api/logout':
                if app == 'exploration' and self.server.runtime:
                    self.server.runtime.stop_user(user)
                store.logout(self.token())
                return self.reply(200, {'ok': True}, headers={'Set-Cookie': self.server.cookie + '=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})
            if app == 'exploration':
                if path == '/api/workspace' and method == 'GET':
                    query = parse_qs(urlsplit(self.path).query)
                    aid = query.get('attempt_id', [None])[0]
                    tasks = store.accessible_tasks(user, 'explorer')
                    task_id = query.get('task_id', [tasks[0]['id'] if tasks else None])[0]
                    if aid:
                        attempt = store.snapshot(user, aid)
                        task_id = attempt['task']['id']
                    else:
                        if task_id: store.require_access(user, task_id, 'explorer')
                        attempt = store.snapshot(user, task_id=task_id) if task_id else None
                    return self.reply(200, {'attempt': attempt, 'task': store.task(task_id) if task_id else None})
                if path == '/api/attempts' and method == 'POST':
                    return self.reply(200, store.start_attempt(user, data.get('task_id', self.server.config['task_id'])))
                match = re.fullmatch('/api/attempts/([a-f0-9]{32})/(draft|flags|delete-flag|submit|runtime)', path)
                if match:
                    aid, operation = match.groups()
                    if method == 'GET' and operation == 'runtime':
                        return self.reply(200, self.server.runtime.status(user, aid))
                    if method == 'POST':
                        if operation == 'draft':
                            result = store.save_draft(user, aid, data)
                        elif operation == 'delete-flag':
                            result = store.delete_flag(user, aid, data)
                        elif operation == 'flags':
                            result = store.add_flag(user, aid, data)
                        elif operation == 'submit':
                            result = store.submit(user, aid, data)
                            # Persist answer first. Runtime cleanup failure must not undo submission.
                            self.server.runtime.finish_attempt(user, aid)
                        else:
                            require(data.get('operation') in ('start', 'stop'), 'Invalid operation')
                            result = self.server.runtime.start(user, aid) if data['operation'] == 'start' else self.server.runtime.stop(user, aid)
                        return self.reply(200, result)
                match = re.fullmatch('/api/evidence/([a-f0-9]{32})', path)
                if match and method == 'GET':
                    return self.reply(200, store.evidence(match[1], user=user), mime='image/png')
            else:
                if path == '/api/next' and method == 'POST':
                    return self.reply(200, store.next_submission(user, data.get('exclude_submission_id')))
                if path == '/api/queue' and method == 'GET':
                    return self.reply(200, {'items': store.queue(user)})
                if path == '/api/claim' and method == 'POST':
                    return self.reply(200, store.claim(user, data.get('id')))
                match = re.fullmatch('/api/submissions/([a-f0-9]{32})/(heartbeat|judgment)', path)
                if match and method == 'POST':
                    return self.reply(200, store.claim(user, match[1]) if match[2] == 'heartbeat' else store.save_judgment(user, match[1], data))
                match = re.fullmatch('/api/evidence/([a-f0-9]{32})', path)
                if match and method == 'GET':
                    return self.reply(200, store.evidence(user, match[1]), mime='image/png')
            raise Problem(404, '接口不存在')
        except Problem as exc:
            self.reply(exc.status, {'error': exc.message})
        except (ValueError, KeyError, TypeError):
            self.reply(400, {'error': '请求格式无效'})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            import traceback
            traceback.print_exc()
            self.reply(503, {'error': '服务暂时不可用，数据已保存的部分不会丢失，请稍后重试'})


def make_server(app, store, config, runtime=None):
    server = ThreadingHTTPServer(('127.0.0.1', config['port']), Handler)
    server.daemon_threads = True
    server.app, server.store, server.config, server.runtime = app, store, config, runtime
    server.cookie = 'bf_explore_session' if app == 'exploration' else 'bf_evaluate_session'
    server.auth_lock, server.login_attempts = threading.Lock(), {}
    server.metrics_lock, server.metrics_cache = threading.Lock(), {}
    return server
