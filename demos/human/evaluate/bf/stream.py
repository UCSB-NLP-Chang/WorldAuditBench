"""Authenticated, bounded loopback proxy for an isolated Pixel Streaming slot."""
import http.client
import re
import select
import socket
from urllib.parse import urlsplit

from .common import require


def proxy(handler, user):
    parsed = urlsplit(handler.path)
    match = re.fullmatch(r'/stream/([a-f0-9]{32})/(.*)', parsed.path)
    require(match is not None, 'Invalid stream path', 404)
    sid, tail = match.groups()
    port = handler.server.runtime.authorize(user, sid)
    require('..' not in tail and not tail.startswith('/'), 'Invalid stream asset', 404)
    if handler.headers.get('Upgrade', '').lower() == 'websocket':
        require(handler.headers.get('Origin') == handler.server.config['origin'], 'Invalid stream origin', 403)
        with socket.create_connection(('127.0.0.1', port), timeout=5) as upstream:
            headers = ['GET / HTTP/1.1', f'Host: 127.0.0.1:{port}', 'Connection: Upgrade', 'Upgrade: websocket']
            for key in ('Sec-WebSocket-Key', 'Sec-WebSocket-Version', 'Sec-WebSocket-Protocol'):
                if handler.headers.get(key):
                    headers.append(key + ': ' + handler.headers[key])
            upstream.sendall(('\r\n'.join(headers) + '\r\n\r\n').encode())
            handshake = b''
            while not handshake.endswith(b'\r\n\r\n'):
                part = upstream.recv(1)
                require(part and len(handshake) < 16384, 'Invalid signalling response', 502)
                handshake += part
            require(b' 101 ' in handshake.split(b'\r\n', 1)[0], 'Signalling unavailable', 502)
            handler.connection.sendall(handshake)
            handler.close_connection = True
            upstream.settimeout(2)
            handler.connection.settimeout(2)
            handler.server.runtime.stream_connected(sid)
            try:
                while True:
                    try:
                        handler.server.runtime.authorize(handler.user(), sid)
                        readable, _, _ = select.select([upstream, handler.connection], [], [], 1)
                        for source in readable:
                            data = source.recv(65536)
                            if not data:
                                return
                            (handler.connection if source is upstream else upstream).sendall(data)
                    except Exception:
                        return
            finally:
                handler.server.runtime.stream_disconnected(sid)
    else:
        require(tail in ('', 'player.html', 'player.js', '43ef81525e6853dc.ico') or re.fullmatch(r'(?:css|images)/[a-zA-Z0-9_.\-/]+', tail), 'Stream asset not found', 404)
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
        try:
            connection.request('GET', '/' + (tail or 'player.html'), headers={'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            body = response.read(32 * 1024 * 1024 + 1)
            require(len(body) <= 32 * 1024 * 1024, 'Stream asset too large', 502)
            mime = response.getheader('Content-Type', 'application/octet-stream')
            if 'text/html' in mime:
                html = body.decode()
                html = re.sub(r'<link[^>]+https://fonts\.(?:googleapis|gstatic)\.com[^>]*>', '', html)
                html = html.replace('<head>', '<head><script src="/static/input-bridge.js"></script><script src="/static/capture-bridge.js"></script>', 1)
                body = html.encode()
            handler.reply(response.status, body, mime=mime, stream=True)
        finally:
            connection.close()
