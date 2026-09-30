import json,unittest,pathlib
import test_dashboard
from server import Store
class ReviewContinuityTests(unittest.TestCase):
 setUp=test_dashboard.DashboardTests.setUp
 tearDown=test_dashboard.DashboardTests.tearDown
 vote=test_dashboard.DashboardTests.vote
 def upgrade(self):
  t=self.s.tasks['S01'];old={k:t[k] for k in ('revision','sha256','build_sha256')};t.update(revision=2,sha256='c'*64,build_sha256='d'*64,review_compatible_versions=[old]);return old
 def test_unchanged_task_restores_own_and_shared_progress(self):
  a,b=self.users[:2];self.vote(a,'pass');self.vote(b,'pass');old=self.upgrade()
  self.assertIn('S01',self.s.reviews(a));self.assertEqual(self.s.dashboard(a)['counts']['accepted'],1)
  peer=self.s.task_reviews('S01',a)[0];self.assertFalse(peer['current_version']);self.assertTrue(peer['counts_toward_current'])
  self.vote(a,'fail');row=self.s.dashboard(a)['tasks'][0];self.assertEqual(row['reviews'],2);self.assertEqual(row['approvals'],1);self.assertEqual(row['my_quality'],'fail')
  votes=[v for v in self.s.task_reviews('S01',self.users[2]) if v['reviewer']==a['reviewer']];self.assertEqual(sum(v['counts_toward_current'] for v in votes),1);self.assertEqual(next(v['quality'] for v in votes if v['counts_toward_current']),'fail')
 def test_unknown_or_changed_versions_remain_excluded(self):
  a=self.users[0];self.vote(a,'pass');self.upgrade();self.s.tasks['S01']['review_compatible_versions'][0]['sha256']='e'*64
  self.assertNotIn('S01',self.s.reviews(a));self.assertEqual(self.s.dashboard(a)['tasks'][0]['reviews'],0)
  self.assertFalse(self.s.task_reviews('S01',self.users[1])[0]['counts_toward_current'])
 def test_reads_preserve_original_feedback_and_history(self):
  a=self.users[0];self.vote(a,'pass');self.upgrade();before=[tuple(x) for x in self.s.db.execute('select * from feedback')];history=self.s.review_history()
  self.s.dashboard(a);self.s.reviews(a);self.s.task_reviews('S01',self.users[1])
  self.assertEqual(before,[tuple(x) for x in self.s.db.execute('select * from feedback')]);self.assertEqual(history,self.s.review_history())
 def test_editing_compatible_review_keeps_original_version(self):
  a=self.users[0];self.vote(a,'pass');old=self.upgrade();v=self.s.reviews(a)['S01'];self.s.update_review(v['feedback_id'],a,dict(updated_at=v['updated_at'],difficulty=3,quality='uncertain',comment='Updated comment'))
  payload=json.loads(self.s.db.execute('select payload from feedback').fetchone()[0]);self.assertEqual({k:payload[k] for k in old},old);self.assertEqual(len(self.s.review_history()),2)
 def test_s19_rubrics_describe_all_escalators_without_a_count(self):
  data=json.loads((pathlib.Path(__file__).resolve().parents[1]/'tasks.json').read_text());t=next(t for t in data['tasks'] if t['id']=='S19')
  self.assertIn('所有',t['rubrics_i18n']['zh']['criteria']);self.assertIn('All escalators',t['rubrics_i18n']['en']['criteria']);self.assertNotRegex(json.dumps(t['rubrics_i18n'],ensure_ascii=False),r'8|eight|八|4|four|四')
