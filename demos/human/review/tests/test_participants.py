import hashlib,importlib.util,json,pathlib,sys,tempfile,threading,unittest,urllib.request,urllib.error
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from participants import Participants
from server import Store,make_server
class ParticipantTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name)
  manifest=json.loads((ROOT/'tests/legacy-manifest.json').read_text())
  self.s=Store(self.root/'db',manifest,capacity=1)
 def tearDown(self):self.s.db.close();self.tmp.cleanup()
 def test_team_code_protects_names_and_login(self):
  p=Participants(self.s,dict(mode='group',access_code='test-secret',reviewers=[{'id':'alice','name':'Alice'},{'id':'bob','name':'Bob'}]))
  for operation in [lambda:p.options('wrong'),lambda:p.login('wrong','Alice')]:
   with self.assertRaises(PermissionError):operation()
  with self.assertRaises(ValueError):p.login('test-secret','Unknown')
  cookie,user=p.login('test-secret',' alice ');self.assertEqual(self.s.auth(cookie)['owner'],'participant:alice');self.assertEqual(user['reviewer'],'Alice')
 def test_names_keep_stable_identity_across_logins_and_restart(self):
  p=Participants(self.s,dict(mode='name'));_,a=p.login('','Alice');_,again=p.login('',' ALICE ');_,b=p.login('','Bob')
  self.assertEqual(a['owner'],again['owner']);self.assertNotEqual(a['owner'],b['owner'])
  p=Participants(self.s,dict(mode='name'));_,again=p.login('','Alice');self.assertEqual(a['owner'],again['owner']);self.assertEqual(len(p.options('')),2)
 def test_feedback_uses_selected_identity_and_session_ownership(self):
  p=Participants(self.s,dict(mode='name'));ca,a=p.login('','Alice');cb,b=p.login('','Bob');a=self.s.auth(ca);b=self.s.auth(cb)
  session=self.s.create(a);self.s.tick();self.s.tick()
  from server import Problem
  with self.assertRaises(Problem):self.s.owned(session['id'],b)
  self.s.feedback(session['id'],a,dict(difficulty=3,quality='pass',comment='test',reviewer='Bob'))
  payload=json.loads(self.s.db.execute('select payload from feedback').fetchone()[0]);self.assertEqual(payload['reviewer'],'Alice');self.assertEqual(payload['reviewer_id'],a['owner'])
 def test_rejects_invalid_config_and_names(self):
  for config in [dict(mode='group'),dict(mode='unknown'),dict(mode='name',reviewers=[dict(id='x',name='A'),dict(id='x',name='B')])]:
   with self.assertRaises(ValueError):Participants(self.s,config)
  p=Participants(self.s,dict(mode='name'))
  for name in ['', 'a'*81,{},'zero\x00byte']:
   with self.assertRaises(ValueError):p.login('',name)
 def test_https_cookie_and_csrf(self):
  http=make_server(self.s,port=0,origin='https://review.example.test');http.participants=Participants(self.s,dict(mode='group',access_code='test-secret'));threading.Thread(target=http.serve_forever,daemon=True).start();url='http://127.0.0.1:'+str(http.server_port)
  try:
   request=urllib.request.Request(url+'/api/participant-login',data=json.dumps(dict(access_code='test-secret',reviewer='Alice')).encode(),headers={'Origin':'https://review.example.test','Content-Type':'application/json'})
   with urllib.request.urlopen(request) as response:self.assertIn('; Secure',response.headers['Set-Cookie']);self.assertIn('HttpOnly',response.headers['Set-Cookie']);self.assertEqual(json.load(response)['reviewer'],'Alice')
   request.headers['Origin']='https://wrong.example'
   with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
   self.assertEqual(error.exception.code,403)
  finally:http.shutdown();http.server_close()
