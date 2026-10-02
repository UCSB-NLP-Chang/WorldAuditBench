import json,pathlib,tempfile,unittest
from unittest.mock import patch
from urllib.parse import parse_qs,urlsplit
from test_service import mod
ROOT=pathlib.Path(__file__).resolve().parents[1]
class BrowserReviewTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.items=[t for t in json.loads((ROOT/'tasks.json').read_text())['tasks'] if t.get('runtime_kind')=='browser']
  native=dict(id='S01',map='/Game/Auditor/Subway/Concourse?Task=S01',family='subway',revision=1,sha256='a'*64,build_sha256='b'*64)
  self.s=mod.Store(pathlib.Path(self.tmp.name)/'db',{'tasks':[native]+self.items},capacity=1,tokens={x:dict(id=x,reviewer=x) for x in 'ABCD'})
  self.users={x:self.s.auth(self.s.login(x,'')[0]) for x in 'ABCD'}
 def tearDown(self):self.s.db.close();self.tmp.cleanup()
 def ack(self,row,user='A'):
  return self.s.browser_report(row['id'],self.users[user],dict(task_id=row['task_id'],load_id=parse_qs(urlsplit(row['stream_url']).query)['load_id'][0]))
 def test_browser_runs_while_gpu_full_and_keeps_fifo(self):
  a=self.s.create(self.users['A'],'S01');self.s.tick();self.s.tick();b=self.s.create(self.users['B'],'S01')
  c=self.s.create(self.users['C'],'JS_SP01');self.assertEqual(c['status'],'starting');self.ack(c,'C')
  with patch.object(self.s,'call_runner',wraps=self.s.call_runner) as call:self.s.tick();self.assertEqual(len(call.call_args_list),1);self.assertEqual(call.call_args.args[1]['task_id'],'S01')
  self.assertIsNone(self.s.owned(c['id'],self.users['C'])['slot']);self.assertEqual(self.s.current(self.users['B'])['status'],'queued')
  self.s.change(c['id'],self.users['C'],'close');self.assertEqual(self.s.current(self.users['B'])['queue_position'],1)
 def test_requires_readiness_and_matching_owner_case_attempt(self):
  a=self.s.create(self.users['A'],'JS_SP01');data=dict(task_id='JS_SP01',load_id=parse_qs(urlsplit(a['stream_url']).query)['load_id'][0])
  for user,d in [('B',data),('A',data|dict(task_id='JS_SP02')),('A',data|dict(load_id='stale'))]:
   with self.assertRaises(mod.Problem):self.s.browser_report(a['id'],self.users[user],d)
  with self.assertRaises(mod.Problem):self.s.feedback(a['id'],self.users['A'],dict(difficulty=3,quality='pass'))
  self.ack(a);self.assertEqual(self.ack(a)['status'],'ready')
 def test_reviews_snapshots_two_people_and_updates(self):
  for user in ['A','B']:
   a=self.s.create(self.users[user],'JS_SP01');self.ack(a,user);self.s.feedback(a['id'],self.users[user],dict(difficulty=3,quality='pass',comment=user));self.s.change(a['id'],self.users[user],'close')
  self.assertEqual(self.s.dashboard(self.users['A'])['counts']['accepted'],1)
  review=self.s.reviews(self.users['A'])['JS_SP01'];self.s.update_review(review['feedback_id'],self.users['A'],review|dict(difficulty=3,quality='fail'))
  self.assertEqual(self.s.dashboard(self.users['A'])['counts']['accepted'],0);self.assertEqual(len(self.s.review_history()),3)
  snapshot=json.loads(self.s.db.execute('SELECT payload FROM feedback LIMIT 1').fetchone()[0]);self.assertEqual(snapshot['runtime_kind'],'browser');self.assertEqual(snapshot['source_case'],'sp01-float');self.assertEqual(snapshot['build_sha256'],self.items[1]['build_sha256'])
 def test_switch_across_browser_worlds_keeps_feedback_separate(self):
  old=self.s.create(self.users['A'],'JS_SP01');self.ack(old);self.s.feedback(old['id'],self.users['A'],dict(difficulty=3,quality='pass',comment='Sponza'))
  new=self.s.switch_task(old['id'],self.users['A'],'JS_CT01');self.assertNotEqual(new['id'],old['id']);self.assertEqual(new['status'],'starting');self.assertEqual(self.s.owned(old['id'],self.users['A'])['status'],'closed')
  self.ack(new);self.s.feedback(new['id'],self.users['A'],dict(difficulty=3,quality='fail',comment='Cottage'))
  self.assertEqual(set(self.s.reviews(self.users['A'])),{'JS_SP01','JS_CT01'})
  with patch.object(self.s,'call_runner',side_effect=AssertionError('GPU runner called')):self.s.tick();self.s.change(new['id'],self.users['A'],'close');self.s.tick()
 def test_reset_new_attempt_rejects_old_ack(self):
  old=self.s.create(self.users['A'],'JS_SP01');self.ack(old);new=self.s.change(old['id'],self.users['A'],'reset');self.assertNotEqual(new['stream_url'],old['stream_url'])
  with self.assertRaises(mod.Problem):self.ack(old)
  self.assertEqual(self.ack(new)['status'],'ready')
 def test_failure_expiry_and_close_no_gpu_cleanup(self):
  old=self.s.create(self.users['A'],'JS_SP01');data=dict(task_id=old['task_id'],load_id=parse_qs(urlsplit(old['stream_url']).query)['load_id'][0]);self.s.browser_report(old['id'],self.users['A'],data,failed=True)
  with self.assertRaises(mod.Problem):self.s.feedback(old['id'],self.users['A'],dict(difficulty=3,quality='pass'))
  self.s.feedback(old['id'],self.users['A'],dict(difficulty=3,quality='uncertain'))
  row=self.s.create(self.users['A'],'JS_SP02');self.s.db.execute('UPDATE sessions SET heartbeat=0 WHERE id=?',(row['id'],));self.s.db.commit()
  with patch.object(self.s,'call_runner',side_effect=AssertionError('GPU runner called')):self.s.tick()
  self.assertEqual(self.s.current(self.users['A'])['status'],'closed')
 def test_all_browser_tasks_validate_and_source_urls_are_pinned(self):
  self.assertEqual(len(self.items),96);self.assertEqual(sum(t['case_type']=='baseline' for t in self.items),6)
  for key,value in [('map','https://evil.example/'),('source_case','sp02-clip'),('family','threejs_house'),('build_sha256','invalid')]:
   bad=dict(self.items[1]);bad[key]=value
   with self.assertRaises(ValueError):mod.Store(pathlib.Path(self.tmp.name)/('bad-'+key),{'tasks':[bad]})
 def test_browser_cannot_reuse_unreal_slot(self):
  old=self.s.create(self.users['A'],'JS_SP01');self.ack(old)
  with self.assertRaises(mod.Problem):self.s.switch_task(old['id'],self.users['A'],'S01')
 def test_readiness_event_allows_later_edit_of_closed_browser_review(self):
  a=self.s.create(self.users['A'],'JS_SP01');self.ack(a);self.s.change(a['id'],self.users['A'],'close');fid=self.s.feedback(a['id'],self.users['A'],dict(difficulty=3,quality='pass'))
  r=self.s.reviews(self.users['A'])['JS_SP01'];self.s.update_review(fid,self.users['A'],r|dict(difficulty=1,quality='fail'))
  self.assertEqual(self.s.reviews(self.users['A'])['JS_SP01']['quality'],'fail')
