#!/usr/bin/env python3
"""Consistent per-service SQLite backups with only referenced evidence copied."""
import argparse
import datetime
import hashlib
import json
import pathlib
import shutil
import sqlite3

parser = argparse.ArgumentParser()
parser.add_argument('state', type=pathlib.Path)
parser.add_argument('destination', type=pathlib.Path)
parser.add_argument('--app', required=True, choices=['exploration', 'evaluation'])
args = parser.parse_args()
database = args.app + '.sqlite3'
target = args.destination / (args.app + '-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
target.mkdir(parents=True, mode=0o700)
with sqlite3.connect('file:' + str(args.state / database) + '?mode=ro', uri=True) as source, sqlite3.connect(target / database) as snapshot:
    source.backup(snapshot)
    assert snapshot.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    rows = snapshot.execute('SELECT id,sha256 FROM ' + ('flags' if args.app == 'exploration' else 'evidence')).fetchall()
    (target / 'evidence').mkdir(mode=0o700)
    for eid, sha256 in rows:
        src = args.state / 'evidence' / eid
        assert hashlib.sha256(src.read_bytes()).hexdigest() == sha256
        shutil.copyfile(src, target / 'evidence' / eid)
(target / 'backup.json').write_text(json.dumps({'app': args.app, 'database': database, 'evidence_count': len(rows), 'integrity_check': 'ok'}, indent=2))
print(target)
