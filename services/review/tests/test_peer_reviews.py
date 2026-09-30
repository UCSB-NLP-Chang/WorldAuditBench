import json, threading, urllib.request, urllib.error
from test_review_updates import ReviewUpdates

class PeerReviews(ReviewUpdates):
 def test_peer_projection_updates_versions_and_ownership(self):
  self.vote('a');fid=self.vote('b')
  votes=self.s.task_reviews('S01',self.users['a'])
  self.assertEqual(len(votes),1);self.assertEqual(votes[0]['reviewer'],'Bob')
  self.assertEqual(set(votes[0]),{'reviewer','difficulty','quality','comment','updated_at','current_version','counts_toward_current'})
  old=self.s.reviews(self.users['b'])['S01']
  self.s.update_review(fid,self.users['b'],old|dict(comment='<script>literal</script> 中文',quality='fail'))
  votes=self.s.task_reviews('S01',self.users['a'])
  self.assertEqual(votes[0]['comment'],'<script>literal</script> 中文');self.assertEqual(votes[0]['quality'],'fail')
  self.vote('b');self.assertEqual(len(self.s.task_reviews('S01',self.users['a'])),1)
  self.s.tasks['S01']['build_sha256']='c'*64
  self.assertFalse(self.s.task_reviews('S01',self.users['a'])[0]['current_version'])
  self.vote('b');votes=self.s.task_reviews('S01',self.users['a'])
  self.assertEqual([v['current_version'] for v in votes],[True,False])
  self.assertTrue(all(v['reviewer']=='Bob' for v in votes))
  self.assertEqual(self.s.dashboard(self.users['a'])['tasks'][0]['approvals'],1)
 def test_peer_http_auth_unknown_and_empty(self):
  self.vote('a');http=__import__('test_service').mod.make_server(self.s,port=0)
  thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
  def req(task='S01',who='b'):
   try:return urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:{http.server_port}/api/tasks/{task}/reviews',headers={'Cookie':'review_session='+self.cookies.get(who,'bad')}))
   except urllib.error.HTTPError as e:return e
  try:
   self.assertEqual(req(who='bad').status,401)
   self.assertEqual(req(task='missing').status,404)
   self.assertEqual(json.load(req(who='a')),{'reviews':[]})
   result=json.load(req())['reviews'];self.assertEqual(result[0]['reviewer'],'Alice')
   self.assertNotIn('owner',result[0]);self.assertNotIn('feedback_id',result[0])
  finally:http.shutdown();http.server_close();thread.join()
