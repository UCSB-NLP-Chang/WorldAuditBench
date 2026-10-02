import copy,json,pathlib,shutil,tempfile,unittest
from ancient_entries import build_ancient_entries
from test_linux_runtime import server
class AncientCatalogTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name)
  actual=pathlib.Path('/home/ubuntu/unreal-auditor/ancient-entry-workspace/ancient-workspace')
  w=self.root/'ancient-workspace'
  shutil.copytree(actual/'environments',w/'environments')
  # This legacy 20-case builder test must not consume unpublished workspace additions.
  catalog=w/'environments/ancient-chinese-city/tasks.json'
  data=json.loads(catalog.read_text());published={t['id'] for t in json.loads((pathlib.Path(__file__).resolve().parents[1]/'tasks.json').read_text())['tasks'] if t.get('family')=='ancient'}
  data['tasks']=[t for t in data['tasks'] if t['id'] in published];catalog.write_text(json.dumps(data))
  for reg in json.loads((w/'environments/ancient-chinese-city/regions.json').read_text())['regions']:
   p=w/'project/Content'/(reg['map'][6:]+'.umap');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(reg['map'].encode())
  p=w/'dist/ancient-era-20260913-v1/Linux/AncientChineseCity/Binaries/Linux/AncientChineseCity';p.parent.mkdir(parents=True);p.write_bytes(b'isolated QA fixture')
  self.entries,self.profiles=build_ancient_entries(self.root)
 def tearDown(self):self.tmp.cleanup()
 def test_catalog_counts_taxonomy_translations_and_profiles(self):
  s=server.Store(self.root/'test.db',{'tasks':self.entries})
  try:
   self.assertEqual(len(s.tasks),28)
   self.assertEqual(sum(t['case_type']=='baseline' for t in s.tasks.values()),3)
   for t in s.tasks.values():
    self.assertEqual(t['family'],'ancient')
    self.assertEqual(self.profiles[t['map']]['build_sha256'],t['build_sha256'])
    self.assertTrue(t['runtime_switch'])
    self.assertEqual('taxonomy' in t,t['case_type']=='bug')
    for lang in ('en','zh'):
     for field in ('criteria','steps','expected'):self.assertTrue(t['rubrics_i18n'][lang][field].strip())
   u=s.auth(s.login('local-demo','QA')[0]);d=s.dashboard(u)
   self.assertEqual(d['counts'],dict(environments=1,scenes=3,tasks=25,baselines=3,accepted=0))
  finally:s.db.close()
 def test_rejects_invalid_id_wrong_world_and_cross_task_url(self):
  good=next(t for t in self.entries if t['id']=='A01')
  for i,change in enumerate([{'id':'A25'},{'map':'/Game/Auditor/Subway/Concourse?Task=A01'},{'map':good['map'].replace('?Task=A01','?Task=A02')},{'map':good['map']+' -ExecCmds=quit'}]):
   with self.assertRaises(ValueError):server.Store(self.root/('invalid'+str(i)),{'tasks':[good|change]})
 def test_same_scene_descriptions_and_explicit_interaction_guidance(self):
  scenes=json.loads((self.root/'ancient-workspace/environments/ancient-chinese-city/scene-descriptions.json').read_text())
  if isinstance(scenes,dict):scenes=scenes['scenes']
  self.assertEqual(len(scenes),3)
  for scene in scenes:
   for lang in ('en','zh'):self.assertTrue(scene['description'][lang])

