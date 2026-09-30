import base64
import gzip
import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch
from bf.common import Problem, uid
from bf.exploration import ExplorationStore
from bf.runtime import Runtime


class BrowserRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.tmp.name)
        self.store=ExplorationStore(self.root/'ex');self.tid=uid()
        self.store.register_task({'id':self.tid,'title':'World','query':'Explore','controls':'WASD'})
        self.users=[]
        for name in ['one','two']:
            self.store.add_user(name,'test-password')
            self.store.grant_task(name,self.tid,'explorer')
            self.users.append(self.store.authenticate(self.store.login(name,'test-password')))
        self.runtime=Runtime(self.store,{'tasks':{self.tid:{'kind':'browser','bundle':'world','config_id':self.tid}},'legacy_player_ports':[1]})
    def tearDown(self):self.store.db.close();self.tmp.cleanup()
    def start(self,user):
        a=self.store.start_attempt(user,self.tid)
        return a,self.runtime.start(user,a['id'])
    def test_browser_concurrency_does_not_allocate_gpu(self):
        with patch.object(self.runtime,'call') as call,patch.object(self.runtime,'legacy_busy',return_value=True):
            a,s=self.start(self.users[0]);b,t=self.start(self.users[1])
            self.assertNotEqual(s['id'],t['id']);call.assert_not_called()
            self.runtime.stop(self.users[0],a['id'])
            self.assertEqual(self.runtime.status(self.users[1],b['id'])['status'],'ready')
    def test_assets_require_owner_and_current_assignment(self):
        a,s=self.start(self.users[0])
        with self.assertRaises(Problem):self.runtime.authorize_browser(self.users[1],s['id'])
        self.store.db.execute('DELETE FROM task_access WHERE user_id=?',(self.users[0]['id'],))
        with self.assertRaises(Problem):self.runtime.authorize_browser(self.users[0],s['id'])
    def test_logout_submit_and_expiry_release_browser(self):
        a,s=self.start(self.users[0]);self.runtime.finish_attempt(self.users[0],a['id'])
        with self.assertRaises(Problem):self.runtime.authorize_browser(self.users[0],s['id'])
        a,s=self.start(self.users[0]);self.runtime.stop_user(self.users[0]);self.assertFalse(self.runtime.browsers)
        a,s=self.start(self.users[0]);self.runtime.browsers[s['id']]['created']=0
        self.runtime.tick();self.assertFalse(self.runtime.browsers)
    def test_bundle_excludes_answers_other_cases_and_debug_entry(self):
        spec=importlib.util.spec_from_file_location('import_tasks',pathlib.Path(__file__).resolve().parents[1]/'ops/import_audit_tasks.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        cfg=lambda value:{'b64':base64.b64encode(json.dumps(value).encode()).decode(),'type':'application/json'}
        pack={'entry':'env/entry.js','order':['env/core.js','env/entry.js'],'js':{'env/core.js':base64.b64encode(gzip.compress(b'window.__ctx = ctx; window.__env = {};')).decode(),'env/entry.js':'old'},'vfs':{'env/configs/chosen.json':cfg({'name':'LEAK','meta':{'desc':'ANSWER'},'bugs':[{'type':'mesh_offset'}]}),'env/configs/chosen.answers.json':cfg('SECRET_ANSWER'),'env/configs/other.json':cfg('OTHER_CASE'),'assets/mesh.bin':cfg('ASSET')}}
        source=self.root/'source.html';source.write_text('<style>canvas{display:block}</style><script>window.__PACK='+json.dumps(pack)+';</script><script>\n(async () => { const P = window.__PACK; })();</script><script>window.__BUG_LIST=["SECRET_ANSWER"];</script>')
        module.bundle_page(source,self.root/'bundles/world',[(self.tid,'chosen')])
        clean=json.loads(gzip.decompress((self.root/'bundles/world/assets.json.gz').read_bytes()))
        self.assertEqual(list(clean['vfs']),['assets/mesh.bin'])
        entry=gzip.decompress(base64.b64decode(clean['js']['env/entry.js'])).decode()
        self.assertNotIn('toggleAnswers',entry)
        current=json.loads(base64.b64decode(json.loads((self.root/'bundles/configs'/ (self.tid+'.json')).read_text())['b64']))
        self.assertNotIn('meta',current);self.assertEqual(current['bugs'],[{'type':'mesh_offset'}])
        self.assertNotIn('SECRET_ANSWER',(self.root/'bundles/world/template.html').read_text())

    def test_native_bundle_pins_selector_and_removes_review_overlay(self):
        spec=importlib.util.spec_from_file_location('native_import',pathlib.Path(__file__).resolve().parents[1]/'ops/import_audit_tasks.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        source=self.root/'native.html'
        source.write_text('<html><head><title>Original</title></head><body><script>const q=new URLSearchParams(location.search);const reviewOn = !harnessOn;window.BenchmarkWorld.bug = bugAnswer;</script><script>window.__BUG_LIST=["SECRET_SENTINEL"];</script></body></html>')
        module.native_page(source,self.root/'native/world',[(self.tid,'chosen')])
        html=gzip.decompress((self.root/'native/world/native.html.gz').read_bytes()).decode()
        self.assertNotIn('SECRET_SENTINEL',html)
        self.assertNotIn('location.search',html)
        self.assertNotIn('window.BenchmarkWorld.bug =',html)
        self.assertIn('const reviewOn = false;',html)
        self.assertIn('/static/browser-native.js',html)
        self.assertEqual(json.loads((self.root/'native/configs'/(self.tid+'.json')).read_text()),'?bug=chosen&noui=1&seed=5')
