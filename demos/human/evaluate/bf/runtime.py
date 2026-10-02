"""Single-slot pilot adapter. Legacy review has priority; no legacy state is mutated."""
import json
import socket
import subprocess
import threading
import time
from .common import require, uid
from .delivery import request_json


def listening(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=.2):
            return True
    except OSError:
        return False


class Runtime:
    def __init__(self, store, config):
        self.store, self.c = store, config
        self.lock = threading.RLock()
        self.current = None
        self.browsers = {}
        self.last_notice = {}

    def call(self, operation, session):
        return request_json(self.c['supervisor_url'] + '/runtime', {'operation': operation, 'session_id': session['id'], 'map': self.c['tasks'][session['task_version_id']]['map'], 'slot': 0}, self.c['supervisor_secret'], timeout=15)

    def legacy_busy(self):
        return any(listening(port) for port in self.c.get('legacy_player_ports', []))

    def start(self, user, aid):
        snapshot = self.store.snapshot(user, aid)
        require(snapshot['status'] == 'draft', '探索已经结束', 409)
        with self.lock:
            if self.c.get('tasks', {}).get(snapshot['task']['id'], {}).get('kind') == 'browser':
                for session in self.browsers.values():
                    if session['owner'] == user['id'] and session['attempt_id'] == aid:
                        return self.public(session)
                session = {'id': uid(), 'owner': user['id'], 'attempt_id': aid, 'task_version_id': snapshot['task']['id'], 'kind': 'browser', 'status': 'ready', 'created': time.time(), 'heartbeat': time.time()}
                self.store.record_runtime(aid, user, session['id'])
                self.browsers[session['id']] = session
                return self.public(session)
            if self.current:
                require(self.current['owner'] == user['id'] and self.current['attempt_id'] == aid, '验证环境正在使用，请稍后重试', 409)
                return self.public(self.current)
            require(not self.legacy_busy(), '现有审核正在使用 GPU，请稍后开始探索', 409)
            if self.c.get('gpu_guard', True):
                result = subprocess.run(['nvidia-smi', '--query-gpu=memory.free,utilization.gpu', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=5, check=True)
                free, utilization = [int(v.strip()) for v in result.stdout.strip().splitlines()[0].split(',')]
                require(free >= 12000 and utilization <= 25, 'GPU 正在忙碌，请稍后再试', 409)
            session = {'id': uid(), 'owner': user['id'], 'attempt_id': aid, 'task_version_id': snapshot['task']['id'], 'status': 'starting', 'created': time.time(), 'heartbeat': time.time()}
            self.store.record_runtime(aid, user, session['id'])
            self.current = session
            try:
                self.call('start', session)
            except Exception:
                # Keep ownership until teardown is confirmed, even for a timed-out start.
                session['status'] = 'closing'
                raise
            self.last_notice.pop(aid, None)
            return self.public(session)

    def public(self, session):
        kind = session.get('kind', 'unreal')
        return {'id': session['id'], 'attempt_id': session['attempt_id'], 'kind': kind, 'status': session['status'], 'stream_url': ('/browser/' if kind == 'browser' else '/stream/') + session['id'] + '/' if session['status'] == 'ready' else None}

    def status(self, user, aid):
        self.store.snapshot(user, aid)
        with self.lock:
            for session in self.browsers.values():
                if session['owner'] == user['id'] and session['attempt_id'] == aid:
                    session['heartbeat'] = time.time()
                    return self.public(session)
            if self.current and self.current['owner'] == user['id'] and self.current['attempt_id'] == aid:
                self.current['heartbeat'] = time.time()
                return self.public(self.current)
            return {'status': 'idle', 'message': self.last_notice.get(aid, '')}

    def authorize_browser(self, user, sid):
        with self.lock:
            session = self.browsers.get(sid)
            require(session and session['owner'] == user['id'] and session['status'] == 'ready', '环境会话不存在或已结束', 403)
            self.store.require_access(user, session['task_version_id'], 'explorer')
            require(self.store.snapshot(user, session['attempt_id'])['status'] == 'draft', '探索已经结束', 403)
            return self.c['tasks'][session['task_version_id']]

    def stop_user(self, user):
        with self.lock:
            for sid, session in list(self.browsers.items()):
                if session['owner'] == user['id']: del self.browsers[sid]
            if self.current and self.current['owner'] == user['id']:
                self.stop(user, self.current['attempt_id'])

    def finish_attempt(self, user, aid):
        with self.lock:
            for sid, session in list(self.browsers.items()):
                if session['owner'] == user['id'] and session['attempt_id'] == aid: del self.browsers[sid]
            if self.current and self.current['owner'] == user['id'] and self.current['attempt_id'] == aid:
                self.current['status'] = 'closing'

    def authorize(self, user, sid):
        with self.lock:
            session = self.current
            require(session and session['id'] == sid and session['owner'] == user['id'] and session['status'] == 'ready', '视频会话不存在或已结束', 403)
            self.store.require_access(user, session['task_version_id'], 'explorer')
            return self.c['player_port']

    def stream_connected(self, sid):
        with self.lock:
            if self.current and self.current['id'] == sid:
                self.current['connections'] = self.current.get('connections', 0) + 1
                self.current.pop('disconnect_deadline', None)

    def stream_disconnected(self, sid):
        with self.lock:
            if self.current and self.current['id'] == sid:
                self.current['connections'] = max(0, self.current.get('connections', 0) - 1)
                if not self.current['connections']:
                    self.current['disconnect_deadline'] = time.time() + 10

    def stop(self, user=None, aid=None, reason='环境已结束，草稿和截图已保存。'):
        with self.lock:
            for sid, browser in list(self.browsers.items()):
                if user is None or (browser['owner'] == user['id'] and browser['attempt_id'] == aid):
                    del self.browsers[sid]
                    if user: return {'status': 'idle', 'message': reason}
            session = self.current
            if not session:
                return {'status': 'idle'}
            if user:
                require(session['owner'] == user['id'] and session['attempt_id'] == aid, '会话不属于当前探索', 403)
            session['status'] = 'closing'
            result = self.call('stop', session)
            require(result.get('stopped'), '正在关闭环境，请稍后重试', 503)
            self.last_notice[session['attempt_id']] = reason
            self.current = None
            return {'status': 'idle', 'message': reason}

    def tick(self):
        with self.lock:
            now = time.time()
            for sid, browser in list(self.browsers.items()):
                if now - browser['heartbeat'] > 120 or now - browser['created'] > 1800:
                    del self.browsers[sid]
            session = self.current
            if not session:
                return
            if self.legacy_busy():
                self.stop(reason='现有审核优先使用 GPU；探索已暂停，草稿和截图已保留。可稍后重新进入。')
                return
            now = time.time()
            if now >= session.get('disconnect_deadline', float('inf')):
                self.stop(reason='视频连接已断开，环境已释放；草稿和截图已保留。请重新进入。')
                return
            if session['status'] == 'closing' or now - session['heartbeat'] > 120 or now - session['created'] > 1800:
                self.stop()
                return
            result = self.call('status', session)
            if result.get('ready'):
                session['status'] = 'ready'
            elif result.get('game_running') is False or now - session['created'] > 120 and session['status'] == 'starting':
                self.stop(reason='环境启动或运行失败；答案草稿已保留，请重新进入或报告技术问题。')

