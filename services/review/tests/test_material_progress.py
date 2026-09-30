import copy,hashlib,json,unittest
from test_dashboard import DashboardTests
from taxonomy import classify

class MaterialProgressTests(DashboardTests):
 def test_reviewer_results_use_latest_applicable_vote(self):
  a,b=self.users[:2]
  self.vote(a,'pass');self.vote(a,'fail');self.vote(b,'uncertain')
  d=self.s.dashboard(a);task=next(t for t in d['tasks'] if t['id']=='S01')
  names={r['id']:r['name'] for r in d['reviewer_options']}
  self.assertEqual({names[r['id']]:r['quality'] for r in task['reviewer_results']},{'A':'fail','B':'uncertain'})
  self.assertEqual(task['my_quality'],'fail');self.assertEqual(task['approvals'],0)
  self.assertEqual(len(d['reviewer_options']),4)
  self.assertEqual(sum(r['mine'] for r in d['reviewer_options']),1)
  self.assertNotIn(a['owner'],json.dumps(d))
  original={k:self.s.tasks['S01'].get(k) for k in ('revision','sha256','build_sha256')}
  self.s.tasks['S01']['build_sha256']='c'*64
  d=self.s.dashboard(a);self.assertFalse(d['tasks'][0]['reviewer_results'])
  self.s.tasks['S01']['review_compatible_versions']=[original]
  self.assertEqual(len(self.s.dashboard(a)['tasks'][0]['reviewer_results']),2)
 def test_same_display_name_keeps_independent_results(self):
  a,b=self.users[:2];b=dict(b,reviewer=a['reviewer'])
  self.vote(a,'pass');self.vote(b,'fail')
  task=self.s.dashboard(a)['tasks'][0]
  self.assertEqual(len(task['reviewer_results']),2)
  self.assertEqual(len({r['id'] for r in task['reviewer_results']}),2)
 def test_material_boundary_and_baseline(self):
  self.assertEqual(classify({'subcategory':'visual.material'})['code'],'V4')
  self.assertIsNone(classify({'subcategory':'V4','case_type':'baseline'}))
  self.assertEqual(classify({'subcategory':'visual.view_appearance'})['code'],'V2')
  self.assertEqual(classify({'subcategory':'state.static_attributes'})['code'],'T2')
