import hashlib
import http.server
import json
from pathlib import Path
import threading
import urllib.error
import urllib.request

import pytest

from environments.pixel_streaming import PixelStreaming, launch_command
from scripts import view_task


@pytest.fixture
def viewer_server(tmp_path):
    rows = [{'task_id': 'JS_TEST', 'engine': 'threejs'}, {'task_id': 'UE_TEST', 'engine': 'unreal'}]
    viewer = view_task.Viewer(rows, tmp_path)
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), view_task.make_handler(viewer))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield viewer, f'http://127.0.0.1:{server.server_port}'
    server.shutdown()
    server.server_close()
    viewer.close()
    thread.join()


def request(base, path, data=None, **headers):
    req = urllib.request.Request(base + path, data=json.dumps(data).encode() if data is not None else None,
                                 headers={'Content-Type': 'application/json', **headers})
    try:
        response = urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        return response.status, response.read()


def test_browser_scene_and_stop_lifecycle(viewer_server, tmp_path, monkeypatch):
    viewer, base = viewer_server
    root = tmp_path / 'scene/site'
    root.mkdir(parents=True)
    body = b'<html>Interactive test scene</html>'
    (root / 'index.html').write_bytes(body)
    monkeypatch.setattr(view_task, 'ensure_environment', lambda *args: {
        'id': 'scene', 'runtime_root': 'site', 'page': 'index.html'})
    monkeypatch.setattr(view_task, 'task_catalog', lambda: {
        'JS_TEST': {'page_sha256': hashlib.sha256(body).hexdigest(), 'source_case': 'test-case'}})
    code, result = request(base, '/api/open', {'task_id': 'JS_TEST'})
    assert code == 200
    result = json.loads(result)
    assert result['engine'] == 'threejs'
    assert request(base, result['url']) == (200, body)
    assert json.loads(request(base, '/api/status')[1])['running'] is True
    assert request(base, '/api/stop', {})[0] == 200
    assert json.loads(request(base, '/api/status')[1])['running'] is False
    assert request(base, result['url'])[0] == 502
    assert request(base, '/api/open', {'task_id': 'JS_TEST'})[0] == 200


def test_unreal_uses_streaming_and_closes_on_stop(viewer_server, tmp_path, monkeypatch):
    viewer, base = viewer_server
    profiles = tmp_path / 'profiles.json'
    profiles.write_text(json.dumps({'tasks': {'UE_TEST': {'runtime_map': '/Game/Scene?Task=UE_TEST'}}}))
    viewer.profiles = profiles
    monkeypatch.setattr(view_task.sys, 'platform', 'linux')
    calls = []
    monkeypatch.setattr(viewer.streaming, 'validate', lambda p: calls.append(('validate', p)))
    monkeypatch.setattr(viewer.streaming, 'start', lambda p: calls.append(('start', p)) or {
        'engine': 'unreal', 'transport': 'pixel-streaming', 'url': '/stream/abc/player.html'})
    monkeypatch.setattr(viewer.streaming, 'close', lambda: calls.append(('close',)))
    code, body = request(base, '/api/open', {'task_id': 'UE_TEST'})
    assert code == 200 and json.loads(body)['transport'] == 'pixel-streaming'
    assert [c[0] for c in calls] == ['validate', 'close', 'start']
    assert request(base, '/api/stop', {})[0] == 200
    assert calls[-1] == ('close',)
    # The viewer must not accidentally send paused agent actions during manual play.
    assert request(base, '/api/step', {'action': 'move_up'})[0] == 404


def test_viewer_rejects_cross_origin_and_stale_streams(viewer_server):
    viewer, base = viewer_server
    assert request(base, '/api/stop', {}, Origin='https://another-site.example')[0] == 403
    assert request(base, '/api/stop', {}, **{'Content-Type': 'text/plain'})[0] == 415
    assert request(base, '/stream/' + 'a' * 32 + '/player.html')[0] == 404
    assert request(base, '/api/open', {'task_id': 'UNKNOWN'})[0] == 400
    viewer.lock.acquire()
    try:
        assert request(base, '/api/stop', {})[0] == 400
    finally:
        viewer.lock.release()
    assert b'task_viewer.js' in request(base, '/')[1]
    assert request(base, '/task_viewer.js')[0] == 200


