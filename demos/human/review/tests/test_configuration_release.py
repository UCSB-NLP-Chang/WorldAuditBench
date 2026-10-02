import json,unittest,tempfile
from pathlib import Path
from test_linux_runtime import server,ROOT
class ConfigurationReleaseTests(unittest.TestCase):
 def test_replacements_new_cases_and_scene_membership(self):
  tasks=json.loads((ROOT/'tasks.json').read_text());byid={t['id']:t for t in tasks['tasks']}
  self.assertEqual(len(byid),250)
  self.assertFalse({'S15','S17','U039','H16'}&byid.keys())
  self.assertEqual({t['id'] for t in json.loads((ROOT/'configuration-backup-cases.json').read_text())['tasks']},{'S17','U039'})
  self.assertIn('KitchenDining',byid['H13']['map']);self.assertIn('Courtyard',byid['A18']['map'])
  for tid in ['S18','H13','U046','A18','I19','R12','MV17']:self.assertEqual(byid[tid]['subcategory'],'S2')
  for tid in ['A21','A22','A23','A24']:self.assertIn(tid,byid)
  scenes=json.loads((ROOT/'review-scene-descriptions.json').read_text())['scenes']
  for tid in ['S18','H13','U046','A18','I19','R12','MV17']:self.assertEqual(sum(tid in s['task_ids'] for s in scenes),1)
  with tempfile.TemporaryDirectory() as d:
   store=server.Store(Path(d)/'test.db',tasks,capacity=3)
   try:
    self.assertFalse({'S15','S17','U039'}&store.tasks.keys());self.assertEqual(store.tasks['I19']['family'],'industrial');self.assertEqual(store.tasks['U046']['family'],'urban')
   finally:store.db.close()
