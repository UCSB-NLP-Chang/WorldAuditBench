"""Small infrastructure primitives; no cross-application database access."""
import contextlib
import hashlib
import hmac
import json
import pathlib
import secrets
import sqlite3
import threading
import time


class Problem(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def require(condition, message, status=400):
    if not condition:
        raise Problem(status, message)


def uid():
    return secrets.token_hex(16)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(data):
    return hashlib.sha256(data).hexdigest()


class Database:
    def __init__(self, root, filename, schema):
        self.root = pathlib.Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.root / filename, check_same_thread=False, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=10000;')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL, password TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS auth_sessions(token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires REAL NOT NULL);
        ''' + schema)
        version = self.db.execute('SELECT version FROM schema_version').fetchone()
        require(version is None or version[0] in (1, 2, 3), 'Unsupported database version', 500)
        # Migration 2: operational QA identities and answers use a separate queue cohort.
        if 'is_test' not in {r[1] for r in self.db.execute('PRAGMA table_info(users)')}:
            self.db.execute('ALTER TABLE users ADD COLUMN is_test INTEGER NOT NULL DEFAULT 0')
        columns = {r[1] for r in self.db.execute('PRAGMA table_info(users)')}
        if 'is_admin' not in columns:
            self.db.execute('ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0')
        if 'last_seen' not in columns:
            self.db.execute('ALTER TABLE users ADD COLUMN last_seen REAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS task_catalog(id TEXT PRIMARY KEY, title TEXT NOT NULL, case_key TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS task_access(user_id TEXT NOT NULL REFERENCES users(id), task_id TEXT NOT NULL REFERENCES task_catalog(id), role TEXT NOT NULL CHECK(role IN ('explorer','reviewer')), assigned REAL NOT NULL, PRIMARY KEY(user_id,task_id));
        ''')
        self.db.execute('DELETE FROM schema_version')
        self.db.execute('INSERT INTO schema_version VALUES(3)')
        self.db.commit()

    @contextlib.contextmanager
    def transaction(self):
        with self.lock, self.db:
            yield self.db

    def add_user(self, name, password, is_test=False, is_admin=False):
        salt = secrets.token_hex(16)
        hashed = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
        with self.transaction() as db:
            db.execute('INSERT INTO users(id,name,password,is_test,is_admin) VALUES(?,?,?,?,?)', (uid(), name, salt + ':' + hashed, int(is_test), int(is_admin)))

    def login(self, name, password):
        require(isinstance(name, str) and isinstance(password, str) and len(password) <= 256, 'Invalid login')
        with self.lock:
            row = self.db.execute('SELECT * FROM users WHERE lower(name)=lower(?)', (name,)).fetchone()
        salt, expected = row['password'].split(':') if row else ('0' * 32, '0' * 128)
        actual = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
        require(row is not None and hmac.compare_digest(actual, expected), '姓名或密码不正确', 401)
        token = secrets.token_urlsafe(32)
        with self.transaction() as db:
            db.execute('DELETE FROM auth_sessions WHERE expires<?', (time.time(),))
            db.execute('UPDATE users SET last_seen=? WHERE id=?', (time.time(), row['id']))
            db.execute('INSERT INTO auth_sessions VALUES(?,?,?)', (digest(token.encode()), row['id'], time.time() + 43200))
        return token

    def authenticate(self, token):
        with self.lock:
            row = self.db.execute('SELECT u.id,u.name,u.is_test,u.is_admin FROM users u JOIN auth_sessions a ON u.id=a.user_id WHERE a.token_hash=? AND a.expires>?', (digest(token.encode()), time.time())).fetchone()
        require(row is not None, '请先登录', 401)
        return dict(row)

    def logout(self, token):
        with self.transaction() as db:
            db.execute('DELETE FROM auth_sessions WHERE token_hash=?', (digest(token.encode()),))

    def catalog(self, task_id, title, case_key):
        with self.transaction() as db:
            db.execute('INSERT OR IGNORE INTO task_catalog VALUES(?,?,?)', (task_id, title, case_key))

    def grant_task(self, name, task_id, role):
        require(role in ('explorer', 'reviewer'), 'Invalid task role')
        with self.transaction() as db:
            user = db.execute('SELECT id FROM users WHERE lower(name)=lower(?)', (name,)).fetchone()
            task = db.execute('SELECT case_key FROM task_catalog WHERE id=?', (task_id,)).fetchone()
            require(user and task, 'Unknown account or task')
            conflict = db.execute("SELECT 1 FROM task_access a JOIN task_catalog t ON t.id=a.task_id WHERE a.user_id=? AND t.case_key=? AND a.role<>?", (user['id'], task['case_key'], role)).fetchone()
            require(not conflict, '同一 case 不可同时分配探索和复核', 409)
            db.execute('INSERT OR IGNORE INTO task_access VALUES(?,?,?,?)', (user['id'], task_id, role, time.time()))

    def require_access(self, user, task_id, role):
        with self.lock:
            require(self.db.execute('SELECT 1 FROM task_access WHERE user_id=? AND task_id=? AND role=?', (user['id'], task_id, role)).fetchone(), '当前账号未分配此任务', 403)

    def accessible_tasks(self, user, role):
        with self.lock:
            return [dict(row) for row in self.db.execute('SELECT t.* FROM task_catalog t JOIN task_access a ON a.task_id=t.id WHERE a.user_id=? AND a.role=? ORDER BY a.assigned,t.id', (user['id'], role))]
