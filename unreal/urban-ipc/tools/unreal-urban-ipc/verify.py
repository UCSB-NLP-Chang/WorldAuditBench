"""Render and exercise every active Urban map against the exact live content."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import os
import signal
import subprocess
import time
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--gpu', type=int, default=0)
    parser.add_argument('--task')
    a = parser.parse_args()
    profiles = json.loads((a.work / 'qa-profiles.json').read_text())
    build = json.loads((a.work / 'build.json').read_text())
    results = []
    for item in profiles:
        task = item['task']
        if a.task and task['id'] != a.task:
            continue
        root = a.work / 'qa' / task['id']
        root.mkdir(parents=True, exist_ok=False)
        log = (root / 'stdout.log').open('w')
        cmd = [item['binary'], task['map'], '-RenderOffscreen', '-windowed',
               '-ResX=960', '-ResY=540', '-unattended', '-nosound', '-vulkan', '-sm6',
               '-AuditorServe', '-AuditorRemoteTask=' + task['id'],
               '-AuditorIPC=' + str(root), '-abslog=' + str(root / 'native.log'),
               '-forcelogflush', f'-graphicsadapter={a.gpu}', *item['extra_args']]
        process = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        started = time.monotonic()
        states = []

        def receive(request_id=None):
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                assert process.poll() is None, 'Game exited; see native.log'
                try:
                    state = json.loads((root / 'response.json').read_text())
                except (FileNotFoundError, json.JSONDecodeError):
                    state = {}
                if (state.get('result') == 'ready' if request_id is None else state.get('request_id') == request_id):
                    assert state['paused'] and state['task_id'] == task['id'], state
                    assert state['map'] == task['map'].rsplit('/', 1)[1], state
                    assert state['result'] not in {'capture_failed', 'capture_timeout', 'not_ready'}
                    return state
                time.sleep(.05)
            raise TimeoutError('IPC response timed out')

        def exchange(action, **fields):
            request_id = uuid.uuid4().hex
            command = {'request_id': request_id, 'action': action, **fields}
            temp = root / 'command.json.tmp'
            temp.write_text(json.dumps(command))
            temp.replace(root / 'command.json')
            state = receive(request_id)
            states.append({'action': action, **state})
            return state

        def png(state):
            raw = (root / 'observation.png').read_bytes()
            assert raw.startswith(b'\x89PNG\r\n\x1a\n') and len(raw) > 10000
            assert (state['width'], state['height']) == (960, 540)
            for frame in state['frames']:
                assert (root / frame['file']).read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
            return hashlib.sha256(raw).hexdigest()

        try:
            initial = receive()
            first_hash = png(initial)
            (root / 'initial.png').write_bytes((root / 'observation.png').read_bytes())
            states.append({'action': 'initial', **initial})
            policy_path = next(x.split('=', 1)[1] for x in item['extra_args'] if x.startswith('-AuditorExplorationPolicy='))
            entry = json.loads(Path(policy_path).read_text())['tasks'][task['id']]
            # Policy field names are checked against the native helper's frozen entry.
            spawn = entry['spawn']
            assert math.dist(initial['position_cm'], spawn) < 5, (initial['position_cm'], spawn)
            assert abs((initial['yaw_degree'] - entry['yaw'] + 180) % 360 - 180) < .1
            before = exchange('snapshot')
            time.sleep(1)
            after = exchange('snapshot')
            for key in ('world_time', 'actor_state_digest', 'position_cm'):
                assert before[key] == after[key], ('pause', key)
            turn = exchange('turn', value=90)
            assert abs((turn['yaw_degree'] - initial['yaw_degree'] + 180) % 360 - 180 - 90) < .1
            assert png(turn) != first_hash
            look = exchange('look', value=15)
            assert abs(look['look_degree'] - 15) < .1
            forward = exchange('move_up', value=100)
            backward = exchange('move_down', value=100)
            assert max(forward['actual_distance_cm'], backward['actual_distance_cm']) > 25, 'No verified walking'
            last_time = backward['simulation_time']
            idle = exchange('idle', value=2)
            png(idle)
            assert abs(idle['simulation_time'] - last_time - 2) < .08
            assert len(idle['frames']) == 4, len(idle['frames'])
            times = [f['simulation_time'] - last_time for f in idle['frames']]
            assert all(abs(t - target) < .08 for t, target in zip(times, [.5, 1, 1.5, 2])), times
            interaction = exchange('interact', value=0)
            assert interaction['result'] in {'ok', 'not_interactable'}
            # Leaving the same command in place must not execute it twice.
            time.sleep(.5)
            assert json.loads((root / 'response.json').read_text()) == interaction
            result = {'task': task['id'], 'status': 'PASS', 'seconds': time.monotonic() - started,
                      'idle_frame_times': times, 'max_walk_cm': max(forward['actual_distance_cm'], backward['actual_distance_cm']),
                      'initial_position_cm': initial['position_cm'], 'initial_yaw': initial['yaw_degree']}
        except Exception as error:
            result = {'task': task['id'], 'status': 'FAIL', 'error': repr(error)}
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
            log.close()
            (root / 'states.json').write_text(json.dumps(states, indent=2))
        results.append(result)
        (a.work / ('qa-' + a.task + '.json' if a.task else 'qa.json')).write_text(json.dumps({
            'status': 'PASS' if len(results) == (1 if a.task else len(profiles)) and all(r['status'] == 'PASS' for r in results) else 'INCOMPLETE',
            'binary_sha256': build['binary_sha256'], 'results': results}, indent=2))
        print(json.dumps(result), flush=True)
    assert all(r['status'] == 'PASS' for r in results), 'See per-task QA reports'


if __name__ == '__main__':
    main()
