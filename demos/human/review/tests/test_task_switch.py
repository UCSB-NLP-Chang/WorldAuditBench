import json,pathlib,tempfile,unittest
from unittest.mock import patch
from test_service import mod

class TaskSwitchTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.tasks=[dict(id='S01',map='/Game/Auditor/Subway/Concourse?Task=S01',family='subway',revision=1,sha256='a'*64,build_sha256='b'*64,runtime_switch=True),dict(id='B01',map='/Game/Auditor/Subway/Concourse',family='subway',revision=1,sha256='a'*64,build_sha256='b'*64,runtime_switch=True,case_type='baseline'),dict(id='H01',map='/Game/Auditor/Regions/LivingRoom?Task=H01',family='indoor',revision=1,sha256='c'*64,build_sha256='d'*64,runtime_switch=True)]
  self.s=mod.Store(pathlib.Path(self.tmp.name)/'db',{'tasks':self.tasks},capacity=1,tokens={k:dict(id=k,reviewer=k) for k in ('A','B')});self.a,self.b=[self.s.auth(self.s.login(k,'')[0]) for k in ('A','B')]
 def tearDown(self):self.s.db.close();self.tmp.cleanup()
 def ready(self):
  ss=self.s.create(self.a,'S01');self.s.tick();self.s.tick();return self.s.current(self.a)
 def test_reuses_slot_runtime_and_keeps_task_feedback_separate(self):
  old=self.ready();self.s.feedback(old['id'],self.a,dict(difficulty=2,quality='pass',comment='S01 only'));wait=self.s.create(self.b,'S01')
  new=self.s.switch_task(old['id'],self.a,'B01');self.assertEqual(new['status'],'switching');self.assertNotEqual(old['id'],new['id']);row=self.s.owned(new['id'],self.a);self.assertEqual(row['runtime_id'],old['id']);self.assertEqual(row['slot'],0)
  self.assertEqual(self.s.owned(old['id'],self.a)['status'],'closed');self.assertIsNone(self.s.owned(old['id'],self.a)['slot'])
  with patch.object(self.s,'call_runner',wraps=self.s.call_runner) as call:self.s.tick();self.assertEqual([c.args[0] for c in call.call_args_list],['switch'])
  self.assertEqual(self.s.current(self.a)['status'],'ready');self.assertEqual(self.s.current(self.b)['status'],'queued')
  self.s.feedback(new['id'],self.a,dict(difficulty=3,quality='fail',comment='B01 only'));payloads=[json.loads(r[0]) for r in self.s.db.execute('select payload from feedback order by created')];self.assertEqual([(p['task_id'],p['comment']) for p in payloads],[('S01','S01 only'),('B01','B01 only')])
  self.assertEqual(self.s.stream_session(old['id'],self.a)['id'],new['id'])
  with self.assertRaises(mod.Problem):self.s.stream_session(old['id'],self.b)
  self.s.change(new['id'],self.a,'close');self.s.tick();self.s.tick();self.assertEqual(self.s.current(self.b)['status'],'ready')
 def test_owner_readiness_and_cross_environment_checks_do_not_change_slot(self):
  old=self.ready()
  for user,target in [(self.b,'B01'),(self.a,'H01'),(self.a,'invalid')]:
   with self.assertRaises(mod.Problem):self.s.switch_task(old['id'],user,target)
  self.assertEqual(self.s.owned(old['id'],self.a)['status'],'ready')
  self.s.tasks['B01']['build_sha256']='e'*64
  with self.assertRaises(mod.Problem):self.s.switch_task(old['id'],self.a,'B01')
  self.s.tasks['B01']['build_sha256']='b'*64;new=self.s.switch_task(old['id'],self.a,'B01')
  with self.assertRaises(mod.Problem):self.s.switch_task(new['id'],self.a,'S01')
  with self.assertRaises(mod.Problem):self.s.switch_task(old['id'],self.a,'B01')
 def test_switch_failure_quarantines_slot_until_stop_confirmed(self):
  old=self.ready();self.s.create(self.b,'S01');new=self.s.switch_task(old['id'],self.a,'B01')
  with patch.object(self.s,'call_runner',side_effect=RuntimeError('adapter failure')):self.s.tick()
  self.assertEqual(self.s.current(self.a)['status'],'closing');self.assertEqual(self.s.owned(new['id'],self.a)['slot'],0)
  with patch.object(self.s,'call_runner',return_value={'stopped':False}):self.s.tick()
  self.assertEqual(self.s.current(self.b)['status'],'queued')
  self.s.tick();self.s.tick();self.assertEqual(self.s.current(self.b)['status'],'ready')
 def test_disconnect_tracks_current_logical_task_and_reconnect_clears_it(self):
  old=self.ready();new=self.s.switch_task(old['id'],self.a,'B01');self.s.stream_disconnected(old['id']);self.assertFalse(self.s.disconnect_deadlines)
  self.s.tick();self.s.stream_connected(old['id']);self.s.stream_disconnected(old['id']);self.assertIn(new['id'],self.s.disconnect_deadlines);self.s.stream_connected(old['id']);self.assertFalse(self.s.disconnect_deadlines)
 def test_switch_timeout_does_not_release_slot_early(self):
  old=self.ready();new=self.s.switch_task(old['id'],self.a,'B01');self.s.db.execute("update events set created=created-130 where session_id=?",(new['id'],));self.s.db.commit()
  with patch.object(self.s,'call_runner',return_value=dict(ready=False,game_running=True,signalling_running=True)):self.s.tick()
  self.assertEqual(self.s.current(self.a)['status'],'closing');self.assertEqual(self.s.owned(new['id'],self.a)['slot'],0)

