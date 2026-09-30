"""Install as tests/test_industrial.py in the candidate review release."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from test_linux_runtime import server, ROOT


class IndustrialReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.entries = [task for task in json.loads((ROOT / 'tasks.json').read_text())['tasks']
                        if task.get('family') == 'industrial']

    def tearDown(self):
        self.temporary.cleanup()

    def test_catalog_taxonomy_and_clean_controls(self):
        self.assertEqual(len(self.entries), 21)
        store = server.Store(self.root / 'test.db', {'tasks': self.entries}, capacity=3)
        try:
            self.assertEqual(sum(task['case_type'] == 'baseline' for task in store.tasks.values()), 3)
            self.assertEqual({task['id'] for task in self.entries if task['case_type'] == 'bug'},
                             {f'I{i:02}' for i in range(1, 19)})
            for task in store.tasks.values():
                self.assertTrue(task['runtime_switch'])
                self.assertEqual('taxonomy' in task, task['case_type'] == 'bug')
                for lang in ('zh', 'en'):
                    for key in ('criteria', 'steps', 'expected'):
                        self.assertTrue(task['rubrics_i18n'][lang][key].strip())
            owner = store.auth(store.login('local-demo', 'Industrial QA')[0])
            dashboard = store.dashboard(owner)
            self.assertEqual(dashboard['counts'], dict(environments=1, scenes=3, tasks=18, baselines=3, accepted=0))
            self.assertEqual(dashboard['capacity'], 3)
        finally:
            store.db.close()

    def test_rejects_unknown_ids_wrong_world_and_cross_task(self):
        task = next(task for task in self.entries if task['id'] == 'I01')
        changes = [{'id': 'I19'}, {'id': 'IB04'},
                   {'map': '/Game/Auditor/Subway/Concourse?Task=I01'},
                   {'map': task['map'].replace('?Task=I01', '?Task=I02')},
                   {'map': task['map'] + ' -ExecCmds=quit'}]
        for index, change in enumerate(changes):
            with self.assertRaises(ValueError):
                server.Store(self.root / str(index), {'tasks': [task | change]})
        broken = copy.deepcopy(task)
        del broken['rubrics_i18n']['en']['criteria']
        with self.assertRaises(ValueError):
            server.Store(self.root / 'translation', {'tasks': [broken]})

    def test_runtime_profiles_match_the_new_binary(self):
        profiles = json.loads((ROOT / 'industrial-runtime-profiles.json').read_text())
        for task in self.entries:
            profile = profiles[task['map']]
            self.assertEqual(profile['family'], 'industrial')
            self.assertEqual(profile['build_sha256'], task['build_sha256'])
            self.assertTrue(profile['runtime_switch'])
            self.assertIn('-sm5', profile['game_args'])
            self.assertNotIn('-sm6', profile['game_args'])
            self.assertIn('-ExecCmds=t.MaxFPS 30', profile['game_args'])