def test_streaming_launch_uses_interactive_task_and_isolated_state(tmp_path):
    profile = {'binary': '/runtime/Scene', 'runtime_map': '/Game/Scene?Task=S01',
               'game_args': ['-vulkan', '-PixelStreamingConnectionURL=ws://old:1',
                             '-AuditorServe', '-graphicsadapter=99'],
               'extra_args': ['-AuditorExplorationTask=S01', '-AuditorExplorationPolicy=/policy.json']}
    command = launch_command(profile, 12345, tmp_path, 1)
    assert command[:2] == ['/runtime/Scene', '/Game/Scene?Task=S01']
    assert '-AuditorRemoteInput' in command
    assert '-PixelStreamingConnectionURL=ws://127.0.0.1:12345' in command
    assert '-graphicsadapter=1' in command
    assert '-UserDir=' + str(tmp_path / 'user') + '/' in command
    assert '-AuditorExplorationPolicy=/policy.json' in command
    assert not any(x in command for x in ['-AuditorServe', '-graphicsadapter=99', '-PixelStreamingConnectionURL=ws://old:1'])


def test_streaming_verifies_binary_before_starting(tmp_path):
    for name in ['SignallingWebServer/dist/index.js', 'SignallingWebServer/www/player.html']:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('fixture')
    binary = tmp_path / 'Unreal'
    binary.write_bytes(b'original')
    stream = PixelStreaming(tmp_path, tmp_path / 'state')
    profile = {'binary': str(binary), 'build_sha256': hashlib.sha256(b'original').hexdigest()}
    stream.validate(profile)
    binary.write_bytes(b'modified')
    with pytest.raises(ValueError, match='checksum'):
        stream.validate(profile)
    assert stream.processes == []


def test_partial_stream_start_is_cleaned_up(tmp_path, monkeypatch):
    stream = PixelStreaming(tmp_path, tmp_path / 'state')
    monkeypatch.setattr(stream, 'spawn', lambda *args: (_ for _ in ()).throw(OSError('node missing')))
    with pytest.raises(OSError, match='node missing'):
        stream.start({'binary': '/not-used'})
    assert stream.session_id is None and stream.player_port is None


def test_native_boundary_transitions_partial_lines_and_reset(tmp_path, monkeypatch):
    stream = PixelStreaming(tmp_path, tmp_path / 'state')
    stream.directory = tmp_path
    monkeypatch.setattr(stream, 'alive', lambda: True)
    log = tmp_path / 'unreal.log'
    assert stream.boundary() is None
    log.write_bytes(b'LogTemp: AUDITOR_BOUNDARY state=0 clearance_cm=500\n')
    assert stream.boundary() == 0
    with log.open('ab') as f:
        f.write(b'LogTemp: AUDITOR_BOUNDARY state=2 clear')
    assert stream.boundary() == 0  # An incomplete write must not change the state.
    with log.open('ab') as f:
        f.write(b'ance_cm=0.2\n')
    assert stream.boundary() == 2
    with log.open('ab') as f:
        f.write(b'Unrelated log\n' * 1000)
    assert stream.boundary() == 2  # Standing still must retain the warning.
    with log.open('ab') as f:
        f.write(b'LogTemp: AUDITOR_BOUNDARY state=1 clearance_cm=10\n')
    assert stream.boundary() == 1
    stream.close()
    log.write_bytes(b'New session\n')
    assert stream.boundary() is None
    with log.open('ab') as f:
        f.write(b'AUDITOR_BOUNDARY state=2 clearance_cm=0\n')
    assert stream.boundary() == 2
    log.write_bytes(b'Truncated\n')
    assert stream.boundary() is None


def test_status_exposes_boundary_only_for_a_running_scene(viewer_server, monkeypatch):
    viewer, base = viewer_server
    viewer.task = 'UE_TEST'
    monkeypatch.setattr(viewer.streaming, 'alive', lambda: True)
    monkeypatch.setattr(viewer.streaming, 'boundary', lambda: 2)
    assert json.loads(request(base, '/api/status')[1])['boundary_state'] == 2
    monkeypatch.setattr(viewer.streaming, 'alive', lambda: False)
    assert json.loads(request(base, '/api/status')[1])['boundary_state'] is None
