import json,pathlib,unittest
from taxonomy import classify
ROOT=pathlib.Path(__file__).resolve().parents[1]
class EntryReleaseTests(unittest.TestCase):
 def test_new_door_and_revised_lions_have_distinct_current_versions(self):
  tasks={t['id']:t for t in json.loads((ROOT/'tasks.json').read_text())['tasks']}
  self.assertEqual(tasks['A19']['revision'],7)
  self.assertEqual(tasks['A25']['revision'],1)
  for tid in ['A19','A25']:
   t=tasks[tid]
   self.assertEqual(classify(t)['code'],'S2')
   self.assertEqual(t['map'],'/Game/Auditor/AncientCity/Courtyard?Task='+tid)
   self.assertEqual(t['case_path'],'/?case='+tid)
   self.assertNotIn('review_compatible_versions',t)
   self.assertTrue(t['rubrics_i18n']['zh']['criteria'])
   self.assertTrue(t['rubrics_i18n']['en']['criteria'])
  for tid in ['A14','A15','A16']:
   self.assertEqual(tasks[tid]['revision'],7)
   self.assertNotIn('review_compatible_versions',tasks[tid])
