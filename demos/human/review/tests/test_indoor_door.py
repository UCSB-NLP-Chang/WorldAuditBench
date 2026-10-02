import copy,json,tempfile,unittest
from pathlib import Path
from server import Store
from taxonomy import classify
ROOT=Path(__file__).resolve().parents[1]
class IndoorDoorTests(unittest.TestCase):
 def test_new_door_task_and_deleted_plumbing(self):
  manifest=json.loads((ROOT/'tasks.json').read_text());t=next(x for x in manifest['tasks'] if x['id']=='H15')
  self.assertEqual(classify(t)['code'],'C1');self.assertEqual(t['family'],'indoor');self.assertIn('BedroomSuite?Task=H15',t['map'])
  self.assertNotIn('H14',{x['id'] for x in manifest['tasks']})
  with tempfile.TemporaryDirectory() as d:
   store=Store(Path(d)/'ok.db',{'tasks':[t]});store.db.close()
   stale=copy.deepcopy(t);stale['id']='H14'
   with self.assertRaises(ValueError):Store(Path(d)/'bad.db',{'tasks':[stale]})
