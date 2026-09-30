import copy,hashlib,json,pathlib,tempfile,unittest
from unittest.mock import patch
from test_linux_runtime import module,runtime,server,ROOT
manage=module('unified_manage',ROOT/'manage.py')
def task(id,map,hash):
 return dict(id=id,map=map,revision=31,sha256='a'*64,build_sha256=hash,rubrics='中文\nEnglish',rubrics_i18n={lang:dict(expected='Expected '+lang,steps='Steps '+lang,criteria='Criteria '+lang) for lang in ('zh','en')})
class UnifiedTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name)
  self.items=[task('S19','/Game/Auditor/Subway/Platform?Task=S19','b'*64),task('H06','/Game/Auditor/Regions/KitchenDining?Task=H06','c'*64)]
 def tearDown(self):self.tmp.cleanup()
 def test_shared_queue_preserves_task_hash_and_bilingual_snapshot(self):
  s=server.Store(self.root/'db',{'tasks':self.items},capacity=1,build_sha='d'*64)
  a=s.auth(s.login('local-demo','A')[0]);b=s.auth(s.login('local-demo','B')[0])
  one=s.create(a,'S19');s.tick();s.tick();two=s.create(b,'H06');s.tick()
  self.assertEqual(s.current(b)['status'],'queued');s.change(one['id'],a,'close');s.tick();s.tick();self.assertEqual(s.current(b)['status'],'ready')
  s.tasks['H06']['rubrics_i18n']['en']['criteria']='later changed'
  s.feedback(two['id'],b,dict(difficulty=2,quality='pass',comment='',rubrics_i18n={'en':'spoof'}))
  p=json.loads(s.db.execute('select payload from feedback').fetchone()[0]);self.assertEqual(p['build_sha256'],'c'*64);self.assertEqual(p['rubrics_i18n']['en']['criteria'],'Criteria en');s.db.close()
 def test_rejects_deleted_tasks_cross_task_urls_and_incomplete_translation(self):
  for n,(id,map) in enumerate([('H14','/Game/Auditor/Regions/BedroomSuite?Task=H14'),('S22','/Game/Auditor/Subway/Platform?Task=S22'),('H06','/Game/Auditor/Regions/KitchenDining?Task=H07'),('S19','/Game/Auditor/Subway/Platform?Task=S19 -ExecCmds=quit'),('H06','/Game/Auditor/Subway/Platform?Task=H06')]):
   with self.assertRaises(ValueError):server.Store(self.root/str(n),{'tasks':[task(id,map,'b'*64)]})
  broken=copy.deepcopy(self.items[0]);del broken['rubrics_i18n']['en']['criteria']
  with self.assertRaises(ValueError):server.Store(self.root/'broken',{'tasks':[broken]})
 def test_export_groups_each_current_case_with_its_actual_build(self):
  data=dict(mode='external',build_sha256='d'*64,tasks=self.items,feedback=[])
  index=manage.write_matrices(data,self.root);self.assertEqual(len(index),2)
  for entry in index:self.assertEqual(len(entry['rows']),1);self.assertEqual(entry['rows'][0]['case_snapshot']['case_id'].split('-')[0],'S19' if entry['build_sha256']=='b'*64 else 'H06')
 def test_profiles_launch_matching_binary_and_reject_drift(self):
  manifest=self.root/'tasks.json';manifest.write_text(json.dumps({'tasks':self.items}));profiles={}
  for t in self.items:
   binary=self.root/t['id'];binary.write_bytes(t['id'].encode());profiles[t['map']]=dict(binary=str(binary),build_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),key_filter='F1,F2')
  for t in self.items:t['build_sha256']=profiles[t['map']]['build_sha256']
  manifest.write_text(json.dumps({'tasks':self.items}))
  profiles[self.items[1]['map']]['game_args']=['-vulkan','-sm5']
  c=dict(game_args=['-vulkan','-sm6'],manifest=str(manifest),state_dir=str(self.root),launch_profiles=profiles,streamer_port=18882,player_port=18082,sfu_port=18892,http_root=str(self.root),signal_argv=['node'],signal_cwd=str(self.root))
  for i,t in enumerate(self.items):
   sup=runtime.Supervisor(c)
   with patch.object(sup,'spawn') as spawn:
    sup.run(dict(operation='start',session_id=str(i)*32,map=t['map'],slot=0));self.assertEqual(spawn.call_args_list[1].args[1][0],profiles[t['map']]['binary'])
    args=spawn.call_args_list[1].args[1];self.assertEqual('-sm5' in args,t['id']=='H06');self.assertEqual('-sm6' in args,t['id']=='S19')
   sup.close()
  (self.root/'H06').write_bytes(b'changed')
  sup=runtime.Supervisor(c)
  with patch.object(sup,'spawn'):
   with self.assertRaises(RuntimeError):sup.run(dict(operation='start',session_id='f'*32,map=self.items[1]['map'],slot=0))
  self.assertFalse(sup.sessions)
 def test_http_bilingual_catalog_and_export_preserve_fields(self):
  import threading,urllib.request
  s=server.Store(self.root/'http.db',{'tasks':self.items},admin_token='qa-admin')
  http=server.make_server(s,port=0);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();url='http://127.0.0.1:'+str(http.server_port)
  try:
   cookie,_=s.login('local-demo','QA')
   for route,headers in [('/api/tasks',{'Cookie':'review_session='+cookie}),('/api/admin/export',{'Authorization':'Bearer qa-admin'})]:
    if route=='/api/tasks':
     # Use the service's own HTTP login response to avoid assuming the cookie name.
     req=urllib.request.Request(url+'/api/login',data=json.dumps({'token':'local-demo','reviewer':'QA'}).encode(),headers={'Origin':url,'Content-Type':'application/json'})
     with urllib.request.urlopen(req) as response:headers={'Cookie':response.headers['Set-Cookie']}
    with urllib.request.urlopen(urllib.request.Request(url+route,headers=headers)) as response:data=json.load(response)
    for task in data['tasks']:
     self.assertIn('rubrics_i18n',task);self.assertEqual(task['build_sha256'],'b'*64 if task['id']=='S19' else 'c'*64)
  finally:http.shutdown();http.server_close();s.db.close()
