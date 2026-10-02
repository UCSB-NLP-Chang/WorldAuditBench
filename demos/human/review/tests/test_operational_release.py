import unittest,json,tempfile
from pathlib import Path
from server import Store
class OperationalReleaseTests(unittest.TestCase):
 def test_new_cases_and_changed_door(self):
  root=Path(__file__).resolve().parents[1];m=json.loads((root/'tasks.json').read_text());by={t['id']:t for t in m['tasks']}
  self.assertGreaterEqual(len(by),250)
  for tid in ['I20','I21','A17']:
   self.assertEqual(by[tid]['subcategory'],'T3')
   # Rebuilds may retain reviews of the same behavior, never the retired door behavior.
   for version in by[tid].get('review_compatible_versions',[]):
    self.assertEqual(version['revision'],by[tid]['revision'])
    if tid=='A17':self.assertGreaterEqual(version['revision'],7)
   self.assertNotRegex(json.dumps(by[tid]['rubrics_i18n']),r'replace|WASD|pressing E')
  self.assertIn('closes',by['A17']['title']);self.assertEqual(by['I20']['revision'],1)
  with tempfile.TemporaryDirectory() as tmp:
   store=Store(Path(tmp)/'qa.sqlite',m,mode='external',tokens={'qa':{'id':'qa','reviewer':'Technical QA'}},runner=['/usr/bin/true'],build_sha='f'*64)
   for tid in ['I20','I21','A17']:self.assertEqual(store.tasks[tid]['taxonomy']['code'],'T3')
   store.db.close()
 def test_unchanged_family_entries_keep_previous_versions(self):
  root=Path(__file__).resolve().parents[1];m=json.loads((root/'tasks.json').read_text())
  for t in m['tasks']:
   if t.get('family') in ['industrial','ancient'] and t['id'] not in ['A13', 'A14', 'A15', 'A16', 'A17', 'A19', 'A25', 'B01', 'B02', 'H10', 'H11', 'I10', 'I11', 'I12', 'I18', 'I20', 'I21', 'IB03', 'R11', 'R16', 'R17', 'S05', 'S13', 'S14', 'S16', 'S21']:self.assertGreater(len(t['review_compatible_versions']),0)
 def test_shared_scene_and_task_registration(self):
  root=Path(__file__).resolve().parents[1];x=json.loads((root/'review-scene-descriptions.json').read_text())['scenes']
  for tid in ['I20','I21']:self.assertEqual(sum(tid in s['task_ids'] for s in x),1)

