"""Serve one verified build-host Urban episode for a real MCP transport check."""
import argparse
import json
from pathlib import Path
import signal
import socket

from environment_server import Environment, serve
from remote_unreal import PinnedBackend, task_launch_map


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work', type=Path, required=True)
    p.add_argument('--task', required=True)
    p.add_argument('--port', type=int, default=49318)
    p.add_argument('--gpu', type=int, default=0)
    a = p.parse_args()
    with socket.socket() as s:
        s.bind(('127.0.0.1', a.port))
    item = next(v for v in json.loads((a.work/'qa-profiles.json').read_text()) if v['task']['id'] == a.task)
    state = a.work / 'mcp-episodes'
    state.mkdir(exist_ok=True)
    map_name, launch_map = task_launch_map(item['task'])
    backend = PinnedBackend(item['binary'], map_name, a.task,
                            ['-vulkan', '-sm6', f'-graphicsadapter={a.gpu}', *item['extra_args']],
                            {}, state, launch_map=launch_map)

    class Identified(Environment):
        def health(self):
            return {**super().health(), 'task_id': a.task, 'sampling_interval_seconds': .5,
                    'build_sha256': json.loads((a.work/'build.json').read_text())['binary_sha256']}

    env = Identified(backend, {'regions': [{'id': 'scene', 'map': map_name}]},
                     {'tasks': [{'id': a.task, 'region': 'scene'}]})

    def stop(*unused):
        raise KeyboardInterrupt

    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        signal.signal(sig, stop)
    try:
        print('Serving private QA episode', a.task, flush=True)
        serve(env, a.port)
    except KeyboardInterrupt:
        pass
    finally:
        backend.close()


if __name__ == '__main__':
    main()
