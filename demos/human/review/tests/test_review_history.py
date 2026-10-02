import json,pathlib,threading,unittest,urllib.request,urllib.error
from unittest.mock import patch
from test_review_updates import ReviewUpdates,mod
class ReviewHistory(unittest.TestCase):
 setUp=ReviewUpdates.setUp
 tearDown=ReviewUpdates.tearDown
 vote=ReviewUpdates.vote
 def test_all_edits_and_new_sessions_retained_latest_vote_only(self):
  fid=self.vote();self.vote('b');u=self.users['a']
  for quality in ('fail','uncertain','pass'):
   old=self.s.reviews(u)['S01'];self.s.update_review(fid,u,old|dict(quality=quality,comment=quality))
   self.assertEqual(self.s.dashboard(u)['tasks'][0]['approvals'],2 if quality=='pass' else 1)
  self.vote(quality='fail')
  h=self.s.review_history(u);self.assertEqual([x['quality'] for x in h],['pass','fail','uncertain','pass','fail'])
  self.assertEqual(h[0]['comment'],'original');self.assertEqual(len({x['history_id'] for x in h}),5)
  self.assertEqual(len(self.s.review_history(self.users['b'])),1)
  self.assertEqual(self.s.reviews(u)['S01']['quality'],'fail');self.assertEqual(self.s.dashboard(u)['tasks'][0]['approvals'],1)
 def test_retry_first_submission_does_not_append(self):
  fid=self.vote();old=self.s.reviews(self.users['a'])['S01'];before=self.s.review_history()
  result=self.s.feedback(old['session_id'],self.users['a'],dict(difficulty=5,quality='fail',comment='retry'))
  self.assertEqual(result,fid);self.assertEqual(before,self.s.review_history())
 def test_atomic_update_rolls_back_on_history_failure(self):
  fid=self.vote();u=self.users['a'];old=self.s.reviews(u)['S01'];before=self.s.review_history()
  with patch.object(self.s,'append_review_history',side_effect=RuntimeError('disk write error')):
   with self.assertRaises(RuntimeError):self.s.update_review(fid,u,old|dict(quality='fail'))
  self.assertEqual(self.s.reviews(u)['S01'],old);self.assertEqual(self.s.review_history(),before)
  self.assertEqual(self.s.db.execute("select count(*) from events where event='feedback_updated'").fetchone()[0],0)
 def test_atomic_first_submission(self):
  u=self.users['a'];ss=self.s.create(u,'S01');self.s.tick();self.s.tick()
  with patch.object(self.s,'append_review_history',side_effect=RuntimeError('disk write error')):
   with self.assertRaises(RuntimeError):self.s.feedback(ss['id'],u,dict(difficulty=3,quality='pass'))
  self.assertEqual(self.s.db.execute('select count(*) from feedback').fetchone()[0],0)
 def test_legacy_migration_and_repeat_start_preserve_original_rows(self):
  fid=self.vote();u=self.users['a'];self.s.update_review(fid,u,self.s.reviews(u)['S01']|dict(comment='second'))
  self.s.update_review(fid,u,self.s.reviews(u)['S01']|dict(comment='third'))
  before=[tuple(r) for r in self.s.db.execute('select * from feedback')]
  # Simulate the old deployed schema, which has only current rows and edit events.
  self.s.db.execute('drop table review_history');self.s.db.execute('drop table review_history_migrations');self.s.db.commit()
  self.s.migrate_review_history();h=self.s.review_history(u)
  self.assertEqual([x['comment'] for x in h],['original','second','third'])
  self.assertEqual(before,[tuple(r) for r in self.s.db.execute('select * from feedback')])
  self.s.migrate_review_history();self.assertEqual(h,self.s.review_history(u))
 def test_versions_stay_in_history_but_not_current_statistics(self):
  self.vote();u=self.users['a'];self.s.tasks['S01']['build_sha256']='c'*64
  self.assertEqual(self.s.reviews(u),{});self.assertEqual(self.s.dashboard(u)['tasks'][0]['approvals'],0)
  self.assertEqual(self.s.review_history(u)[0]['build_sha256'],'b'*64)
 def test_http_history_is_owner_only_and_admin_export_complete(self):
  self.vote();self.vote('b');self.s.admin_token='test-admin'
  http=mod.make_server(self.s,port=0);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
  def get(path,headers):
   try:return urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{http.server_port}'+path,headers=headers))
   except urllib.error.HTTPError as e:return e
  try:
   self.assertEqual(get('/api/reviews/history',{}).status,401)
   history=json.load(get('/api/reviews/history',{'Cookie':'review_session='+self.cookies['a']}))['review_history']
   self.assertEqual(len(history),1);self.assertEqual(history[0]['reviewer_id'],'a')
   exported=json.load(get('/api/admin/export',{'Authorization':'Bearer test-admin'}));self.assertEqual(len(exported['review_history']),2)
  finally:http.shutdown();http.server_close();thread.join()
