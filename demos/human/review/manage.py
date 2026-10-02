#!/usr/bin/env python3
"""Generate participant tokens or export observations. Never updates candidate QA."""
import argparse
import collections
import csv
import hashlib
import json
import os
import pathlib
import secrets
import urllib.request

CASE_FIELDS = ('environment', 'case_id', 'rubrics', 'case_path', 'case_type')
CASE_HEADERS = ('Environment', 'Case ID', 'Rubrics', 'Case Path', 'Case Type')


def safe_cell(value):
    """Keep text literal in Excel, including formulas behind leading whitespace."""
    if value is None:
        return ''
    if not isinstance(value, str):
        return value
    if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')):
        return "'" + value
    return value


def case_snapshot(row):
    # Never fill a historical snapshot from a possibly changed current manifest.
    case_id = row.get('case_id')
    if not case_id:
        rev = row.get('revision', '')
        rev = f'R{rev:02}' if isinstance(rev, int) else str(rev)
        case_id = f"{row.get('task_id', row.get('id', 'unknown'))}-{rev}"
    values = tuple(str(row.get(key, '') or '') if key != 'case_id' else str(case_id)
                   for key in CASE_FIELDS)
    return (values, str(row.get('revision', '')), str(row.get('sha256', '')))


def reviewer_id(row):
    # Missing legacy owner must never cause two unnamed people to overwrite.
    return str(row.get('reviewer_id') or row.get('owner') or 'legacy-record:' + str(row['id']))


def write_matrices(data, out, mode=None, build_sha256=None):
    groups = collections.defaultdict(list)
    for row in data.get('feedback', []):
        groups[(str(row.get('mode', 'unknown')), str(row.get('build_sha256', '')))].append(row)
    current = (str(data.get('mode', 'unknown')), str(data.get('build_sha256', '')))
    task_groups=collections.defaultdict(list)
    for task in data.get('tasks',[]):
        group=(current[0],str(task.get('build_sha256',current[1])))
        task_groups[group].append(task);groups.setdefault(group,[])
    if not task_groups:groups.setdefault(current, [])
    groups = {k: v for k, v in groups.items()
              if (mode is None or k[0] == mode) and (build_sha256 is None or k[1] == build_sha256)}
    index = []
    for group, feedback in sorted(groups.items()):
        rows = {}
        rows.update({case_snapshot(task): {} for task in task_groups.get(group,[])})
        latest = {}
        names = {}
        for item in sorted(feedback, key=lambda r: (float(r.get('created', 0)), str(r.get('id', '')))):
            identity = reviewer_id(item)
            names[identity] = str(item.get('reviewer') or identity)
            key = case_snapshot(item)
            rows.setdefault(key, {})
            latest[(key, identity)] = item
        duplicate_names = collections.Counter(names.values())
        reviewers = sorted(names, key=lambda rid: (names[rid], rid))
        labels = {}
        for rid in reviewers:
            # Stable digest suffix avoids prefix collisions and exposing full owner tokens.
            labels[rid] = names[rid] + (f' [{hashlib.sha256(rid.encode()).hexdigest()[:10]}]'
                                      if duplicate_names[names[rid]] > 1 else '')
        filename = 'reviews.csv' if len(groups) == 1 else 'reviews-' + hashlib.sha256(json.dumps(group).encode()).hexdigest()[:16] + '.csv'
        ordered = sorted(rows)
        with (out / filename).open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([*CASE_HEADERS, *[safe_cell(labels[rid] + ' ' + field)
                                             for rid in reviewers for field in ('Difficulty', 'Quality', 'Comment')]])
            for key in ordered:
                cells = list(key[0])
                for rid in reviewers:
                    observation = latest.get((key, rid), {})
                    # Legacy verdict remains in JSON/summary only; never reinterpret it.
                    difficulty = observation.get('difficulty', '')
                    quality = observation.get('quality', '')
                    cells.extend([difficulty if type(difficulty) is int and 1 <= difficulty <= 5 else '',
                                  quality if quality in ('pass', 'fail', 'uncertain') else '',
                                  observation.get('comment', '')])
                writer.writerow([safe_cell(c) for c in cells])
        index.append({'file': filename, 'mode': group[0], 'build_sha256': group[1],
                      'reviewers': [{'reviewer_id': rid, 'display_name': names[rid], 'column_label': labels[rid]} for rid in reviewers],
                      'rows': [{'csv_row': i + 2, 'case_snapshot': dict(zip(CASE_FIELDS, key[0])),
                                'revision': key[1], 'map_sha256': key[2]} for i, key in enumerate(ordered)]})
    (out / 'matrix-index.json').write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return index


