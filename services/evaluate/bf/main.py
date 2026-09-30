"""One process per application; separate configs and persistent roots."""
import argparse
import json
import os
import pathlib
import signal
import subprocess
import sys
import threading

from .delivery import deliver_pending
from .evaluation import EvaluationStore
from .exploration import ExplorationStore
from .http import make_server
from .runtime import Runtime


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('app', choices=['exploration', 'evaluation'])
    parser.add_argument('config')
    args = parser.parse_args()
    os.umask(0o077)
    config = json.loads(pathlib.Path(args.config).read_text())
    store = ExplorationStore(config['state_dir']) if args.app == 'exploration' else EvaluationStore(config['state_dir'])
    runtime, children = None, []
    stop = threading.Event()
    if args.app == 'exploration':
        for task in config.get('tasks', [config['task']]):
            store.register_task(task)
        runtime = Runtime(store, config['runtime'])
        if config.get('supervisor_config'):
            supervisor_config = pathlib.Path(config['supervisor_config'])
            c = json.loads(supervisor_config.read_text())
            if c.get('turn_argv'):
                children.append(subprocess.Popen(c['turn_argv'], env={**os.environ, **c.get('turn_env', {})}))
            children.append(subprocess.Popen([sys.executable, '-m', 'bf.runtime_supervisor', str(supervisor_config)]))
    else:
        for reference in config['references']:
            store.register_reference(reference)
    server = make_server(args.app, store, config, runtime)
    def check_children():
        if any(child.poll() is not None for child in children):
            raise RuntimeError('A pilot runtime dependency exited')
    server.service_actions = check_children

    def loop(fn, interval):
        while not stop.wait(interval):
            try:
                fn()
            except Exception:
                import traceback
                traceback.print_exc()

    if runtime:
        threading.Thread(target=loop, args=(runtime.tick, 2), daemon=True).start()
        threading.Thread(target=loop, args=(lambda: deliver_pending(store, config), 3), daemon=True).start()

    def terminate(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, terminate)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
        if runtime:
            try:
                runtime.stop()
            except Exception:
                pass
        for child in reversed(children):
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()


if __name__ == '__main__':
    main()
