import json,pathlib,tempfile,unittest,threading,urllib.request
from server import Store,make_server
from taxonomy import TAXONOMY,classify
ROOT=pathlib.Path(__file__).resolve().parents[1]
class TaxonomyTests(unittest.TestCase):
 def test_five_categories_sixteen_types_and_aliases(self):
  self.assertEqual(len(TAXONOMY['categories']),5)
  codes=[]
  for category in TAXONOMY['categories']:
   self.assertEqual(len(category['subcategories']),4 if category['id']=='visual' else 3)
   for sub in category['subcategories']:
    codes.append(sub['code']);self.assertEqual(classify({'subcategory':sub['code']}),classify({'subcategory':sub['id']}))
    self.assertTrue(all(sub['name'].get(lang) and category['name'].get(lang) for lang in ('zh','en')))
  self.assertEqual(len(set(codes)),16);self.assertIsNone(classify({'case_type':'baseline','subcategory':'G1'}))
 def test_live_catalog_classification_and_documented_static_material_exception(self):
  with tempfile.TemporaryDirectory() as tmp:
   s=Store(pathlib.Path(tmp)/'db',json.loads((ROOT/'tasks.json').read_text()));self.addCleanup(s.db.close)
   user=s.auth(s.login('local-demo','QA')[0]);d=s.dashboard(user)
   unmapped={'JS_WT16','JS_WT17'}
   self.assertEqual(d['taxonomy']['unclassified'],len(unmapped))
   self.assertEqual({t['id'] for t in d['tasks'] if t['case_type']!='baseline' and not t['taxonomy']},unmapped)
   self.assertEqual(s.tasks['U045']['taxonomy']['code'],'V4')
   subs=[sub for c in d['taxonomy']['categories'] for sub in c['subcategories']]
   self.assertEqual(sum(sub['tasks'] for sub in subs),225);self.assertEqual(sum(c['tasks'] for c in d['taxonomy']['categories']),225)
   self.assertEqual([sub['tasks'] for sub in subs[-3:]],[1, 11, 10])
   self.assertEqual(s.tasks['I19']['taxonomy']['subcategory']['en'],'Improper configuration')
   self.assertEqual(s.tasks['S18']['taxonomy']['subcategory']['en'],'Improper configuration')
   self.assertEqual(s.tasks['H13']['taxonomy']['subcategory']['en'],'Improper configuration')
   self.assertEqual(s.tasks['S19']['taxonomy']['subcategory']['en'],'Improper configuration')
   for task in ('S05','H06'):
    self.assertEqual(s.tasks[task]['taxonomy']['subcategory']['zh'],'交互后物体运动轨迹异常')
    self.assertEqual(s.tasks[task]['taxonomy']['subcategory']['en'],'Abnormal object trajectories after interaction')
   for t in d['tasks']:self.assertEqual(bool(t['taxonomy']),t['case_type']!='baseline' and t['id'] not in unmapped)
   self.assertEqual(s.tasks['S01']['taxonomy'],s.tasks['H01']['taxonomy'])
 def test_classification_snapshot_and_category_accepted_counts(self):
  with tempfile.TemporaryDirectory() as tmp:
   items=json.loads((ROOT/'tasks.json').read_text())
   s=Store(pathlib.Path(tmp)/'db',items);self.addCleanup(s.db.close)
   for name in ('One','Two'):
    user=s.auth(s.login('local-demo',name)[0]);session=s.create(user,'H01');s.tick();s.tick();s.feedback(session['id'],user,dict(difficulty=1,quality='pass',comment=''))
    s.change(session['id'],user,'close');s.tick()
   payload=json.loads(s.db.execute('select payload from feedback limit 1').fetchone()[0]);self.assertEqual(payload['taxonomy']['code'],'G1')
   d=s.dashboard(user);self.assertEqual(d['taxonomy']['categories'][0]['accepted'],1);self.assertEqual(d['taxonomy']['categories'][0]['subcategories'][0]['accepted'],1)
   s.tasks['H01']['build_sha256']='f'*64;self.assertEqual(s.dashboard(user)['taxonomy']['categories'][0]['accepted'],0)
 def test_authenticated_http_payloads_include_taxonomy(self):
  with tempfile.TemporaryDirectory() as tmp:
   s=Store(pathlib.Path(tmp)/'db',json.loads((ROOT/'tasks.json').read_text()));http=make_server(s,port=0);threading.Thread(target=http.serve_forever,daemon=True).start()
   cookie,_=s.login('local-demo','QA');origin='http://127.0.0.1:'+str(http.server_port)
   try:
    for route in ('/api/tasks','/api/dashboard'):
     with urllib.request.urlopen(urllib.request.Request(origin+route,headers={'Cookie':'review_session='+cookie})) as response:data=json.load(response)
     task=next(t for t in data['tasks'] if t['id']=='H01');self.assertEqual(task['taxonomy']['code'],'G1');self.assertTrue(task['taxonomy']['category']['en'])
   finally:http.shutdown();http.server_close();s.db.close()