class SupervisorSwitchTests(unittest.TestCase):
 def test_command_deduplication_ready_ack_and_no_process_respawn(self):
  import hashlib
  from types import SimpleNamespace
  from test_linux_runtime import runtime
  with tempfile.TemporaryDirectory() as temp:
   root=pathlib.Path(temp);binary=root/'game';binary.write_bytes(b'fixture');sha=hashlib.sha256(b'fixture').hexdigest();maps=['/Game/Auditor/Subway/Concourse','/Game/Auditor/Subway/Concourse?Task=S01'];manifest=root/'manifest.json';manifest.write_text(json.dumps({'tasks':[dict(map=m,build_sha256=sha) for m in maps]}))
   c=dict(capacity=1,manifest=str(manifest),state_dir=str(root/'state'),streamer_port=18882,player_port=18082,sfu_port=18892,http_root=str(root),signal_argv=['node'],signal_cwd=str(root),binary=str(binary),probe_argv=['probe'],launch_profiles={m:dict(binary=str(binary),build_sha256=sha,family='subway',runtime_switch=True) for m in maps})
   sup=runtime.Supervisor(c);calls=[]
   def spawn(s,argv,*args):calls.append(argv);s['processes'].append(SimpleNamespace(pid=101+len(calls),poll=lambda:None))
   sid='a'*32;request=dict(session_id=sid,map=maps[0],slot=0)
   with patch.object(sup,'spawn',side_effect=spawn),patch.object(runtime.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='{"ready":true}')):
    sup.run(request|dict(operation='start'));ipc=root/'state'/sid/'review-ipc';ipc.mkdir()
    (ipc/'response.json').write_text(json.dumps(dict(request_id='',status='ready',map=maps[0],task='baseline',pid=103)))
    self.assertTrue(sup.run(request|dict(operation='status'))['ready'])
    request['map']=maps[1];self.assertFalse(sup.run(request|dict(operation='switch'))['ready']);command=json.loads((ipc/'command.json').read_text());self.assertEqual(command['task'],'S01')
    sup.run(request|dict(operation='switch'));self.assertEqual(json.loads((ipc/'command.json').read_text()),command);self.assertEqual(len(calls),2)
    ack=dict(request_id=command['request_id'],status='ready',map=maps[0],task='S01',pid=999)
    (ipc/'response.json').write_text(json.dumps(ack));self.assertFalse(sup.run(request|dict(operation='status'))['ready'])
    ack['pid']=103;(ipc/'response.json').write_text(json.dumps(ack));self.assertTrue(sup.run(request|dict(operation='status'))['ready']);self.assertEqual(len(calls),2)
    with self.assertRaises(ValueError):sup.run(request|dict(operation='switch',slot=1))
