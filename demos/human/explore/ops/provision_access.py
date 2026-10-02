#!/usr/bin/env python3
"""Offline account/assignment synchronization. Never writes to legacy auditing."""
import argparse
import hashlib
import json
import pathlib
import secrets
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bf.exploration import ExplorationStore
from bf.evaluation import EvaluationStore
from bf.common import require

NEW_EXPLORERS = ['yifeng', 'yutao', 'li', 'xinyi', 'feng']


def provision(root, participants_path):
    root = pathlib.Path(root)
    legacy = json.loads(pathlib.Path(participants_path).read_text())
    require(legacy.get('mode') == 'group' and legacy.get('access_code'), 'Expected group password config')
    original = [row['name'] for row in legacy['reviewers']]
    # Include registered accounts even if no longer present in the configured picker.
    import sqlite3
    old_db = pathlib.Path(participants_path).with_name('review.sqlite3')
    with sqlite3.connect('file:' + str(old_db) + '?mode=ro', uri=True) as db:
        original += [row[0] for row in db.execute('SELECT name FROM participants')]
    names = {}
    for name in original + NEW_EXPLORERS:
        names.setdefault(name.casefold(), name)
    plan_path = root / 'config/access-plan.json'
    exconfig = json.loads((root / 'config/exploration.json').read_text())
    evconfig = json.loads((root / 'config/evaluation.json').read_text())
    task_id = exconfig['task_id']
    reference = next(ref for ref in evconfig['references'] if ref['id'] == task_id)
    case_key = reference.get('case_id', task_id)
    role_by_name = {key: 'explorer' if key in NEW_EXPLORERS else 'reviewer' for key in names}
    role_by_name.update({'testuser': 'explorer', 'qa-explorer': 'explorer', 'qa-evaluator': 'reviewer'})
    if plan_path.exists():
        plan = json.loads(plan_path.read_text())
        require(plan['task_id'] == task_id and plan['case_key'] == case_key, 'Access plan task mismatch')
        role_by_name = plan['roles']
        require(set(role_by_name) == set(names) | {'testuser','qa-explorer','qa-evaluator'}, 'Access plan roster mismatch')
    else:
        plan = {'task_id': task_id, 'case_key': case_key, 'roles': role_by_name, 'admins': ['testuser']}
    stores = {'exploration': ExplorationStore(root / 'exploration-state'), 'evaluation': EvaluationStore(root / 'evaluation-state')}
    try:
        for app, store in stores.items():
            store.catalog(task_id, exconfig['task']['title'], case_key)
            with store.transaction() as db:
                db.execute('UPDATE task_catalog SET title=?,case_key=? WHERE id=?', (exconfig['task']['title'], case_key, task_id))
            for key, name in names.items():
                row = store.db.execute('SELECT id FROM users WHERE lower(name)=lower(?)', (name,)).fetchone()
                if row is None:
                    store.add_user(name, legacy['access_code'])
                else:
                    # Preserve account IDs and all owned data.
                    salt = secrets.token_hex(16)
                    hashed = hashlib.scrypt(legacy['access_code'].encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
                    with store.transaction() as db:
                        db.execute('UPDATE users SET password=? WHERE id=?', (salt+':'+hashed, row['id']))
            # Test accounts already have independently configured credentials.
            accounts = json.loads((root / 'config/acceptance-accounts.json').read_text())
            for name in ('testuser', 'qa-explorer', 'qa-evaluator'):
                if not store.db.execute('SELECT 1 FROM users WHERE name=?', (name,)).fetchone():
                    store.add_user(name, accounts[name], is_test=True)
                with store.transaction() as db:
                    db.execute('UPDATE users SET is_test=1,is_admin=? WHERE name=?', (int(name in plan['admins']), name))
            for key, role in role_by_name.items():
                store.grant_task(names.get(key, key), task_id, role)
        # Attribute historical answers and reclassify test metadata without rewriting envelopes.
        ex, ev = stores['exploration'], stores['evaluation']
        authors = ex.db.execute('SELECT s.id,u.name,u.is_test FROM submissions s JOIN attempts a ON a.id=s.attempt_id JOIN users u ON u.id=a.owner').fetchall()
        with ev.transaction() as db:
            for row in authors:
                if db.execute('SELECT 1 FROM submissions WHERE id=?', (row['id'],)).fetchone():
                    db.execute('INSERT INTO submission_authors(submission_id,name,is_test) VALUES(?,?,?) ON CONFLICT(submission_id) DO UPDATE SET name=excluded.name,is_test=excluded.is_test', tuple(row))
        # Both independent DBs must enforce the same role for the same identity and case.
        roles = []
        for store in stores.values():
            roles.append([tuple(row) for row in store.db.execute('SELECT lower(u.name),t.case_key,a.role FROM task_access a JOIN users u ON u.id=a.user_id JOIN task_catalog t ON t.id=a.task_id ORDER BY lower(u.name),t.case_key')])
        require(roles[0] == roles[1], 'Cross-service role assignments differ', 500)
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2)+'\n')
        plan_path.chmod(0o600)
        return {'formal_users': list(names.values()), 'explorers': [names[k] for k,v in role_by_name.items() if v=='explorer' and k in names],
                'reviewers': [names[k] for k,v in role_by_name.items() if v=='reviewer' and k in names],
                'admins': plan['admins'], 'password_source': 'legacy group access_code', 'matching_case_roles': True}
    finally:
        for store in stores.values(): store.db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root')
    parser.add_argument('--participants', default='/home/ubuntu/unreal-auditor/review-service/state/participants.json')
    args = parser.parse_args()
    print(json.dumps(provision(args.root, args.participants), ensure_ascii=False))
