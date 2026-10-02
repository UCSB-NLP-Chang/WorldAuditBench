"""Count-only cross-service progress. Each process reads only its own database."""
import time
from .common import require
from .delivery import request_json


def local_metrics(store, app, cohort):
    require(type(cohort) is int and cohort in (0, 1), 'Invalid cohort')
    result = {}
    def put(rows, columns):
        for row in rows:
            item = result.setdefault(row[0], {})
            item.update(zip(columns, row[1:]))
    with store.lock:
        db = store.db
        if app == 'exploration':
            put(db.execute("""SELECT t.case_key,count(DISTINCT a.user_id) FROM task_access a
                JOIN task_catalog t ON t.id=a.task_id JOIN users u ON u.id=a.user_id
                WHERE a.role='explorer' AND u.is_test=? GROUP BY t.case_key""", (cohort,)), ['assigned_explorers'])
            put(db.execute("""SELECT t.case_key,count(DISTINCT a.owner),count(*) FROM submissions s
                JOIN attempts a ON a.id=s.attempt_id JOIN task_catalog t ON t.id=a.task_version_id
                JOIN users u ON u.id=a.owner WHERE u.is_test=? GROUP BY t.case_key""", (cohort,)), ['completed_explorers','submitted_answers'])
            put(db.execute("""SELECT t.case_key,count(DISTINCT a.owner) FROM attempts a
                JOIN task_catalog t ON t.id=a.task_version_id JOIN users u ON u.id=a.owner
                WHERE u.is_test=? AND a.status='draft' AND NOT EXISTS (
                    SELECT 1 FROM attempts done JOIN task_catalog dt ON dt.id=done.task_version_id
                    WHERE done.owner=a.owner AND dt.case_key=t.case_key AND done.status='submitted')
                GROUP BY t.case_key""", (cohort,)), ['active_explorers'])
        else:
            put(db.execute("""SELECT t.case_key,count(*),sum(a.state='complete'),
                sum(a.state<>'complete' AND a.owner IS NOT NULL AND a.lease_until>?),
                sum(a.state<>'complete' AND (a.owner IS NULL OR a.lease_until<=?))
                FROM submissions s JOIN task_catalog t ON t.id=s.task_version_id
                JOIN review_assignments a ON a.submission_id=s.id
                LEFT JOIN submission_authors author ON author.submission_id=s.id
                WHERE COALESCE(author.is_test,json_extract(s.payload,'$.test_submission'),0)=?
                GROUP BY t.case_key""", (time.time(), time.time(), cohort)), ['received_answers','reviewed_answers','active_reviews','pending_answers'])
            # Historical saves are completions, never page views/claims. UNION removes revisions.
            put(db.execute("""SELECT t.case_key,count(DISTINCT j.owner) FROM (
                SELECT submission_id,owner FROM judgment_history UNION SELECT submission_id,owner FROM judgments) j
                JOIN submissions s ON s.id=j.submission_id JOIN task_catalog t ON t.id=s.task_version_id
                JOIN users u ON u.id=j.owner LEFT JOIN submission_authors author ON author.submission_id=s.id
                WHERE u.is_test=? AND COALESCE(author.is_test,json_extract(s.payload,'$.test_submission'),0)=?
                GROUP BY t.case_key""", (cohort, cohort)), ['reviewer_count'])
    return result


EX_KEYS = ('assigned_explorers','completed_explorers','submitted_answers','active_explorers')
EV_KEYS = ('received_answers','reviewed_answers','active_reviews','pending_answers','reviewer_count')


def peer_metrics(server, cohort):
    peer = 'evaluation' if server.app == 'exploration' else 'exploration'
    url = server.config.get(peer + '_internal')
    if not url:
        return None
    with server.metrics_lock:
        cached = server.metrics_cache.get(cohort)
        if cached and time.monotonic() - cached[0] < 10:
            return cached[1]
        try:
            value = request_json(url + '/internal/progress', {'cohort': cohort}, server.config['transfer_secret'], timeout=3)['cases']
        except Exception:
            # Missing is unknown, not zero. Retry on the next refresh.
            return None
        server.metrics_cache[cohort] = (time.monotonic(), value)
        return value


def add_group_progress(store, app, user, data, peer):
    cohort = data['cohort']
    own = local_metrics(store, app, cohort)
    ex, ev = (own, peer) if app == 'exploration' else (peer, own)
    with store.lock:
        if user.get('is_admin'):
            catalog = [dict(r) for r in store.db.execute('SELECT * FROM task_catalog ORDER BY title,id')]
        else:
            catalog = store.accessible_tasks(user, 'explorer' if app == 'exploration' else 'reviewer')
    cases, by_id = {}, {}
    for task in catalog:
        key = task['case_key']
        if key not in cases:
            item = {'id':task['id'], 'title':task['title']}
            # Private source case keys do not cross the public API.
            item.update({k: ex.get(key, {}).get(k, 0) if ex is not None else None for k in EX_KEYS})
            item.update({k: ev.get(key, {}).get(k, 0) if ev is not None else None for k in EV_KEYS})
            cases[key] = item
        by_id[task['id']] = cases[key]
    rows = list(cases.values())
    summary = {'total_cases':len(rows)}
    for keys, source in ((EX_KEYS, ex), (EV_KEYS, ev)):
        for k in keys:
            # reviewer_count is meaningful per case; summed values are person-case completions.
            summary[k] = sum(r[k] for r in rows) if source is not None else None
    summary['explored_cases'] = sum(r['completed_explorers'] > 0 for r in rows) if ex is not None else None
    summary['fully_reviewed_cases'] = sum(r['submitted_answers'] > 0 and r['received_answers'] >= r['submitted_answers'] and r['reviewed_answers'] >= r['received_answers'] for r in rows) if ex is not None and ev is not None else None
    summary['reviewed_cases'] = sum(r['reviewer_count'] > 0 for r in rows) if ev is not None else None
    for label, numerator, denominator in [('exploration_percent','explored_cases','total_cases'),('review_percent','reviewed_answers','received_answers')]:
        n, d = summary[numerator], summary[denominator]
        summary[label] = None if n is None or d is None else round(100*n/d, 1) if d else 0
    data['group'] = {'summary':summary, 'cases':rows, 'cohort':cohort, 'peer_available':peer is not None}
    for row in data['rows']:
        row['case_progress'] = by_id.get(row['task_id'])
    return data
