"""Serve only the current session's sanitized, self-contained Three.js bundle."""
import gzip
import json
import pathlib
import re
from urllib.parse import urlsplit
from .common import require


def serve(handler, user):
    match = re.fullmatch(r'/browser/([a-f0-9]{32})/(|assets.json)', urlsplit(handler.path).path)
    require(match is not None, 'Environment asset not found', 404)
    sid, asset = match.groups()
    task = handler.server.runtime.authorize_browser(user, sid)
    root = pathlib.Path(handler.server.runtime.c['browser_root'])
    bundle = root / task['bundle']
    if (bundle / 'native.html.gz').exists():
        require(not asset, 'Environment asset not found', 404)
        query = (root / 'configs' / (task['config_id'] + '.json')).read_text()
        body = gzip.decompress((bundle / 'native.html.gz').read_bytes()).replace(b'__BF_QUERY_VALUE__', query.encode())
        if 'gzip' in handler.headers.get('Accept-Encoding', ''):
            return handler.reply(200, gzip.compress(body, compresslevel=3), mime='text/html; charset=utf-8', headers={'Content-Encoding': 'gzip'}, stream=True)
        return handler.reply(200, body, mime='text/html; charset=utf-8', stream=True)
    if asset:
        data = (bundle / 'assets.json.gz').read_bytes()
        if 'gzip' in handler.headers.get('Accept-Encoding', ''):
            return handler.reply(200, data, mime='application/json', headers={'Content-Encoding': 'gzip'}, stream=True)
        return handler.reply(200, gzip.decompress(data), mime='application/json', stream=True)
    config = (root / 'configs' / (task['config_id'] + '.json')).read_text()
    html = (bundle / 'template.html').read_text().replace('__BF_CONFIG__', config.replace('<', r'\u003c'))
    return handler.reply(200, html.encode(), mime='text/html; charset=utf-8', stream=True)
