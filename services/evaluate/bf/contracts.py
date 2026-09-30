"""Versioned import contract shared by the two applications."""
import re
from .common import require
from .taxonomy import category

VERDICTS = ('correct', 'partial', 'incorrect', 'insufficient', 'additional_bug')
EMPTY_VERDICTS = ('correct_none', 'missed', 'insufficient')


def identifier(value):
    require(isinstance(value, str) and re.fullmatch('[a-f0-9]{32}', value), 'Invalid identifier')
    return value


def validate_envelope(payload):
    require(isinstance(payload, dict) and payload.get('schema_version') == 1, 'Unsupported submission schema')
    for key in ('id', 'task_version_id', 'attempt_id'):
        identifier(payload.get(key))
    require(payload.get('outcome') in ('reports', 'none'), 'Invalid outcome')
    require(isinstance(payload.get('explorer_name', ''), str) and len(payload.get('explorer_name', '')) <= 100, 'Invalid explorer name')
    require(type(payload.get('test_submission', False)) is bool, 'Invalid test cohort')
    require(isinstance(payload.get('query'), str) and 0 < len(payload['query']) <= 10000, 'Invalid query')
    require(isinstance(payload.get('reports'), list) and len(payload['reports']) <= 20, 'Invalid reports')
    require(bool(payload['reports']) == (payload['outcome'] == 'reports'), 'Outcome mismatch')
    evidence = payload.get('evidence')
    require(isinstance(evidence, list) and len(evidence) <= 30, 'Invalid evidence')
    ids = set()
    for item in evidence:
        eid = identifier(item.get('id'))
        require(eid not in ids, 'Duplicate evidence')
        ids.add(eid)
        require(re.fullmatch('[a-f0-9]{64}', item.get('sha256', '')), 'Invalid evidence hash')
        require(item.get('mime') == 'image/png' and 0 < item.get('size', 0) <= 5 * 1024 * 1024, 'Invalid image')
    report_ids = set()
    for report in payload['reports']:
        rid = identifier(report.get('id'))
        require(rid not in report_ids, 'Duplicate report')
        report_ids.add(rid)
        require(isinstance(report.get('description'), str) and 0 < len(report['description'].strip()) <= 10000, 'Invalid description')
        category(report.get('category', 'unsure'))
        linked = report.get('evidence_ids')
        require(isinstance(linked, list) and linked and set(linked) <= ids, 'Invalid evidence association')
