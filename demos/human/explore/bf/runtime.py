"""FIFO single-slot exploration adapter. Legacy review has priority; no legacy state is mutated."""
import json
import socket
import subprocess
import threading
import time
from .common import Problem, require, uid
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
        self.queue = []
        self.ttl = config.get("session_ttl", 180)
        self.max_age = config.get("session_max_age", 3600)
        self.last_notice = {}

    def call(self, operation, session):
        return request_json(self.c['supervisor_url'] + '/runtime', {'operation': operation, 'session_id': session['id'], 'map': self.c['tasks'][session['task_version_id']]['map'], 'slot': 0}, self.c['supervisor_secret'], timeout=15)

    def legacy_busy(self):
        return any(listening(port) for port in self.c.get('legacy_player_ports', []))

    def start(self, user, aid):
        if self.store.guidance is not None:
            from .allocation import claim
            prior=self.store.snapshot(user,aid)
            reserved=claim(self.store,user,prior['task']['id'])
            require(reserved['id']==aid,'请打开当前领取的草稿',409)
        snapshot = self.store.snapshot(user, aid)
        require(snapshot['status'] == 'draft', '探索已经结束', 409)
        with self.lock:
            sessions = list(self.browsers.values()) + self.queue + ([self.current] if self.current else [])
            for existing in sessions:
                if existing['owner'] == user['id']:
                    require(existing['attempt_id'] == aid, '请先在原任务 End session；每个账号同时只能有一个会话（含排队）。', 409)
                    return self.public(existing)
            kind = self.c.get('tasks', {}).get(snapshot['task']['id'], {}).get('kind', 'unreal')
            session = {'id': uid(), 'owner': user['id'], 'attempt_id': aid, 'task_version_id': snapshot['task']['id'], 'kind': kind,
                       'status': 'ready' if kind == 'browser' else 'queued', 'created': time.time(), 'heartbeat': time.time()}
            self.last_notice.pop(aid, None)
            if kind == 'browser':
                self.store.record_runtime(aid, user, session['id'])
                self.browsers[session['id']] = session
            else:
                self.queue.append(session)
            return self.public(session)

    def capacity(self):
        with self.lock:
            return {'capacity': 1, 'running': int(self.current is not None), 'queued': len(self.queue),
                    'legacy_busy': self.legacy_busy(), 'heartbeat_timeout': self.ttl, 'max_age': self.max_age}

    def dispatch(self):
        # Do not release or reuse a slot until supervisor teardown succeeds.
        if self.current or not self.queue or self.legacy_busy():
            return
        if self.c.get('gpu_guard', True):
            result = subprocess.run(['nvidia-smi', '--query-gpu=memory.free,utilization.gpu', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=5, check=True)
            free, utilization = [int(v.strip()) for v in result.stdout.strip().splitlines()[0].split(',')]
            if free < 12000 or utilization > 25:
                return
        session = self.queue[0]
        user = {'id': session['owner']}
        try:
            self.store.require_access(user, session['task_version_id'], 'explorer')
            require(self.store.snapshot(user, session['attempt_id'])['status'] == 'draft', '探索已经结束', 409)
            self.store.record_runtime(session['attempt_id'], user, session['id'])
        except Problem:
            self.queue.pop(0)
            self.last_notice[session['attempt_id']] = '任务已提交或访问权限已变更，会话排队已取消。'
            return
        self.queue.pop(0)
        session.update(status='starting', started=time.time())
        self.current = session
        try:
            self.call('start', session)
        except Exception:
            session['status'] = 'closing'
            raise

    def public(self, session):
        kind = session.get('kind', 'unreal')
        return {'queue_position': next((i+1 for i, queued in enumerate(self.queue) if queued['id'] == session['id']), None), 'capacity': self.capacity(), 'expires_at': session['created'] + self.max_age, 'id': session['id'], 'attempt_id': session['attempt_id'], 'kind': kind, 'status': session['status'], 'stream_url': ('/browser/' if kind == 'browser' else '/stream/') + session['id'] + '/' if session['status'] == 'ready' else None}

    def status(self, user, aid):
        self.store.snapshot(user, aid)
        with self.lock:
            for session in list(self.browsers.values()) + self.queue:
                if session['owner'] == user['id'] and session['attempt_id'] == aid:
                    session['heartbeat'] = time.time()
                    return self.public(session)
            if self.current and self.current['owner'] == user['id'] and self.current['attempt_id'] == aid:
                self.current['heartbeat'] = time.time()
                return self.public(self.current)
            return {'status': 'idle', 'message': self.last_notice.get(aid, ''), 'capacity': self.capacity()}

    def authorize_browser(self, user, sid):
        with self.lock:
            session = self.browsers.get(sid)
            require(session and session['owner'] == user['id'] and session['status'] == 'ready', '环境会话不存在或已结束', 403)
            self.store.require_access(user, session['task_version_id'], 'explorer')
            require(self.store.snapshot(user, session['attempt_id'])['status'] == 'draft', '探索已经结束', 403)
            return self.c['tasks'][session['task_version_id']]

    def stop_user(self, user):
        with self.lock:
            self.queue = [s for s in self.queue if s['owner'] != user['id']]
            for sid, session in list(self.browsers.items()):
                if session['owner'] == user['id']: del self.browsers[sid]
            if self.current and self.current['owner'] == user['id']:
                self.stop(user, self.current['attempt_id'])

    def finish_attempt(self, user, aid):
        with self.lock:
            self.queue = [s for s in self.queue if not (s['owner'] == user['id'] and s['attempt_id'] == aid)]
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

    def stop(self, user=None, aid=None, reason='Session 已结束，已保存的草稿和截图保留；结束会话不会提交答案。', all_sessions=False):
        with self.lock:
            for queued in list(self.queue):
                if all_sessions or (user is not None and queued['owner'] == user['id'] and queued['attempt_id'] == aid):
                    self.queue.remove(queued)
                    self.last_notice[queued['attempt_id']] = reason
                    if user: return {'status': 'idle', 'message': reason}
            for sid, browser in list(self.browsers.items()):
                if all_sessions or (user is not None and browser['owner'] == user['id'] and browser['attempt_id'] == aid):
                    del self.browsers[sid]
                    self.last_notice[browser['attempt_id']] = reason
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
            for queued in list(self.queue):
                if now - queued['heartbeat'] > self.ttl or now - queued['created'] > self.max_age:
                    self.queue.remove(queued)
                    self.last_notice[queued['attempt_id']] = '排队心跳超时，会话已取消；可重新 Start session。'
            self.tick_current()
            self.dispatch()

    def tick_current(self):
        with self.lock:
            now = time.time()
            for sid, browser in list(self.browsers.items()):
                if now - browser['heartbeat'] > self.ttl or now - browser['created'] > self.max_age:
                    del self.browsers[sid]
                    self.last_notice[browser['attempt_id']] = 'Session 已超时，请重新 Start session；草稿和截图保留。'
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
            if session['status'] == 'closing' or now - session['heartbeat'] > self.ttl or now - session['created'] > self.max_age:
                self.stop()
                return
            result = self.call('status', session)
            if result.get('ready'):
                session['status'] = 'ready'
            elif result.get('game_running') is False or now - session.get('started', session['created']) > 120 and session['status'] == 'starting':
                self.stop(reason='环境启动或运行失败；答案草稿已保留，请重新进入或报告技术问题。')

