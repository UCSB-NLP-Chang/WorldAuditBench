"""Same-origin HTTP/WebSocket forwarding for the viewer's active stream only."""
import http.client
import re
import select
import socket
from urllib.parse import unquote, urlsplit


def proxy(handler, stream):
    parsed = urlsplit(handler.path)
    match = re.fullmatch(r'/stream/([0-9a-f]{32})/(.*)', parsed.path)
    if not match or stream is None or match[1] != stream.session_id or not stream.alive():
        return handler.reply(404, {'error': 'Stream is no longer active'})
    session_id, tail = match.groups()
    if '..' in unquote(tail).split('/') or '\\' in unquote(tail):
        return handler.reply(400, {'error': 'Invalid stream path'})
    port = stream.player_port
    if handler.headers.get('Upgrade', '').lower() == 'websocket':
        if handler.headers.get('Origin') != 'http://' + handler.headers.get('Host', ''):
            return handler.reply(403, {'error': 'Origin mismatch'})
        with socket.create_connection(('127.0.0.1', port), timeout=5) as upstream:
            headers = ['GET / HTTP/1.1', f'Host: 127.0.0.1:{port}',
                       'Connection: Upgrade', 'Upgrade: websocket']
            for name in ['Sec-WebSocket-Key', 'Sec-WebSocket-Version', 'Sec-WebSocket-Protocol']:
                if handler.headers.get(name):
                    headers.append(name + ': ' + handler.headers[name])
            upstream.sendall(('\r\n'.join(headers) + '\r\n\r\n').encode())
            handshake = b''
            while not handshake.endswith(b'\r\n\r\n'):
                chunk = upstream.recv(1)
                if not chunk or len(handshake) > 16384:
                    return handler.reply(502, {'error': 'Invalid signalling response'})
                handshake += chunk
            if b' 101 ' not in handshake.split(b'\r\n', 1)[0]:
                return handler.reply(502, {'error': 'Signalling upgrade failed'})
            handler.connection.sendall(handshake)
            handler.stream_upgraded = True
            handler.close_connection = True
            upstream.settimeout(5)
            handler.connection.settimeout(5)
            try:
                while stream.session_id == session_id and stream.alive():
                    readable, _, _ = select.select([upstream, handler.connection], [], [], 1)
                    for source in readable:
                        data = source.recv(65536)
                        if not data:
                            return
                        (handler.connection if source is upstream else upstream).sendall(data)
            except OSError:
                pass
        return
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=15)
    try:
        target = '/' + (tail or 'player.html') + ('?' + parsed.query if parsed.query else '')
        connection.request('GET', target, headers={'Accept-Encoding': 'identity'})
        response = connection.getresponse()
        body = response.read(32 * 1024 * 1024 + 1)
        if len(body) > 32 * 1024 * 1024:
            return handler.reply(502, {'error': 'Stream asset is too large'})
        content_type = response.getheader('Content-Type', 'application/octet-stream')
        if 'text/html' in content_type:
            body = re.sub(r'((?:src|href)=["\'])/(?!/)', r'\1/stream/' + session_id + '/',
                          body.decode()).encode()
        handler.reply(response.status, body, content_type)
    finally:
        connection.close()
