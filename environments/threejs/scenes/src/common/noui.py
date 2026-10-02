"""Shared "noui" block for the environment pages (the review site's clean view, `?bug=<case>&noui=1`).

`inject_noui(html, keys)` puts src/common/noui_block.html into the page head (idempotent: an existing block is
replaced) with the family's list of key codes that must never reach the page - keys that would change the world or
the camera in ways the agent cannot (answer beacons, fly, third person, jump, weather, debug console, scenario
restart).  Used by every build script and by the release relayer.
"""
import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
BLOCK_RE = re.compile(r'<!-- noui-block.*?<script id="noui-script">.*?</script>\n?', re.S)
KEYS = {
    'packed': ['KeyV', 'KeyF'],              # sponza / house: collider + answer beacons, fly
    'water': [],                             # reef: R = back to start only (same as the site's reset)
    'cottage': ['KeyV', 'Space'],            # third-person toggle, jump
    'sketch': ['KeyV', 'KeyR'],              # third-person toggle, Shift+R scenario restart
    'fable': ['KeyR', 'KeyT', 'Backquote'],  # atmosphere shift, HUD chrome, world console
}


def noui_block(keys=()):
    return (HERE / 'noui_block.html').read_text(encoding='utf-8').replace('__NOUI_KEYS__', json.dumps(list(keys)))


def inject_noui(html, keys=()):
    html = BLOCK_RE.sub('', html)
    i = html.index('</head>')   # the first </head> is the real one
    return html[:i] + noui_block(keys) + html[i:]
