import unittest
import json
import base64
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import test_workflow as workflow
from bf import allocation
from bf.common import uid,Problem

class AllocationTests(unittest.TestCase):
    setUp=workflow.Workflow.setUp
    tearDown=workflow.Workflow.tearDown

    def configure(self):
        self.ex.guidance={self.task['id']:['geometry']}
        tid=uid();self.ex.register_task({'id':tid,'title':'Second','query':'Explore','controls':'WASD'})
        self.ex.guidance[tid]=['collision']
        for user in (self.user,self.other):self.ex.grant_task(user['name'],tid,'explorer')
        return tid

    def test_parallel_claims_are_distinct_and_retries_idempotent(self):
        self.configure()
        with ThreadPoolExecutor(2) as pool:
            a,b=list(pool.map(lambda u:allocation.claim(self.ex,u),[self.user,self.other]))
        self.assertNotEqual(a['task']['id'],b['task']['id'])
        self.assertEqual(allocation.claim(self.ex,self.user)['id'],a['id'])

    def test_skip_is_not_submission_and_next_excludes_personal_history(self):
        self.configure();a=allocation.claim(self.ex,self.user)
        d=self.ex.save_draft(self.user,a['id'],{'version':a['draft_version'],'draft':{'outcome':'none','reports':[]}})
        self.assertEqual(self.ex.submit(self.user,a['id'],{'version':d['draft_version']})['status'],'skipped')
        self.assertEqual(self.ex.db.execute('SELECT count(*) FROM submissions').fetchone()[0],0)
        b=allocation.claim(self.ex,self.user);self.assertNotEqual(a['task']['id'],b['task']['id'])
        self.assertEqual(self.ex.snapshot(self.user,a['id'])['status'],'skipped')

    def test_lowest_global_exposure_first_and_cohorts_independent(self):
        tid=self.configure()
        self.ex.db.execute("UPDATE attempts SET status='skipped' WHERE id=?",(self.a['id'],))
        a=allocation.claim(self.ex,self.other);self.assertEqual(a['task']['id'],tid)
        self.ex.add_user('qa','password',is_test=True);self.ex.grant_task('qa',tid,'explorer')
        qa=self.ex.authenticate(self.ex.login('qa','password'))
        self.assertEqual(allocation.claim(self.ex,qa)['task']['id'],tid)

    def test_expiry_preserves_drafts_and_allows_reassignment(self):
        self.configure();a=allocation.claim(self.ex,self.user)
        self.ex.db.execute('UPDATE exploration_claims SET expires=0')
        b=allocation.claim(self.ex,self.other,a['task']['id']);self.assertEqual(b['task']['id'],a['task']['id'])
        self.assertEqual(self.ex.snapshot(self.user,a['id'])['status'],'draft')

    def test_controls_excluded_hint_allowlist_and_exhaustion(self):
        tid=self.configure();self.ex.guidance[tid]=[]
        task=self.ex.task(self.task['id']);self.assertEqual(task['ground_truth_categories'][0]['id'],'geometry')
        self.assertEqual(set(task['ground_truth_categories'][0]),{'id','name','description'})
        a=allocation.claim(self.ex,self.user);self.assertEqual(a['task']['id'],self.task['id'])
        self.assertTrue(allocation.claim(self.ex,self.other)['unavailable'])
        with self.assertRaises(Problem):self.ex.start_attempt(self.user,tid)

    def test_new_report_carries_protocol_without_changing_reference_query(self):
        self.configure();a=allocation.claim(self.ex,self.user,self.task['id'])
        self.assertEqual(a['task']['query'],self.task['query'])
        allocation.heartbeat(self.ex,self.user,a['id'])
        self.assertEqual(self.ex.db.execute('SELECT count(*) FROM exploration_claims').fetchone()[0],1)

    def test_guided_report_is_accepted_by_existing_evaluation_contract(self):
        self.configure();a=allocation.claim(self.ex,self.user,self.task['id'])
        fid=uid();self.ex.add_flag(self.user,a['id'],{'id':fid,'runtime_id':self.rid,'captured_at':__import__('time').time(),'content_base64':base64.b64encode(workflow.png()).decode()})
        d=self.ex.save_draft(self.user,a['id'],{'version':a['draft_version'],'draft':{'outcome':'reports','reports':[{'id':uid(),'description':'Observed issue','category':'geometry','evidence_ids':[fid]}]}})
        result=self.ex.submit(self.user,a['id'],{'version':d['draft_version']})
        payload=json.loads(self.ex.db.execute('SELECT payload FROM submissions WHERE id=?',(result['id'],)).fetchone()[0])
        self.assertEqual(payload['exploration_protocol'],'category_guided_v1')
        self.assertEqual(payload['provided_categories'],['geometry'])
        self.ev.import_submission(payload,lambda *_:workflow.png())
        self.assertEqual(self.ex.db.execute('SELECT count(*) FROM exploration_claims').fetchone()[0],0)

    def test_reservation_survives_process_restart(self):
        from bf.exploration import ExplorationStore
        self.configure();a=allocation.claim(self.ex,self.user);guidance=self.ex.guidance
        self.ex.db.close();self.ex=ExplorationStore(self.root/'exploration');self.ex.guidance=guidance
        self.assertEqual(allocation.claim(self.ex,self.user)['id'],a['id'])

    def test_release_and_switch_preserves_draft_and_resumes_same_attempt(self):
        self.configure();a=allocation.claim(self.ex,self.user)
        d=self.ex.save_draft(self.user,a['id'],{'version':a['draft_version'],'draft':{'outcome':'reports','reports':[],'technical_note':'saved note'}})
        with self.ex.transaction():allocation.finish(self.ex,self.user,a['id'])
        b=allocation.claim(self.ex,self.user,exclude_task_id=a['task']['id'])
        self.assertNotEqual(a['task']['id'],b['task']['id'])
        self.assertEqual(self.ex.snapshot(self.user,a['id'])['status'],'draft')
        with self.ex.transaction():allocation.finish(self.ex,self.user,b['id'])
        resumed=allocation.claim(self.ex,self.user,a['task']['id'])
        self.assertEqual(resumed['id'],a['id'])
        self.assertEqual(resumed['draft']['technical_note'],'saved note')
        self.assertEqual(self.ex.db.execute('SELECT count(*) FROM submissions').fetchone()[0],0)

    def test_http_release_only_releases_current_user_and_next_can_switch(self):
        import threading, urllib.request
        from unittest.mock import Mock
        from bf.http import make_server
        self.configure();a=allocation.claim(self.ex,self.user);other=allocation.claim(self.ex,self.other)
        runtime=Mock();server=make_server('exploration',self.ex,{'port':0,'origin':'http://explore.test','task_id':self.task['id']},runtime)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        token=self.ex.login('explorer','test-explorer-password')
        def post(path,data):
            req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json','Origin':'http://explore.test','Cookie':'bf_explore_session='+token})
            return json.load(urllib.request.urlopen(req))
        try:
            self.assertTrue(post('/api/release',{})['ok'])
            runtime.stop_user.assert_called_once()
            self.assertEqual(runtime.stop_user.call_args.args[0]['id'],self.user['id'])
            claims=self.ex.db.execute('SELECT owner FROM exploration_claims').fetchall()
            self.assertEqual([r[0] for r in claims],[self.other['id']])
            self.assertEqual(self.ex.snapshot(self.user,a['id'])['status'],'draft')
            self.assertTrue(post('/api/next',{'exclude_task_id':a['task']['id']})['unavailable'])
        finally:
            server.shutdown();server.server_close()
