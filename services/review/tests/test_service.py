import importlib.util,json,pathlib,tempfile,unittest,threading,urllib.request,urllib.error,concurrent.futures,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('review_server',ROOT/'server.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
MANIFEST=json.loads((ROOT/'tests/legacy-manifest.json').read_text())
class ServiceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=mod.Store(pathlib.Path(self.tmp.name)/'db',MANIFEST,capacity=1,tokens={'a':{'id':'alice','reviewer':'Alice'},'b':{'id':'bob','reviewer':'Bob'}})
  self.a=self.s.auth(self.s.login('a','spoof')[0]);self.b=self.s.auth(self.s.login('b','spoof')[0])
 def tearDown(self):self.s.db.close();self.tmp.cleanup()
 def ready(self,u):
  r=self.s.create(u);self.s.tick();self.s.tick();return self.s.current(u)
 def test_all_18_maps_and_no_answers(self):
  self.assertEqual(len(self.s.tasks),18);self.assertNotIn('kind',json.dumps(self.s.tasks))
 def test_capacity_queue_and_release(self):
  a=self.ready(self.a);b=self.s.create(self.b);self.s.tick();self.assertEqual(self.s.current(self.b)['status'],'queued');self.assertEqual(self.s.current(self.b)['queue_position'],1)
  self.s.change(a['id'],self.a,'close');self.s.tick();self.s.tick();self.assertEqual(self.s.current(self.b)['status'],'ready')
 def test_concurrent_create_one_session_per_reviewer(self):
  with concurrent.futures.ThreadPoolExecutor(8) as pool:r=list(pool.map(lambda _:self.s.create(self.a),range(20)))
  self.assertEqual(len({x['id'] for x in r}),1)
 def test_reset_runs_cleanup_then_new_start(self):
  a=self.ready(self.a);calls=[];old=self.s.call_runner
  self.s.call_runner=lambda op,s:(calls.append(op) or old(op,s))
  self.s.change(a['id'],self.a,'reset');self.s.tick();self.s.tick();self.assertEqual(calls[:2],['stop','start']);self.assertEqual(self.s.current(self.a)['status'],'ready')
 def test_expired_session_reclaimed(self):
  a=self.ready(self.a);self.s.db.execute('UPDATE sessions SET heartbeat=?',(0,));self.s.db.commit();self.s.tick();self.assertEqual(self.s.current(self.a)['status'],'closed')
 def test_feedback_snapshot_and_idempotency(self):
  a=self.ready(self.a);d={'verdict':'found','description':'问题描述','location':'路口','steps':'走近','confidence':4,'prior_exposure':True}
  fid=self.s.feedback(a['id'],self.a,d);self.assertEqual(fid,self.s.feedback(a['id'],self.a,d))
  p=json.loads(self.s.db.execute('SELECT payload FROM feedback').fetchone()[0]);self.assertEqual(p['mode'],'mock');self.assertEqual(p['status'],'observation_submitted');self.assertEqual(p['sha256'],self.s.tasks[a['task_id']]['sha256']);self.assertTrue(p['prior_exposure'])
 def test_external_fail_closed_config(self):
  with self.assertRaises(ValueError):mod.Store(pathlib.Path(self.tmp.name)/'other',MANIFEST,mode='external')
 def test_restart_closes_mock_previous_sessions(self):
  a=self.ready(self.a);self.s.db.close();self.s=mod.Store(pathlib.Path(self.tmp.name)/'db',MANIFEST);self.s.tick();self.assertEqual(self.s.current(self.a)['status'],'closed')

class HTTPTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=mod.Store(pathlib.Path(self.tmp.name)/'db',MANIFEST)
  self.http=mod.make_server(self.s,port=0);self.url=f'http://127.0.0.1:{self.http.server_port}';self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
 def tearDown(self):self.http.shutdown();self.http.server_close();self.s.db.close();self.tmp.cleanup()
 def req(self,path,data=None,cookie=None,origin=None):
  headers={};body=None
  if data is not None:body=json.dumps(data).encode();headers['Content-Type']='application/json';headers['Origin']=self.url
  if cookie:headers['Cookie']=cookie
  if origin:headers['Origin']=origin
  req=urllib.request.Request(self.url+path,data=body,headers=headers)
  try:return urllib.request.urlopen(req)
  except urllib.error.HTTPError as e:return e
 def test_login_cookie_and_api(self):
  r=self.req('/api/login',{'token':'local-demo','reviewer':'Tester'});self.assertEqual(r.status,200);cookie=r.headers['Set-Cookie'];self.assertIn('HttpOnly',cookie)
  self.assertEqual(self.req('/api/tasks').status,401);r=self.req('/api/tasks',cookie=cookie);d=json.load(r);self.assertEqual(len(d['tasks']),18);self.assertEqual(d['mode'],'mock');self.assertEqual(set(d['tasks'][0]),{'id','revision','sha256','environment','case_id','rubrics','case_path','case_type'})
  self.assertEqual(self.req('/api/sessions',{},cookie=cookie,origin='https://evil.example').status,403)
  self.assertEqual(self.req('/api/admin/export',cookie=cookie).status,403)
 def test_admin_export_roundtrip(self):
  import subprocess,os,base64
  self.s.admin_token='export-secret'
  cookie,_=self.s.login('local-demo','Tester');u=self.s.auth(cookie);r=self.s.create(u);self.s.tick();self.s.tick()
  eid=self.s.evidence(r['id'],u,{'content_base64':base64.b64encode(b'\x89PNG\r\n\x1a\nfixture').decode(),'mime_type':'image/png'})
  self.s.feedback(r['id'],u,{'verdict':'uncertain','description':'sample','confidence':2,'evidence_ids':[eid]})
  out=pathlib.Path(self.tmp.name)/'export';env=os.environ.copy();env['REVIEW_ADMIN_TOKEN']='export-secret'
  proc=subprocess.run(['python3',str(ROOT/'manage.py'),'export','--url',self.url,'--out',str(out)],env=env,capture_output=True,text=True)
  self.assertEqual(proc.returncode,0,proc.stderr);data=json.loads((out/'observations.json').read_text());self.assertEqual(len(data['feedback']),1);self.assertEqual(data['feedback'][0]['mode'],'mock');self.assertEqual((out/'evidence'/eid).read_bytes(),b'\x89PNG\r\n\x1a\nfixture');self.assertIn('uncertain',(out/'summary.csv').read_text())
 def test_static_path_allowlist(self):
  self.assertEqual(self.req('/').status,200);self.assertEqual(self.req('/tasks.json').status,401);self.assertEqual(self.req('/../../server.py').status,401)

class CaseReviewTests(unittest.TestCase):
 setUp=ServiceTests.setUp
 tearDown=ServiceTests.tearDown
 ready=ServiceTests.ready
 def test_personal_rating_snapshot_and_no_approval(self):
  a=self.ready(self.a);original=dict(self.s.tasks[a['task_id']]);self.s.tasks[a['task_id']]['rubrics']='later changed'
  fid=self.s.feedback(a['id'],self.a,{'difficulty':2,'quality':'pass','comment':'.','reviewer_id':'bob','rubrics':'spoof'})
  p=json.loads(self.s.db.execute('SELECT payload FROM feedback WHERE id=?',(fid,)).fetchone()[0])
  self.assertEqual((p['difficulty'],p['quality'],p['comment']),(2,'pass','.'));self.assertEqual(p['reviewer_id'],'alice');self.assertEqual(p['rubrics'],original['rubrics']);self.assertEqual(p['case_id'],original['case_id']);self.assertEqual(p['status'],'observation_submitted');self.assertNotIn('verdict',p)
 def test_optional_comment_and_independent_people(self):
  a=self.ready(self.a);self.s.feedback(a['id'],self.a,{'difficulty':2,'quality':'pass','comment':''});self.s.change(a['id'],self.a,'close');self.s.tick()
  self.s.create(self.b,a['task_id']);self.s.tick();self.s.tick();b=self.s.current(self.b);self.s.feedback(b['id'],self.b,{'difficulty':4,'quality':'fail','comment':'unclear'})
  rows=[json.loads(r[0]) for r in self.s.db.execute('SELECT payload FROM feedback')];self.assertEqual({r['reviewer_id'] for r in rows},{'alice','bob'});self.assertEqual({r['quality'] for r in rows},{'pass','fail'})
 def test_invalid_rating_rejected(self):
  a=self.ready(self.a)
  for d,q in [(0,'pass'),(6,'pass'),(True,'pass'),(2,'accepted'),('2','pass')]:
   with self.assertRaises(mod.Problem):self.s.feedback(a['id'],self.a,{'difficulty':d,'quality':q,'comment':''})
  self.assertEqual(self.s.db.execute('SELECT count(*) FROM feedback').fetchone()[0],0)

if __name__=='__main__':unittest.main()

class RecoveryTests(unittest.TestCase):
 setUp=ServiceTests.setUp
 tearDown=ServiceTests.tearDown
 ready=ServiceTests.ready
 def test_restart_closed_case_and_owner_isolation(self):
  a=self.ready(self.a)
  with self.assertRaises(mod.Problem):self.s.change(a['id'],self.b,'restart')
  self.s.change(a['id'],self.a,'close');self.s.tick()
  b=self.s.change(a['id'],self.a,'restart')
  self.assertNotEqual(a['id'],b['id']);self.assertEqual(a['task_id'],b['task_id']);self.assertEqual(b['status'],'queued')
 def test_health_separates_process_from_stream_and_releases_after_stop(self):
  a=self.ready(self.a)
  self.s.call_runner=lambda op,s:({'ready':True,'game_running':True,'signalling_running':True,'streamer_registered':True} if op=='status' else {'stopped':True})
  self.s.tick();h=self.s.current(self.a)['health'];self.assertTrue(h['game_running']);self.assertGreater(h['checked_at'],0)
  self.s.change(a['id'],self.a,'restart');self.assertEqual(self.s.current(self.a)['status'],'resetting')
  self.s.change(a['id'],self.a,'close');self.s.tick();self.assertFalse(self.s.current(self.a)['health']['game_running'])
 def test_no_restart_of_saved_feedback(self):
  a=self.ready(self.a);self.s.feedback(a['id'],self.a,{'difficulty':2,'quality':'pass','comment':'test'})
  with self.assertRaises(mod.Problem):self.s.change(a['id'],self.a,'restart')

class StreamLifetimeTests(unittest.TestCase):
 setUp=ServiceTests.setUp
 tearDown=ServiceTests.tearDown
 ready=ServiceTests.ready
 def test_last_browser_disconnect_reclaims_game(self):
  s=self.ready(self.a);self.s.stream_connected(s['id']);self.s.stream_disconnected(s['id']);self.s.disconnect_deadlines[s['id']]=0
  self.s.tick();r=self.s.current(self.a);self.assertEqual(r['status'],'closed');self.assertEqual(r['error'],'Browser disconnected')
 def test_refresh_reconnect_cancels_shutdown(self):
  s=self.ready(self.a);self.s.stream_connected(s['id']);self.s.stream_disconnected(s['id']);self.s.stream_connected(s['id']);self.s.tick();self.assertEqual(self.s.current(self.a)['status'],'ready');self.assertNotIn(s['id'],self.s.disconnect_deadlines)
 def test_other_browser_connection_keeps_session(self):
  s=self.ready(self.a);self.s.stream_connected(s['id']);self.s.stream_connected(s['id']);self.s.stream_disconnected(s['id']);self.s.tick();self.assertNotIn(s['id'],self.s.disconnect_deadlines);self.assertEqual(self.s.current(self.a)['status'],'ready')

 def test_requested_reset_does_not_schedule_disconnect_shutdown(self):
  s=self.ready(self.a);self.s.stream_connected(s['id']);self.s.change(s['id'],self.a,'reset');self.s.stream_disconnected(s['id']);self.assertNotIn(s['id'],self.s.disconnect_deadlines)

class LocalUsabilityTests(HTTPTests):
 def test_local_login_requires_opt_in_and_preserves_owner(self):
  self.assertEqual(self.req('/api/local-login',{}).status,404)
  self.s.tokens={'fixture-secret':{'id':'local-person','reviewer':'Local person'}};self.http.local_autologin_owner='local-person'
  r=self.req('/api/local-login',{});self.assertEqual(r.status,200);cookie=r.headers['Set-Cookie'];self.assertEqual(json.load(r)['reviewer'],'Local person')
  self.assertEqual(self.s.auth(cookie.split('=',1)[1].split(';')[0])['owner'],'local-person')
  self.assertEqual(self.req('/api/local-login',{},origin='https://elsewhere.example').status,403)
 def test_closed_previously_ready_case_can_be_rated(self):
  cookie,_=self.s.login('local-demo','Tester');u=self.s.auth(cookie);a=self.s.create(u);self.s.tick();self.s.tick();self.s.change(a['id'],u,'close');self.s.tick()
  fid=self.s.feedback(a['id'],u,{'difficulty':2,'quality':'pass','comment':'After playing'});self.assertTrue(fid)
