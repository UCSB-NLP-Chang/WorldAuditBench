import json
import unittest
import test_workflow as workflow
from bf.common import canonical, uid
from bf.group_progress import local_metrics, add_group_progress
from bf.progress import progress


class GroupProgressTests(unittest.TestCase):
    setUp=workflow.Workflow.setUp
    tearDown=workflow.Workflow.tearDown

    def publish(self, user):
        a=self.ex.start_attempt(user,self.task['id'])
        self.ex.record_runtime(a['id'],user,uid())
        a=self.ex.save_draft(user,a['id'],{'version':a['draft_version'],'draft':{'outcome':'none','reports':[]}})
        self.ex.submit(user,a['id'],{'version':a['draft_version']})
        p=json.loads(self.ex.db.execute('SELECT payload FROM submissions WHERE attempt_id=?',(a['id'],)).fetchone()[0])
        self.ev.import_submission(p,lambda *_: b'')
        return p['id']

    def judge_answer(self, user, sid):
        d=self.ev.claim(user,sid)
        return self.ev.save_judgment(user,sid,{'revision':d['revision'],'answers':[{'report_id':'none','verdict':'correct_none','reason':'PRIVATE_REASON_SENTINEL'}]})

    def test_unique_people_not_attempts_or_revisions(self):
        first=self.publish(self.user);second=self.publish(self.user);third=self.publish(self.other)
        self.judge_answer(self.judge,first);self.judge_answer(self.judge,first);self.judge_answer(self.judge,second)
        ex=local_metrics(self.ex,'exploration',0)[self.task['id']]
        ev=local_metrics(self.ev,'evaluation',0)[self.task['id']]
        self.assertEqual((ex['completed_explorers'],ex['submitted_answers']),(2,3))
        self.assertEqual((ev['reviewer_count'],ev['reviewed_answers']),(1,2))
        self.judge_answer(self.judge2,third)
        self.assertEqual(local_metrics(self.ev,'evaluation',0)[self.task['id']]['reviewer_count'],2)

    def test_claim_is_not_review_and_expired_claim_is_pending(self):
        sid=self.publish(self.user);self.ev.claim(self.judge,sid)
        d=local_metrics(self.ev,'evaluation',0)[self.task['id']]
        self.assertEqual((d.get('reviewer_count',0),d['active_reviews'],d['reviewed_answers']),(0,1,0))
        self.ev.db.execute('UPDATE review_assignments SET lease_until=0')
        self.assertEqual(local_metrics(self.ev,'evaluation',0)[self.task['id']]['pending_answers'],1)

    def test_group_projection_has_counts_only_and_includes_zero_cases(self):
        sid=self.publish(self.user);self.judge_answer(self.judge,sid)
        second={'id':uid(),'title':'Second','query':'Explore','controls':'WASD','case_key':'PRIVATE_CASE_ID'}
        self.ex.register_task(second);self.ex.grant_task('explorer',second['id'],'explorer')
        data=add_group_progress(self.ex,'exploration',self.user,progress(self.ex,'exploration',self.user),local_metrics(self.ev,'evaluation',0))
        self.assertEqual(data['group']['summary']['total_cases'],2)
        self.assertEqual(data['group']['summary']['reviewed_cases'],1)
        self.assertEqual(data['group']['summary']['exploration_percent'],50.0)
        self.assertEqual(data['group']['summary']['fully_reviewed_cases'],1)
        # One of two permitted explorers is sufficient; a new answer reopens backlog.
        self.publish(self.other)
        updated=add_group_progress(self.ex,'exploration',self.user,progress(self.ex,'exploration',self.user),local_metrics(self.ev,'evaluation',0))
        self.assertEqual(updated['group']['summary']['exploration_percent'],50.0)
        self.assertEqual(updated['group']['summary']['fully_reviewed_cases'],0)
        payload=canonical(data['group'])
        for secret in ['PRIVATE_REASON_SENTINEL','SECRET_SENTINEL','PRIVATE_CASE_ID','correct_none','judge']:
            self.assertNotIn(secret,payload)
        hidden={'id':uid(),'title':'Not assigned','query':'Hidden','controls':'WASD'}
        self.ex.register_task(hidden)
        self.assertEqual(len(add_group_progress(self.ex,'exploration',self.user,progress(self.ex,'exploration',self.user),{})['group']['cases']),2)

    def test_unavailable_peer_is_unknown_not_zero(self):
        data=add_group_progress(self.ex,'exploration',self.user,progress(self.ex,'exploration',self.user),None)
        summary=data['group']['summary']
        self.assertEqual(summary['assigned_explorers'],2)
        self.assertIsNone(summary['reviewer_count']);self.assertIsNone(summary['review_percent'])
        self.assertFalse(data['group']['peer_available'])
        self.assertIsNone(summary['fully_reviewed_cases'])

    def test_qa_answers_do_not_inflate_formal_counts(self):
        sid=self.publish(self.user);self.judge_answer(self.judge,sid)
        self.ex.db.execute('UPDATE users SET is_test=1 WHERE id=?',(self.user['id'],))
        self.ev.db.execute('UPDATE submission_authors SET is_test=1 WHERE submission_id=?',(sid,))
        self.ev.db.execute('UPDATE users SET is_test=1 WHERE id=?',(self.judge['id'],))
        ex=local_metrics(self.ex,'exploration',0)[self.task['id']]
        self.assertEqual(ex['assigned_explorers'],1);self.assertEqual(ex.get('completed_explorers',0),0)
        self.assertEqual(local_metrics(self.ev,'evaluation',0),{})
        self.assertEqual(local_metrics(self.ev,'evaluation',1)[self.task['id']]['reviewer_count'],1)

    def test_same_case_versions_do_not_duplicate_assignment_denominator(self):
        version={'id':uid(),'title':'Updated world','query':'Explore','controls':'WASD','case_key':self.task['id']}
        self.ex.register_task(version);self.ex.grant_task('explorer',version['id'],'explorer')
        group=add_group_progress(self.ex,'exploration',self.user,progress(self.ex,'exploration',self.user),{})['group']
        self.assertEqual(group['summary']['total_cases'],1)
        self.assertEqual(group['summary']['assigned_explorers'],2)

    def test_restart_preserves_drafts_for_multiple_cases(self):
        from bf.exploration import ExplorationStore
        second={'id':uid(),'title':'Second case','query':'Explore','controls':'WASD'}
        self.ex.register_task(second);self.ex.grant_task('explorer',second['id'],'explorer')
        draft=self.ex.start_attempt(self.user,second['id'])
        old=self.ex.snapshot(self.user,self.a['id'])
        self.ex.db.close();self.ex=ExplorationStore(self.root/'exploration')
        self.assertEqual(self.ex.snapshot(self.user,self.a['id']),old)
        self.assertEqual(self.ex.snapshot(self.user,draft['id'])['status'],'draft')
        self.assertEqual(self.ex.start_attempt(self.user,second['id'])['id'],draft['id'])
