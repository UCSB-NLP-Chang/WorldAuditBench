#!/usr/bin/env python3
"""Serve the pinned Three.js release using the review site's existing login."""
import argparse
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
from urllib.parse import unquote, urlsplit


class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        route = unquote(urlsplit(self.path).path)
        if route == '/health':
            self.send_response(200)
            self.end_headers()
            return
        if not route.startswith('/threejs/'):
            self.send_error(404)
            return
        connection = http.client.HTTPConnection('127.0.0.1', 8092, timeout=5)
        try:
            connection.request('GET', '/api/me', headers={'Cookie': self.headers.get('Cookie', '')})
            authenticated = connection.getresponse().status == 200
        except OSError:
            self.send_error(503, 'Review login service unavailable')
            return
        finally:
            connection.close()
        if not authenticated:
            body = ('<!doctype html><meta charset="utf-8"><title>Sign in</title>'
                    '<main style="font:18px system-ui;max-width:620px;margin:12vh auto;padding:24px">'
                    '<h1>请先登录 / Sign in first</h1>'
                    '<p>使用原评审网站的姓名和口令登录，再从导航栏进入 Three.js environments。</p>'
                    '<a href="/">前往登录 / Open sign in</a></main>').encode()
            self.send_response(401)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)
            return
        name = route.removeprefix('/threejs/') or 'index.html'
        if name not in self.server.allowed:
            self.send_error(404)
            return
        target = self.server.root / name
        compressed = 'gzip' in self.headers.get('Accept-Encoding', '') and target.with_suffix(target.suffix + '.gz').is_file()
        if compressed:
            target = target.with_suffix(target.suffix + '.gz')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8' if name.endswith('.html') else 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(target.stat().st_size))
        self.send_header('Cache-Control', 'private, no-store')
        self.send_header('Vary', 'Accept-Encoding, Cookie')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        if compressed:
            self.send_header('Content-Encoding', 'gzip')
        self.end_headers()
        if self.command != 'HEAD':
            try:
                with target.open('rb') as source:
                    shutil.copyfileobj(source, self.wfile)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def log_message(self, fmt, *args):
        # Do not log query strings or authentication headers.
        print(f'{self.command} {urlsplit(self.path).path}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('--port', type=int, default=8094)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.root = args.root.resolve()
    server.allowed = {p.name for p in server.root.glob('*_constrained.html')} | {'index.html', 'bugs.html', 'SHA256SUMS'}
    server.serve_forever()
