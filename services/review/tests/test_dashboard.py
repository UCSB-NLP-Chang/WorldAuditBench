import json,pathlib,tempfile,unittest
from unittest.mock import patch
from test_linux_runtime import runtime,server
from participants import Participants
class DashboardTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name)
  self.tasks=[dict(id='S01',map='/Game/Auditor/Subway/Concourse?Task=S01',family='subway',revision=1,sha256='a'*64,build_sha256='b'*64),dict(id='B01',map='/Game/Auditor/Subway/Concourse',family='subway',revision=1,sha256='a'*64,build_sha256='b'*64,case_type='baseline')]
  self.s=server.Store(self.root/'db',{'tasks':self.tasks},capacity=3)
  self.p=Participants(self.s,{'mode':'name'})
  self.users=[self.s.auth(self.p.login('',name)[0]) for name in ['A','B','C','D']]
 def tearDown(self):self.s.db.close();self.tmp.cleanup()
 def vote(self,user,quality,task='S01'):
  session=self.s.create(user,task);self.s.tick();self.s.tick();self.s.feedback(session['id'],user,dict(difficulty=2,quality=quality,comment=''));self.s.change(session['id'],user,'close');self.s.tick()
 def test_latest_distinct_current_version_votes(self):
  a,b=self.users[:2];self.vote(a,'pass');self.vote(a,'pass');self.assertEqual(self.s.dashboard(a)['counts']['accepted'],0)
  self.vote(b,'pass');self.assertEqual(self.s.dashboard(a)['counts']['accepted'],1)
  self.vote(a,'fail');self.assertEqual(self.s.dashboard(a)['counts']['accepted'],0)
  self.vote(a,'pass');self.assertEqual(self.s.dashboard(a)['counts']['accepted'],1)
  self.s.tasks['S01']['build_sha256']='c'*64;self.assertEqual(self.s.dashboard(a)['counts']['accepted'],0)
 def test_scenes_deduplicate_variants_and_baseline_is_separate(self):
  a,b=self.users[:2]
  for user in (a,b):self.vote(user,'pass','B01')
  d=self.s.dashboard(a);self.assertEqual(d['counts'],dict(environments=1,scenes=1,tasks=1,baselines=1,accepted=0));self.assertTrue(d['tasks'][1]['accepted'])
 def test_three_slots_fourth_waits_and_freed_slot_is_reused(self):
  for user in self.users:self.s.create(user,'S01')
  self.s.tick();self.s.tick();d=self.s.dashboard(self.users[3]);self.assertEqual([r['slot'] for r in d['running']],[1,2,3]);self.assertEqual(len(d['queue']),1);self.assertTrue(d['queue'][0]['mine']);self.assertNotIn('owner',str(d))
  self.s.change(self.s.current(self.users[1])['id'],self.users[1],'close');self.s.tick();self.s.tick();d=self.s.dashboard(self.users[3]);self.assertEqual(len(d['running']),3);self.assertEqual(len(d['queue']),0);self.assertEqual(next(r for r in d['running'] if r['mine'])['slot'],2)
 def test_roster_preserves_existing_identity_and_rejects_new_names(self):
  owner=self.users[0]['owner'];p=Participants(self.s,dict(mode='group',access_code='test',allow_new_names=False,reviewers=[dict(id=owner.removeprefix('participant:'),name='A')]))
  self.assertEqual(p.login('test','A')[1]['owner'],owner)
  with self.assertRaises(ValueError):p.login('test','Unexpected')
 def test_multi_slot_ports_and_session_isolation(self):
  manifest=self.root/'manifest.json';manifest.write_text(json.dumps({'tasks':[{'map':'/Game/Test'}]}))
  c=dict(capacity=3,manifest=str(manifest),state_dir=str(self.root),streamer_port=18882,player_port=18082,sfu_port=18892,http_root=str(self.root),signal_argv=['node'],signal_cwd=str(self.root),binary='/tmp/game')
  sup=runtime.Supervisor(c)
  with patch.object(sup,'spawn') as spawn:
   for i in range(3):
    sid=str(i)*32;sup.run(dict(operation='start',session_id=sid,map='/Game/Test',slot=i))
    config=json.loads((self.root/sid/'signal-config.json').read_text());self.assertEqual(config['player_port'],18082+i);self.assertIn('-PixelStreamingConnectionURL=ws://127.0.0.1:'+str(18882+i),spawn.call_args_list[-1].args[1])
   with self.assertRaises(RuntimeError):sup.run(dict(operation='start',session_id='f'*32,map='/Game/Test',slot=1))
   with self.assertRaises(ValueError):sup.run(dict(operation='stop',session_id='1'*32,map='/Game/Test',slot=0))
   for slot in (-1,3,True):
    with self.assertRaises(ValueError):sup.run(dict(operation='start',session_id='f'*32,map='/Game/Test',slot=slot))
   sup.run(dict(operation='stop',session_id='1'*32,map='/Game/Test',slot=1));self.assertEqual(len(sup.sessions),2)
  sup.close()