def write_observations(data, out, mode=None, build_sha256=None):
    (out / 'observations.json').write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    counts = collections.defaultdict(collections.Counter)
    latest={}
    for row in sorted(data.get('feedback', []),key=lambda r:(float(r.get('created',0)),str(r.get('id','')))):
        key=(reviewer_id(row),)+tuple(str(row.get(k,'')) for k in ('task_id','revision','sha256','build_sha256','mode'))
        latest[key]=row
    for row in latest.values():
        if row.get('verdict') not in ('found', 'not_found', 'uncertain', 'technical_issue'):
            continue
        key = tuple(str(row.get(k, '')) for k in ('task_id', 'revision', 'sha256', 'build_sha256', 'mode', 'prior_exposure'))
        counts[key][row['verdict']] += 1
    with (out / 'summary.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['task_id', 'revision', 'map_sha256', 'build_sha256', 'mode', 'prior_exposure', 'found', 'not_found', 'uncertain', 'technical_issue'])
        for key, counts_for_key in sorted(counts.items()):
            writer.writerow([*[safe_cell(c) for c in key], *[counts_for_key[v] for v in ('found', 'not_found', 'uncertain', 'technical_issue')]])
    return write_matrices(data, out, mode, build_sha256)


def main():
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest='action', required=True)
    tokens = subs.add_parser('tokens')
    tokens.add_argument('reviewers', nargs='+', help='Stable reviewer IDs, e.g. alice bob')
    export = subs.add_parser('export')
    export.add_argument('--url', default='http://127.0.0.1:8090')
    export.add_argument('--out', required=True)
    export.add_argument('--mode', choices=('mock', 'external'), help='Filter CSV matrices only; complete JSON/evidence history retained')
    export.add_argument('--build-sha256', help='Filter CSV matrices only by exact build SHA256')
    args = parser.parse_args()
    if args.action == 'tokens':
        if len(set(args.reviewers)) != len(args.reviewers):
            parser.error('Reviewer IDs must be unique')
        print(json.dumps({secrets.token_urlsafe(32): {'id': name, 'reviewer': name} for name in args.reviewers}, ensure_ascii=False))
        return
    admin = os.environ.get('REVIEW_ADMIN_TOKEN')
    if not admin:
        parser.error('Set REVIEW_ADMIN_TOKEN')
    request = urllib.request.Request(args.url.rstrip('/') + '/api/admin/export', headers={'Authorization': 'Bearer ' + admin})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.load(response)
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    write_observations(data, out, args.mode, args.build_sha256)
    for row in data.get('evidence', []):
        identifier = row['id']
        if not identifier or any(c not in '0123456789abcdef' for c in identifier):
            raise RuntimeError('Invalid evidence ID')
        req = urllib.request.Request(args.url.rstrip('/') + '/api/admin/evidence/' + identifier, headers={'Authorization': 'Bearer ' + admin})
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read()
        if hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise RuntimeError('Evidence digest mismatch')
        dest = out / 'evidence'
        dest.mkdir(exist_ok=True)
        (dest / identifier).write_bytes(raw)
    print(str(out))
    print('Observations exported; no acceptance decisions changed.')


if __name__ == '__main__':
    main()
