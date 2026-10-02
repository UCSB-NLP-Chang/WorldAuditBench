"""Loopback-only, owner-checked HTTP/WebSocket gateway for Pixel Streaming slots."""
import http.client,re,select,socket,time
from urllib.parse import urlparse


def proxy(handler):
    match=re.fullmatch(r'/stream/([0-9a-f]{32})/(.*)',urlparse(handler.path).path)
    if not match:return handler.reply(404,{'error':'Invalid stream path'})
    sid,tail=match.groups();user=handler.user();store=handler.store
    def authorized():
        with store.lock:
            row=store.stream_session(sid,user)
            if row['status'] not in ('ready','switching') or row['mode']!='external':raise PermissionError('Session not active')
            if hasattr(store,'shared_runtime'):store.shared_runtime.port(row)
            return row
    try:row=authorized()
    except PermissionError:return handler.reply(403,{'error':'Session not active'})
    ports=getattr(handler.server,'stream_ports',[])
    if row['slot'] is None or (not hasattr(store,'shared_runtime') and row['slot']>=len(ports)):return handler.reply(503,{'error':'Stream gateway not configured'})
    try:port=store.shared_runtime.port(row) if hasattr(store,'shared_runtime') else ports[row['slot']]
    except Exception:return handler.reply(403,{'error':'Stream lease is not active'})
    parsed=urlparse(handler.path);target='/'+tail
    if tail=='ws':target='/'
    if parsed.query:target+='?'+parsed.query
    upgrade=handler.headers.get('Upgrade','').lower()=='websocket'
    if upgrade:
        if handler.headers.get('Origin')!=handler.server.public_origin:return handler.reply(403,{'error':'Stream origin mismatch'})
        upstream=socket.create_connection(('127.0.0.1',port),timeout=5)
        tracked=False
        try:
            headers=[f'GET {target} HTTP/1.1',f'Host: 127.0.0.1:{port}','Connection: Upgrade','Upgrade: websocket']
            for key in ('Sec-WebSocket-Key','Sec-WebSocket-Version','Sec-WebSocket-Protocol'):
                value=handler.headers.get(key)
                if value:headers.append(key+': '+value)
            headers.append('Origin: '+handler.server.public_origin)
            upstream.sendall(('\r\n'.join(headers)+'\r\n\r\n').encode())
            handshake=b''
            # Read exact handshake so early WS frames aren't lost in a HTTP buffer.
            while not handshake.endswith(b'\r\n\r\n'):
                part=upstream.recv(1)
                if not part or len(handshake)>16384:raise ConnectionError('Invalid upstream upgrade')
                handshake+=part
            if b' 101 ' not in handshake.split(b'\r\n',1)[0]:return handler.reply(502,{'error':'Signalling upgrade failed'})
            handler.connection.sendall(handshake);handler.close_connection=True
            store.stream_connected(sid);tracked=True
            upstream.settimeout(2);handler.connection.settimeout(2)
            last_check=time.monotonic()
            while True:
                if time.monotonic()-last_check>1:
                    try:authorized();store.auth_cookie_for_gateway(user)
                    except Exception:break
                    last_check=time.monotonic()
                sockets,_,_=select.select([upstream,handler.connection],[],[],1)
                for source in sockets:
                    data=source.recv(65536)
                    if not data:return
                    destination=handler.connection if source is upstream else upstream
                    destination.sendall(data)
        except (ConnectionError,OSError):pass
        finally:
            upstream.close();handler.close_connection=True
            if tracked:store.stream_disconnected(sid)
        return
    connection=http.client.HTTPConnection('127.0.0.1',port,timeout=10)
    try:
        connection.request('GET',target,headers={'Accept-Encoding':'identity','Host':f'127.0.0.1:{port}'})
        response=connection.getresponse();body=response.read(32*1024*1024+1)
        if len(body)>32*1024*1024:return handler.reply(502,{'error':'Stream asset too large'})
        content_type=response.getheader('Content-Type','application/octet-stream')
        if 'text/html' in content_type:
            text=body.decode('utf-8')
            text=re.sub(r'<link[^>]+https://fonts\.(?:googleapis|gstatic)\.com[^>]*>', '', text)
            # Keep absolute asset references behind the session owner gateway.
            text=re.sub(r'((?:src|href)=["\'])/(?!/)',r'\1/stream/'+sid+'/',text)
            text=text.replace('<head>','<head><script src="/review-bridge.js"></script>',1)
            body=text.encode()
        handler.send_response(response.status);handler.send_header('Content-Type',content_type)
        handler.send_header('Content-Length',str(len(body)));handler.send_header('Cache-Control','no-store')
        handler.send_header('X-Content-Type-Options','nosniff');handler.send_header('Referrer-Policy','same-origin')
        ws_origin=handler.server.public_origin.replace('http://','ws://').replace('https://','wss://')
        handler.send_header('Content-Security-Policy',f"default-src 'self' blob: data:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self' {ws_origin}; frame-ancestors 'self'")
        handler.end_headers();handler.wfile.write(body)
    finally:connection.close()
