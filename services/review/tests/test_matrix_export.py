import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('review_manage', Path(__file__).resolve().parents[1] / 'manage.py')
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)


def task(number=11, revision=1, **overrides):
    value = dict(id=f'U{number:03}', environment='Urban', case_id=f'U{number:03}-R{revision:02}',
                 rubrics='Find anomaly', case_path=f'/Game/Tasks/U{number}/R{revision}',
                 case_type='geometry', revision=revision, sha256=str(number) * 32)
    value.update(overrides)
    return value


def feedback(identity='alice', name='Alice', created=1, source=None, **overrides):
    source = dict(source or task())
    source['task_id'] = source.pop('id')
    source.update(id=f'{identity}-{created}', reviewer_id=identity, reviewer=name, created=created,
                  mode='external', build_sha256='a' * 64, difficulty=3, quality='pass', comment='Readable')
    source.update(overrides)
    return source


class MatrixExportTest(unittest.TestCase):
    def export(self, feedback_rows, tasks=None, **filters):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        out = Path(temp.name)
        data = dict(tasks=tasks if tasks is not None else [task(), task(12)], feedback=feedback_rows,
                    evidence=[], mode='external', build_sha256='a' * 64)
        index = manage.write_observations(data, out, **filters)
        matrices = []
        for item in index:
            with (out / item['file']).open(encoding='utf-8-sig', newline='') as f:
                matrices.append(list(csv.reader(f)))
        return out, index, matrices

    def test_two_reviewers_columns_and_unreviewed_case(self):
        out, index, matrices = self.export([feedback(), feedback('bob', 'Bob', quality='fail', difficulty=5)])
        matrix = matrices[0]
        self.assertEqual(matrix[0][:5], list(manage.CASE_HEADERS))
        self.assertEqual(matrix[0][5:], ['Alice Difficulty', 'Alice Quality', 'Alice Comment', 'Bob Difficulty', 'Bob Quality', 'Bob Comment'])
        self.assertEqual(matrix[1][5:], ['3', 'pass', 'Readable', '5', 'fail', 'Readable'])
        self.assertEqual(matrix[2][5:], [''] * 6)
        self.assertTrue((out / 'reviews.csv').read_bytes().startswith(b'\xef\xbb\xbf'))

    def test_latest_same_identity_keeps_all_history(self):
        original = feedback(created=10, quality='fail', comment='old')
        newer = feedback(created=20, difficulty=1, comment='new')
        out, _, matrices = self.export([newer, original])
        self.assertEqual(matrices[0][1][5:], ['1', 'pass', 'new'])
        self.assertEqual(len(json.loads((out / 'observations.json').read_text())['feedback']), 2)

    def test_legacy_verdict_not_quality(self):
        old = feedback(verdict='found')
        for key in ('difficulty', 'quality', 'comment'):
            old.pop(key)
        out, _, matrices = self.export([old])
        self.assertEqual(matrices[0][1][5:], ['', '', ''])
        with (out / 'summary.csv').open(encoding='utf-8-sig') as f:
            summary = list(csv.reader(f))
        self.assertEqual(summary[1][6:], ['1', '0', '0', '0'])

    def test_same_display_name_gets_distinct_stable_columns(self):
        _, index, matrices = self.export([feedback('owner-one', 'Same'), feedback('owner-two', 'Same', quality='fail')])
        labels = [r['column_label'] for r in index[0]['reviewers']]
        self.assertEqual(len(set(labels)), 2)
        self.assertTrue(all(label.startswith('Same [') for label in labels))
        self.assertEqual(matrices[0][1][6], 'pass')
        self.assertEqual(matrices[0][1][9], 'fail')

    def test_mode_build_grouping_and_revision_rows(self):
        rows = [feedback(), feedback(created=2, source=task(revision=2)),
                feedback(created=3, mode='mock'), feedback(created=4, build_sha256='b' * 64)]
        _, index, matrices = self.export(rows)
        self.assertEqual(len(index), 3)
        self.assertEqual(len({x['file'] for x in index}), 3)
        current = next(i for i, item in enumerate(index) if item['mode'] == 'external' and item['build_sha256'] == 'a' * 64)
        self.assertEqual([r[1] for r in matrices[current][1:]], ['U011-R01', 'U011-R02', 'U012-R01'])
        historical = next(i for i, item in enumerate(index) if item['build_sha256'] == 'b' * 64)
        self.assertEqual(len(matrices[historical]), 2)  # current manifest does not leak into old build
        _, filtered, _ = self.export(rows, mode='mock', build_sha256='a' * 64)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]['file'], 'reviews.csv')

    def test_snapshot_preserved_and_formula_text_safe(self):
        historical = task(rubrics='Old rubric', case_path='=HYPERLINK("evil")')
        _, _, matrices = self.export([feedback(source=historical, comment='  =SUM(1,2)', name='@attacker')])
        matching = next(row for row in matrices[0][1:] if row[2] == 'Old rubric')
        self.assertTrue(matching[3].startswith("'="))
        self.assertEqual(matching[7], "'  =SUM(1,2)")
        self.assertTrue(matrices[0][0][5].startswith("'@"))
        self.assertEqual(len(matrices[0]), 4)  # changed snapshot not merged into current row

    def test_empty_feedback_exports_all_tasks(self):
        _, _, matrices = self.export([])
        self.assertEqual(len(matrices[0]), 3)
        self.assertEqual(matrices[0][0], list(manage.CASE_HEADERS))


if __name__ == '__main__':
    unittest.main()
