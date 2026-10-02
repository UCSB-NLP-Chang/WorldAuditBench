"""Explore adapter for the shared scheduler. Legacy feedback/evidence stores stay authoritative."""
import secrets,threading,time
from .common import require
from . import allocation
from .scheduler_link import Links

class ScheduledRuntime:
 def __init__(self,store,config):
  self.store=store;self.c=config;self.lock=threading.RLock();self.shared=config['shared_scheduler']
  self.links=Links(store.root/'scheduler-links.sqlite3',self.shared)
  self.mapping=self.shared['task_ids'];self.reverse={v:k for k,v in self.mapping.items()}
  self.connections={};self.deadlines={};self.last_notice={}
 def _owner(self,user):return user['id']
 def _candidates(self,user,task_id=None,exclude=None):
  with self.store.lock:
   now=time.time()
   # Ending an environment does not release the writer's business-level claim.
   busy={r[0] for r in self.store.db.execute('SELECT case_key FROM exploration_claims WHERE cohort=? AND owner<>? AND expires>? AND created>?',(int(user.get('is_test',0)),user['id'],now,now-allocation.MAX_AGE))}
   done={r[0] for r in self.store.db.execute("SELECT t.case_key FROM attempts a JOIN task_catalog t ON t.id=a.task_version_id WHERE a.owner=? AND a.status IN ('submitted','skipped','technical')",(user['id'],))}
   return [self.mapping[t['id']] for t in self.store.accessible_tasks(user,'explorer') if t['id'] in self.mapping and t['id']!=exclude and t['case_key'] not in busy and (task_id is None or t['id']==task_id) and (self.store.guidance is None or self.store.guidance.get(t['id'])) and (task_id is not None or t['case_key'] not in done)]
 def _resume_unsubmitted_drafts(self,user,choices):
  # Re-enable only the caller's eligible drafts on cases with no formal report.
  # The shared scheduler still arbitrates busy cases and global coverage priority.
  with self.store.lock:
   drafts=list(self.store.db.execute("""SELECT a.id,a.task_version_id FROM attempts a
    JOIN task_catalog t ON t.id=a.task_version_id
    WHERE a.owner=? AND a.status='draft' AND NOT EXISTS (
     SELECT 1 FROM submissions s JOIN attempts sa ON sa.id=s.attempt_id
     JOIN task_catalog st ON st.id=sa.task_version_id JOIN users u ON u.id=sa.owner
     WHERE st.case_key=t.case_key AND u.is_test=?)""",(user['id'],int(user.get('is_test',0)))))
  allowed=set(choices)
  for aid,tid in drafts:
   if self.mapping.get(tid) not in allowed:continue
   for old in self.links.attached(aid):
    if old['closed'] and old['lease']:
     self.links.rpc('resume',user['id'],lease=old['lease'])
 def next_task(self,user,exclude_task_id=None):
  with self.lock:
   self.links.flush()
   for _ in range(3):
    active=self.links.active(user['id'])
    if active:
     row=active[-1];status=self.links.poll(row['id']);key=row['id']
    else:
     choices=self._candidates(user,exclude=exclude_task_id)
     if not choices:return {'unavailable':True,'message':'暂时没有可领取的题目：你已处理全部可用题目，或剩余题目正在被其他人探索。请稍后重试。'}
     self._resume_unsubmitted_drafts(user,choices)
     key=secrets.token_hex(16);status=self.links.ensure(key,user['id'],choices,'test' if user.get('is_test') else 'human')
    lease=status.get('lease')
    if not lease:return {'waiting':True,'message':'正在等待可用环境。系统会优先安排适合当前资源的题目。','queue_position':status.get('queue_position')}
    if lease['state']=='ended':
     self.links.finish(key,'cancelled');return {'waiting':True,'message':'启动预留已过期，正在重新安排。'}
    tid=self.reverse[lease['task']]
    try:
     # A manual claim can appear while this request waits in the shared queue.
     # Recheck and claim under the same store lock; never hold it for RPCs.
     with self.store.lock:
      attempt=allocation.claim(self.store,user,tid) if lease['task'] in self._candidates(user,exclude=exclude_task_id) else None
     if attempt is None:
      self.links.finish(key,'cancelled')
      continue
     self.links.attach(key,attempt['id'],tid)
    except Exception:
     self.links.finish(key,'cancelled');raise
    return attempt
   return {'waiting':True,'message':'题目领取状态已变化，正在重新安排。'}
 def _binding(self,aid):
  rows=self.links.attached(aid);return next((r for r in reversed(rows) if not r['closed']),None)
 def start(self,user,aid):
  with self.lock:
   snap=self.store.snapshot(user,aid);require(snap['status']=='draft','探索已经结束',409)
   if self.store.guidance is not None:require(allocation.claim(self.store,user,snap['task']['id'])['id']==aid,'请打开当前领取的草稿',409)
   self.links.flush()
   other=[r for r in self.links.active(user['id']) if r['id'] not in {x['id'] for x in self.links.attached(aid)}]
   require(not other,'请先结束当前会话或取消等待',409)
   row=self._binding(aid)
   if row:
    status=self.links.poll(row['id'])
    if (status.get('lease') or {}).get('state')=='ended':self.links.finish(row['id'],'cancelled');row=None
   if not row:
    # Resume an unfinished report without counting an extra independent participant.
    for old in self.links.attached(aid):
     if old['lease']:self.links.rpc('resume',user['id'],lease=old['lease'])
    key=secrets.token_hex(16)
    self.links.ensure(key,user['id'],[self.mapping[snap['task']['id']]],'test' if user.get('is_test') else 'human')
    self.links.attach(key,aid,snap['task']['id']);row=self.links.row(key)
   if not self.links.started(row['id']):self.store.record_runtime(aid,user,row['id'])
   self.links.mark_started(row['id'])
   self.links.poll(row['id'],activate=True)
   return self.status(user,aid)
 def capacity(self):
  try:return {**self.links.rpc('capacity','system'),'legacy_busy':False,'heartbeat_timeout':180,'max_age':3600}
  except Exception:return {'capacity':0,'running':0,'queued':0,'legacy_busy':False,'heartbeat_timeout':180,'max_age':3600,'unavailable':True}
 def status(self,user,aid):
  with self.lock:
   snap=self.store.snapshot(user,aid);row=self._binding(aid)
   if not row:return {'status':'idle','capacity':self.capacity(),'message':self.last_notice.get(aid,'')}
   require(row['owner']==user['id'],'会话不属于你',403)
   status=self.links.poll(row['id'],activate=self.links.started(row['id']));lease=status.get('lease')
   if lease and lease['state']=='ended':
    self.links.finish(row['id'],'cancelled');return {'status':'idle','capacity':self.capacity(),'message':'资源预留已结束；草稿保留，点击 Start session 可重新申请。'}
   state='queued' if not lease else {'reserved':'queued' if self.links.started(row['id']) else 'idle','starting':'starting','running':'ready'}[lease['state']]
   kind=self.c['tasks'][snap['task']['id']].get('kind','unreal')
   return {'id':row['id'],'attempt_id':aid,'kind':kind,'status':state,'queue_position':status.get('queue_position') or 1,'capacity':self.capacity(),'stream_url':('/browser/' if kind=='browser' else '/stream/')+row['id']+'/' if state=='ready' else None}
 def stop(self,user=None,aid=None,all_sessions=False,**kwargs):
  with self.lock:
   rows=self.links.active(None if all_sessions else user['id'])
   if aid:rows=[r for r in rows if r['id'] in {x['id'] for x in self.links.attached(aid)}]
   for row in rows:self.links.finish(row['id'],'writing')
   return {'status':'idle','message':'环境已释放，可继续填写报告；草稿和截图保留。'}
 def stop_user(self,user):return self.stop(user)
 def finish_attempt(self,user,aid):
  status=self.store.snapshot(user,aid)['status'];outcome={'submitted':'submitted','skipped':'skipped','technical':'technical'}.get(status,'writing')
  # Outbox survives coordinator/network failure after the local answer committed.
  for row in self.links.attached(aid):self.links.enqueue_finish(row['id'],outcome)
  try:self.links.flush()
  except Exception:pass
 def authorize(self,user,sid):
  try:info=self.links.authorize(sid,user['id'])
  except PermissionError:require(False,'会话已结束或不属于你',403)
  row=self.links.attachment(sid)
  require(row is not None,'会话不存在',403);self.store.require_access(user,row['task'],'explorer')
  require(self.store.snapshot(user,row['attempt'])['status']=='draft','探索已结束',403)
  require(info['slot'] is not None,'非 Unreal 会话',403)
  return self.shared['player_port']+info['slot']
 def authorize_browser(self,user,sid):
  try:self.links.authorize(sid,user['id'])
  except PermissionError:require(False,'会话已结束或不属于你',403)
  row=self.links.attachment(sid)
  require(row is not None,'会话不存在',403);self.store.require_access(user,row['task'],'explorer')
  require(self.store.snapshot(user,row['attempt'])['status']=='draft','探索已结束',403)
  profile=self.c['tasks'][row['task']];require(profile.get('kind')=='browser','不是浏览器环境',403);return profile
 def stream_connected(self,sid):
  with self.lock:self.connections[sid]=self.connections.get(sid,0)+1;self.deadlines.pop(sid,None)
 def stream_disconnected(self,sid):
  with self.lock:
   self.connections[sid]=max(0,self.connections.get(sid,0)-1)
   if not self.connections[sid]:self.deadlines[sid]=time.time()+30
 def tick(self):
  with self.lock:
   self.links.flush()
   for sid,deadline in list(self.deadlines.items()):
    if time.time()>=deadline:self.links.finish(sid,'writing');self.deadlines.pop(sid,None)
