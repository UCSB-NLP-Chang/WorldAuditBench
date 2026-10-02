"""Read-only progress projections. Each app queries only its own database."""
import collections
import json
import time
from .common import require


def counts(rows):
    states = collections.Counter(row['status'] for row in rows)
    completed = states.get('submitted', 0) + states.get('complete', 0)
    return {'total': len(rows), 'completed': completed, 'completion_percent': round(100 * completed / len(rows), 1) if rows else 0, 'states': dict(states)}


def exploration_rows(store, user, all_users, cohort):
    with store.lock:
        assignments = store.db.execute("""SELECT a.*,u.name,u.is_test,t.title FROM task_access a
            JOIN users u ON u.id=a.user_id JOIN task_catalog t ON t.id=a.task_id
            WHERE a.role='explorer' AND u.is_test=? AND (? OR u.id=?) ORDER BY u.name,a.assigned""", (cohort, int(all_users), user['id'])).fetchall()
        rows = []
        for assignment in assignments:
            attempts = store.db.execute("SELECT * FROM attempts WHERE owner=? AND task_version_id=? ORDER BY created DESC", (assignment['user_id'], assignment['task_id'])).fetchall()
            latest = attempts[0] if attempts else None
            submissions = [a for a in attempts if a['status'] == 'submitted']
            status = 'submitted' if submissions else latest['status'] if latest else 'not_started'
            sid = store.db.execute('SELECT id,created FROM submissions WHERE attempt_id=?', (submissions[0]['id'],)).fetchone() if submissions else None
            draft = json.loads(latest['draft']) if latest else {'reports': []}
            flags = store.db.execute('SELECT count(*) FROM flags WHERE attempt_id=?', (latest['id'],)).fetchone()[0] if latest else 0
            rows.append({'id': assignment['task_id'], 'task_id': assignment['task_id'], 'title': assignment['title'], 'owner': assignment['name'],
                         'status': status, 'latest_status': latest['status'] if latest else None,
                         'attempt_id': latest['id'] if latest else None, 'attempt_count': len(attempts),
                         'report_count': len(draft['reports']), 'flag_count': flags,
                         'technical_count': sum(a['status'] == 'technical' for a in attempts),
                         'updated': max((a['updated'] or a['created'] for a in attempts), default=None),
                         'submitted_at': sid['created'] if sid else None, 'history': [{'id': a['id'], 'status': a['status'], 'created': a['created']} for a in attempts], 'can_open': assignment['user_id'] == user['id']})
        return rows


def evaluation_rows(store, user, all_users, cohort, mine):
    with store.lock:
        allowed = {row['id']: row for row in store.queue(user)}
        raw = store.db.execute("""SELECT s.*,a.owner,a.state,a.lease_until,u.name AS reviewer,author.name AS explorer,t.title,t.case_key,j.payload AS judgment,j.updated AS reviewed_at
            FROM submissions s JOIN review_assignments a ON a.submission_id=s.id
            LEFT JOIN users u ON u.id=a.owner LEFT JOIN submission_authors author ON author.submission_id=s.id
            JOIN task_catalog t ON t.id=s.task_version_id LEFT JOIN judgments j ON j.submission_id=s.id
            WHERE COALESCE(author.is_test,json_extract(s.payload,'$.test_submission'),0)=? ORDER BY s.created DESC""", (cohort,)).fetchall()
        rows = []
        for row in raw:
            if not all_users and row['id'] not in allowed:
                continue
            if mine and row['owner'] != user['id']:
                continue
            payload = json.loads(row['payload'])
            status = 'complete' if row['state'] == 'complete' else 'in_progress' if row['owner'] and row['lease_until'] > time.time() else 'pending'
            permission = allowed.get(row['id'], {})
            rows.append({'id': row['id'], 'task_id': row['task_version_id'], 'title': row['title'], 'case_id': row['case_key'], 'owner': row['explorer'] or '历史账号',
                         'reviewer': row['reviewer'] if status != 'pending' else '', 'status': status,
                         'outcome': payload['outcome'], 'report_count': len(payload['reports']), 'flag_count': len(payload['evidence']),
                         'submitted_at': payload['submitted_at'], 'updated': row['reviewed_at'] or payload['submitted_at'],
                         'mine': row['owner'] == user['id'],
                         'can_open': bool(permission.get('mine') or permission.get('available')),
                         'judgments': json.loads(row['judgment'])['answers'] if row['judgment'] else []})
        return rows


def progress(store, app, user, scope='assigned', cohort=None):
    require(scope in ('assigned', 'mine', 'all', 'overview'), 'Unknown scope')
    all_users = scope == 'all'
    require(not all_users or user.get('is_admin'), '仅管理员可查看整体人员进度', 403)
    cohort = int(user.get('is_test', 0)) if cohort is None else int(cohort)
    require(cohort in (0, 1) and (user.get('is_admin') or cohort == int(user.get('is_test', 0))), '不能查看其他数据组', 403)
    if app == 'exploration':
        rows = exploration_rows(store, user, all_users, cohort)
    else:
        rows = evaluation_rows(store, user, all_users, cohort, scope == 'mine')
    distribution = {'bugs': {}, 'categories': {}, 'no_bug': {}}
    if app == 'evaluation':
        for key, values in (
            ('bugs', [a['verdict'] for r in rows if r['outcome'] == 'reports' for a in r['judgments']]),
            ('categories', [a.get('category_verdict', 'not_reviewed') for r in rows if r['outcome'] == 'reports' for a in r['judgments']]),
            ('no_bug', [a['verdict'] for r in rows if r['outcome'] == 'none' for a in r['judgments']])):
            distribution[key] = dict(collections.Counter(values))
        # Progress does not expose private rationale or reference text.
        for row in rows:
            row.pop('judgments')
    people = []
    if all_users:
        with store.lock:
            for person in store.db.execute('SELECT id,name,last_seen FROM users WHERE is_test=? ORDER BY name', (cohort,)):
                owned = [r for r in rows if r['owner' if app == 'exploration' else 'reviewer'] == person['name']]
                role = 'explorer' if app == 'exploration' else 'reviewer'
                assigned_tasks = store.db.execute('SELECT count(*) FROM task_access WHERE user_id=? AND role=?', (person['id'], role)).fetchone()[0]
                summary = counts(owned)
                people.append({'name': person['name'], 'assigned_cases': assigned_tasks, 'last_seen': person['last_seen'],
                               'last_activity': max((r['updated'] or 0 for r in owned), default=None),
                               'technical_count': sum(r.get('technical_count', 0) for r in owned), **summary})
    return {'rows': rows, 'summary': counts(rows), 'people': people, 'distribution': distribution,
            'scope': scope, 'cohort': cohort, 'unit': 'assigned_cases' if app == 'exploration' else 'received_submissions'}
