import json,pathlib,tempfile,unittest
from server import Store
ROOT=pathlib.Path(__file__).resolve().parents[1]
class MedievalCatalogTests(unittest.TestCase):
 def test_complete_catalog_bilingual_taxonomy_and_baselines(self):
  with tempfile.TemporaryDirectory() as tmp:
   s=Store(pathlib.Path(tmp)/'db',json.loads((ROOT/'tasks.json').read_text()));self.addCleanup(s.db.close)
   ours={k:v for k,v in s.tasks.items() if v.get('family')=='medieval'}
   self.assertEqual(set(ours),{'MVB01','MVB02'}|{f'MV{i:02}' for i in range(1,23)})
   codes=['G1','G2','G3','C1','C2','C3','V1','V2','V3','T1','G1','G2','T2','T3','V1','T2','S2','S3','S3','S3','S3','S3']
   for i,code in enumerate(codes,1):
    t=ours[f'MV{i:02}'];self.assertEqual(t['taxonomy']['code'],code)
    self.assertEqual(t['map'],'/Game/Auditor/MedievalVillage/'+('Market' if i<=10 or i in (19,20,22) else 'Windmill')+'?Task='+t['id'])
    for lang in ('en','zh'):
     self.assertTrue(all(t['rubrics_i18n'][lang][field].strip() for field in ('criteria','expected','steps')))
   for id,name in [('MVB01','Market'),('MVB02','Windmill')]:
    self.assertEqual(ours[id]['case_type'],'baseline');self.assertIsNone(ours[id].get('taxonomy'));self.assertEqual(ours[id]['map'],'/Game/Auditor/MedievalVillage/'+name)
 def test_one_immutable_streaming_build_for_all_variants(self):
  tasks=[t for t in json.loads((ROOT/'tasks.json').read_text())['tasks'] if t.get('family')=='medieval'];cfg=json.loads((ROOT/'candidate-runtime.json' if (ROOT/'candidate-runtime.json').exists() else ROOT.parents[1]/'state/runtime.json').read_text())
  profiles=[cfg['launch_profiles'][t['map']] for t in tasks]
  self.assertEqual(len({p['binary'] for p in profiles}),1);self.assertEqual(len({p['build_sha256'] for p in profiles}),1)
  for p in profiles:self.assertTrue(p['runtime_switch']);self.assertNotIn('E',p['key_filter'].split(','));self.assertIn('-sm6',p['game_args'])
