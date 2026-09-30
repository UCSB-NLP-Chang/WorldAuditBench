import json, pathlib, tempfile, threading, unittest, urllib.request, urllib.error
from test_service import mod

class ReviewUpdates(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.s=mod.Store(pathlib.Path(self.tmp.name)/'db',{'tasks':[dict(id='S01',revision=1,map='/Game/Auditor/Subway/Concourse?Task=S01',sha256='a'*64,build_sha256='b'*64)]},tokens={'a':{'id':'a','reviewer':'Alice'},'b':{'id':'b','reviewer':'Bob'}})
  self.cookies={k:self.s.login(k,'')[0] for k in ('a','b')};self.users={k:self.s.auth(v) for k,v in self.cookies.items()}
 def tearDown(self):self.s.db.close();self.tmp.cleanup()
 def vote(self,who='a',quality='pass'):
  u=self.users[who];ss=self.s.create(u,'S01');self.s.tick();self.s.tick();fid=self.s.feedback(ss['id'],u,dict(difficulty=2,quality=quality,comment='original'));self.s.change(ss['id'],u,'close');self.s.tick();return fid
 def test_closed_session_update_preserves_identity_snapshot_and_history(self):
  fid=self.vote();old=self.s.reviews(self.users['a'])['S01'];self.assertEqual(self.s.reviews(self.users['b']),{})
  new=self.s.update_review(fid,self.users['a'],old|dict(comment='updated 中文',difficulty=4,reviewer_id='b',task_id='B01'))
  self.assertEqual(new['comment'],'updated 中文');self.assertEqual(new['difficulty'],4)
  self.assertEqual(self.s.db.execute('select count(*) from feedback').fetchone()[0],1)
  payload=json.loads(self.s.db.execute('select payload from feedback').fetchone()[0]);self.assertEqual(payload['reviewer_id'],'a');self.assertEqual(payload['sha256'],'a'*64);self.assertEqual(payload['task_id'],'S01')
  event=json.loads(self.s.db.execute("select detail from events where event='feedback_updated'").fetchone()[0]);self.assertEqual(event['previous_payload']['comment'],'original')
  with self.assertRaises(mod.Problem) as e:self.s.update_review(fid,self.users['a'],old|dict(comment='stale'))
  self.assertEqual(e.exception.status,409)
 def test_accepted_recomputed_without_duplicate_reviewer(self):
  fid=self.vote();self.vote('b');self.assertEqual(self.s.dashboard(self.users['a'])['counts']['accepted'],1)
  for quality,accepted in [('fail',0),('uncertain',0),('pass',1),('pass',1)]:
   old=self.s.reviews(self.users['a'])['S01'];self.s.update_review(fid,self.users['a'],old|dict(quality=quality));self.assertEqual(self.s.dashboard(self.users['a'])['counts']['accepted'],accepted)
  self.assertEqual(self.s.dashboard(self.users['a'])['tasks'][0]['approvals'],2)
 def test_superseded_version_and_older_session_cannot_be_updated(self):
  fid=self.vote();old=self.s.reviews(self.users['a'])['S01'];self.vote()
  with self.assertRaises(mod.Problem):self.s.update_review(fid,self.users['a'],old)
  current=self.s.reviews(self.users['a'])['S01'];self.s.tasks['S01']['revision']=2
  self.assertEqual(self.s.reviews(self.users['a']),{})
  with self.assertRaises(mod.Problem):self.s.update_review(current['feedback_id'],self.users['a'],current)
 def test_unrun_uncertain_cannot_turn_into_pass(self):
  u=self.users['a'];ss=self.s.create(u,'S01');self.s.change(ss['id'],u,'close');fid=self.s.feedback(ss['id'],u,dict(difficulty=1,quality='uncertain',comment='no game'))
  old=self.s.reviews(u)['S01']
  with self.assertRaises(mod.Problem):self.s.update_review(fid,u,old|dict(quality='pass'))
  self.assertEqual(self.s.update_review(fid,u,old|dict(comment='revised'))['comment'],'revised')
 def test_http_owner_validation_csrf_and_refresh(self):
  fid=self.vote();http=mod.make_server(self.s,port=0);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();url=f'http://127.0.0.1:{http.server_port}'
  def req(path,who='a',body=None,origin=None):
   headers={'Cookie':'review_session='+self.cookies.get(who,'bad')}
   if body is not None:headers.update({'Origin':origin or url,'Content-Type':'application/json'})
   try:return urllib.request.urlopen(urllib.request.Request(url+path,headers=headers,data=None if body is None else json.dumps(body).encode()))
   except urllib.error.HTTPError as e:return e
  try:
   self.assertEqual(req('/api/reviews',who='x').status,401)
   self.assertEqual(json.load(req('/api/reviews',who='b'))['reviews'],{})
   old=json.load(req('/api/reviews'))['reviews']['S01']
   self.assertEqual(req('/api/reviews/'+fid,who='b',body=old).status,404)
   self.assertEqual(req('/api/reviews/'+fid,body=old,origin='https://wrong.example').status,403)
   self.assertEqual(req('/api/reviews/'+fid,body=old|dict(difficulty=True)).status,400)
   self.assertEqual(req('/api/reviews/'+fid,body=old|dict(comment='saved through HTTP')).status,200)
   self.assertEqual(json.load(req('/api/reviews'))['reviews']['S01']['comment'],'saved through HTTP')
  finally:http.shutdown();http.server_close();thread.join()
