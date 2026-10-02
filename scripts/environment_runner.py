#!/usr/bin/env python3
"""Run a task from a self-contained WorldAuditBench environment package."""
import argparse
import functools
import http.server
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlencode
import webbrowser


def main():
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / 'launch.json').read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('task', nargs='?')
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--gpu', type=int, default=0)
    parser.add_argument('--headless', action='store_true')
    args, extra = parser.parse_known_args()
    tasks = manifest['tasks']
    if args.list:
        print('\n'.join(tasks))
        return 0
    task = args.task
    if not task:
        if sys.stdin.isatty():
            print('Tasks: ' + ', '.join(tasks))
            task = input('Task ID [' + next(iter(tasks)) + ']: ').strip() or next(iter(tasks))
        else:
            parser.error('Choose a task ID; use --list to see available tasks')
    if task not in tasks:
        parser.error('Unknown task: ' + task)
    spec = tasks[task]
    if manifest['engine'] == 'three.js':
        if extra:
            parser.error('Unrecognized arguments: ' + ' '.join(extra))
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root / 'runtime'))
        server = http.server.ThreadingHTTPServer(('127.0.0.1', args.port), handler)
        query = urlencode({'bug': spec['case'], 'noui': 1, 'seed': 5})
        url = f'http://127.0.0.1:{server.server_port}/{spec["page"]}?{query}'
        print(url, flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    if sys.platform != 'linux':
        parser.error('This Unreal package requires Linux x86_64 and a Vulkan-capable GPU')
    import resource
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    if soft == resource.RLIM_INFINITY or soft > 4096:
        resource.setrlimit(resource.RLIMIT_NOFILE, (4096, hard))
    binary = root / spec['binary']
    command = [str(binary), spec['launch_map'], f'-graphicsadapter={args.gpu}',
               '-windowed', '-ResX=1280', '-ResY=720', *spec.get('args', [])]
    if args.headless:
        command += ['-RenderOffscreen', '-unattended', '-nosound']
    command += extra
    return subprocess.call(command, cwd=binary.parent, env=os.environ.copy())


if __name__ == '__main__':
    raise SystemExit(main())
