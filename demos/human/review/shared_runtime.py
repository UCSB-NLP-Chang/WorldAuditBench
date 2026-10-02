"""Review coordinator adapter. Existing review/evidence records remain unchanged."""
import json,pathlib,secrets
from scheduler_link import Links
class SharedRuntime:
 def __init__(self,store,path):
  self.store=store;self.c=json.loads(pathlib.Path(path).read_text());self.links=Links(pathlib.Path(path).with_name('review-scheduler-links.sqlite3'),self.c)
 def call(self,op,s):
  owner=s['owner'];rows=self.links.attached(s['id'])
  binding=next((x for x in reversed(rows) if not x['closed']),None)
  key=binding['id'] if binding else None
  self.links.flush()
  if op=='stop':
   if key:self.links.finish(key,'skipped')
   return {'stopped':True}
  if key is None:
   key=secrets.token_hex(16)
   for old in self.links.active(owner):
    if old['id']!=key:self.links.finish(old['id'],'skipped')
   profile=self.c['task_ids'][s['task_id']]
   if profile['sha256']!=s['sha256']:raise ValueError('Shared scheduler catalog refresh required')
   self.links.ensure(key,owner,[profile['id']],'review')
   self.links.attach(key,s['id'],s['task_id'])
  state=self.links.poll(key,activate=True);lease=state.get('lease')
  if not lease or lease['state']=='reserved':return {'ready':False,'scheduler_waiting':True,'queue_position':state.get('queue_position')}
  if lease['state']=='ended':return {'ready':False,'game_running':False,'error':'Runtime unavailable'}
  ready=lease['state']=='running'
  return {'ready':ready,'scheduler_waiting':not ready,'game_running':True if ready else None,'signalling_running':True if ready else None,'streamer_registered':ready,'physical_slot':lease.get('slot')}
 def port(self,row):
  bindings=self.links.attached(row['id'])
  active=next((x for x in reversed(bindings) if not x['closed']),None)
  if not active:raise PermissionError('Inactive review runtime')
  try:lease=self.links.authorize(active['id'],row['owner'])
  except Exception as e:raise PermissionError('Inactive scheduler lease') from e
  return self.c['player_port']+lease['slot']
