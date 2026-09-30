#!/usr/bin/env python3
"""Render industrial cases, exercise view triggers, and verify clean resets in one process."""
import json
import math
import os
from pathlib import Path
import subprocess
import time
import uuid
from PIL import Image, ImageStat

ROOT = Path('/home/ubuntu/unreal-auditor/industrial-workspace')
OUT = ROOT / 'out/render-review'
OUT.mkdir(parents=True, exist_ok=True)
BINARY = ROOT / 'dist/industrial-linux/Linux/FactoryEnvironmentCollect/Binaries/Linux/FactoryEnvironmentCollect'
TASKS = json.loads((ROOT / 'environments/industrial-factory/tasks.json').read_text())['tasks']


def request(**fields):
    request_id = uuid.uuid4().hex
    temporary = OUT / 'command.tmp'
    temporary.write_text(json.dumps(dict(request_id=request_id, **fields)))
    temporary.replace(OUT / 'command.json')
    start = time.monotonic()
    while time.monotonic() - start < 90:
        try:
            response = json.loads((OUT / 'response.json').read_text())
            if response['request_id'] == request_id and response['status'] != 'switching':
                assert response['status'] == 'ready', response['status']
                return response
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        time.sleep(.1)
    raise RuntimeError('Timed out: ' + str(fields))


def capture(name):
    response = request(action='capture')
    path = OUT / (response['request_id'] + '.png')
    start = time.monotonic()
    while not path.exists():
        assert time.monotonic() - start < 20, 'Screenshot missing'
        time.sleep(.1)
    time.sleep(.2)
    image = Image.open(path).convert('RGB')
    assert image.size == (1280, 720), image.size
    scene = ImageStat.Stat(image.crop((128, 160, 1050, 660)))
    assert max(scene.stddev) > 8 and max(scene.mean) > 5, 'Blank scene frame'
    path.replace(OUT / (name + '.png'))


def view(position, aim):
    request(action='view', position=position, aim=aim)
    time.sleep(.45)


def target(snapshot, task):
    return next(actor for actor in snapshot['actors'] if actor['tag'] == 'auditor_actor:' + task['target'])


def stable_state(snapshot):
    # Untouched native physics props may settle slightly differently. Their
    # visibility, collision, material and simulation state must still restore.
    result = []
    for actor in snapshot['actors']:
        state = {key: value for key, value in actor.items()
                 if not (actor.get('simulating') and key == 'transform')}
        # These two native ventilation propellers rotate continuously in the
        # original scene. Compare their position/scale, not animation phase.
        if actor['tag'] in ('auditor_actor:SM_AirConditioningPropeller_2', 'auditor_actor:SM_AirConditioningPropeller_3'):
            position, rotation, scale = state['transform'].split('|')
            state['transform'] = position + '|native rotation|' + scale
        result.append(state)
    return sorted(result, key=lambda actor: actor['tag'])


def main():
    results = []
    golden = {}
    with (OUT / 'game.log').open('w') as stream:
        process = subprocess.Popen([str(BINARY), TASKS[0]['map'], '-RenderOffscreen', '-vulkan', '-sm5',
            '-ResX=1280', '-ResY=720', '-ForceRes', '-nosound', '-unattended', '-AuditorRemoteInput',
            '-AuditorReviewDiagnostics', '-AuditorReviewIPC=' + str(OUT), '-ExecCmds=t.MaxFPS 30'],
            stdout=stream, stderr=subprocess.STDOUT, env=dict(os.environ, DISPLAY=':99'))
        try:
            initial = request(action='snapshot')
            for task in TASKS:
                task_id = task['id']
                clean = request(action='switch', map=task['map'], task='baseline')
                clean_state = stable_state(clean)
                if task['map'] not in golden:
                    golden[task['map']] = clean_state
                    time.sleep(3)
                    capture(task['region'] + '-baseline')
                assert clean_state == golden[task['map']], ('Dirty before task', task_id)
                aim = task.get('review_aim', task.get('position'))
                view(task['probe'], aim)
                capture(task_id + '-clean')
                bug = request(action='switch', map=task['map'], task=task_id)
                view(task['probe'], aim)
                first = request(action='snapshot')
                kind = task['kind']
                if kind == 'view_cull':
                    assert target(first, task)['hidden']
                    capture(task_id + '-center')
                    p = task['probe']; dx = aim[0] - p[0]; dy = aim[1] - p[1]
                    angle = math.radians(40)
                    view(p, [p[0] + dx * math.cos(angle) - dy * math.sin(angle),
                             p[1] + dx * math.sin(angle) + dy * math.cos(angle), aim[2]])
                    assert not target(request(action='snapshot'), task)['hidden']
                elif kind in ('distance_cull', 'distance_scale'):
                    capture(task_id + '-near')
                    view(task['far_probe'], aim)
                    if kind == 'distance_cull':
                        assert not target(first, task)['hidden']
                        assert target(request(action='snapshot'), task)['hidden']
                elif kind in ('lookaway_hide', 'lookaway_material', 'return_move'):
                    capture(task_id + '-before')
                    p = task.get('far_probe', task['probe'])
                    view(p, [2 * p[0] - aim[0], 2 * p[1] - aim[1], p[2] + 70])
                    view(task['probe'], aim)
                    after = target(request(action='snapshot'), task)
                    before = target(first, task)
                    if kind == 'lookaway_hide':
                        assert not before['hidden'] and after['hidden']
                    elif kind == 'lookaway_material':
                        assert before['materials'] != after['materials']
                    else:
                        assert before['transform'] != after['transform']
                capture(task_id + '-bug')
                restored = request(action='switch', map=task['map'], task='baseline')
                assert restored['pid'] == bug['pid'] == initial['pid'] == process.pid
                assert restored['task'] == 'baseline'
                assert stable_state(restored) == golden[task['map']], ('Dirty after task', task_id)
                assert sum((a - b) ** 2 for a, b in zip(restored['position'], clean['position'])) < 1
                result = dict(id=task_id, result='PASS', same_pid=process.pid,
                              clean_restored=True, rendered=True, generation=restored['generation'])
                results.append(result)
                (OUT / 'results.json').write_text(json.dumps(results, indent=2))
                print(json.dumps(result), flush=True)
        finally:
            process.terminate()
            try:
                process.wait(15)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
    assert len(results) == 18


if __name__ == '__main__':
    main()
