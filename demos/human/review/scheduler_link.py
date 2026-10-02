"""Durable app-to-scheduler bindings and completion outbox. No review payloads here."""
import json,pathlib,secrets,sqlite3,threading,urllib.request,urllib.error

class Links:
 def __init__(self,path,config,rpc=None):
  self.c=config;self.lock=threading.RLock();self.rpc=rpc or self._http
  self.db=sqlite3.connect(path,check_same_thread=False,timeout=15);self.db.row_factory=sqlite3.Row
  self.db.executescript('''PRAGMA journal_mode=WAL;
   CREATE TABLE IF NOT EXISTS links(id TEXT PRIMARY KEY,owner TEXT NOT NULL,candidates TEXT NOT NULL,cohort TEXT NOT NULL,nonce TEXT NOT NULL,request TEXT,lease TEXT,closed INTEGER NOT NULL DEFAULT 0,wanted TEXT,created REAL NOT NULL DEFAULT (strftime('%s','now')));
   CREATE TABLE IF NOT EXISTS attachments(id TEXT PRIMARY KEY,attempt TEXT,task TEXT);
   CREATE TABLE IF NOT EXISTS activations(id TEXT PRIMARY KEY);
  ''')
 def _http(self,operation,owner,**data):
  req=urllib.request.Request(self.c['url']+'/scheduler',data=json.dumps(dict(data,operation=operation,owner=owner)).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+self.c['token']})
  with urllib.request.urlopen(req,timeout=10) as r:return json.load(r)['result']
 def row(self,key):
  with self.lock:
   r=self.db.execute('SELECT * FROM links WHERE id=?',(key,)).fetchone();return dict(r) if r else None
 def ensure(self,key,owner,candidates,cohort='human'):
  with self.lock,self.db:
   r=self.row(key)
   if r and (r['owner']!=owner or json.loads(r['candidates'])!=sorted(candidates)):raise ValueError('Binding mismatch')
   if not r:self.db.execute('INSERT INTO links(id,owner,candidates,cohort,nonce) VALUES(?,?,?,?,?)',(key,owner,json.dumps(sorted(candidates)),cohort,secrets.token_hex(16)))
  return self.poll(key)
 def poll(self,key,activate=False):
  with self.lock:
   r=self.row(key)
   if not r:raise ValueError('Unknown scheduler binding')
   if not r['request']:
    value=self.rpc('request',r['owner'],candidates=json.loads(r['candidates']),cohort=r['cohort'],request_id=r['nonce'])
    expected=self.c['service']+':'+r['nonce']
    if value['id']!=expected:raise ValueError('Previous assignment must be released first')
    with self.db:self.db.execute('UPDATE links SET request=? WHERE id=?',(value['id'],key))
    r=self.row(key)
   self.rpc('heartbeat',r['owner'],request_id=r['request'])
   status=self.rpc('status',r['owner'],request_id=r['request']);lease=status.get('lease')
   if not lease and status['state'] in ('expired','cancelled') and not r['closed']:
    with self.db:self.db.execute('UPDATE links SET nonce=?,request=NULL WHERE id=?',(secrets.token_hex(16),key))
    return self.poll(key,activate=activate)
   if lease:
    with self.db:self.db.execute('UPDATE links SET lease=? WHERE id=?',(lease['id'],key))
    if activate and lease['state']=='reserved':status['lease']=self.rpc('activate',r['owner'],lease=lease['id'])
   return status
 def enqueue_finish(self,key,outcome='writing'):
  with self.lock,self.db:
   r=self.row(key)
   if not r:return
   self.db.execute('UPDATE links SET closed=1,wanted=? WHERE id=?',(outcome,key))
 def finish(self,key,outcome='writing'):
  self.enqueue_finish(key,outcome);self.flush(key)
 def flush(self,key=None):
  with self.lock:
   rows=self.db.execute('SELECT * FROM links WHERE wanted IS NOT NULL'+(' AND id=?' if key else ''),((key,) if key else ())).fetchall()
   for row in rows:
    r=dict(row)
    if not r['request']:
     # Ensure the idempotent ticket first: a lost response may have created it remotely.
     self.poll(r['id']);r=self.row(r['id'])
    state=self.rpc('status',r['owner'],request_id=r['request']);lease=state.get('lease')
    if lease:
     desired=r['wanted'];experienced=lease.get('ready_at') is not None
     if not experienced:desired='cancelled'
     if lease['state']=='ended':
      if experienced and lease['outcome'] in ('writing','paused','interrupted','cancelled','technical') and desired in ('submitted','not_found','skipped','technical'):
       self.rpc('complete_report',r['owner'],lease=lease['id'],outcome=desired)
     else:self.rpc('finish',r['owner'],lease=lease['id'],outcome=desired)
    else:self.rpc('cancel',r['owner'],request_id=r['request'])
    with self.db:self.db.execute('UPDATE links SET wanted=NULL WHERE id=? AND wanted=?',(r['id'],r['wanted']))
 def active(self,owner=None):
  with self.lock:return [dict(r) for r in self.db.execute('SELECT * FROM links WHERE closed=0'+(' AND owner=?' if owner else '')+' ORDER BY created,id',((owner,) if owner else ()))]
 def attach(self,key,attempt,task):
  with self.lock,self.db:self.db.execute('INSERT OR REPLACE INTO attachments VALUES(?,?,?)',(key,attempt,task))
 def attached(self,attempt):
  with self.lock:return [dict(r) for r in self.db.execute('SELECT l.*,a.attempt,a.task FROM links l JOIN attachments a ON a.id=l.id WHERE a.attempt=? ORDER BY l.created,l.rowid',(attempt,))]
 def authorize(self,key,owner):
  r=self.row(key)
  if not r or r['closed'] or r['owner']!=owner or not r['lease']:raise PermissionError('Inactive scheduler lease')
  try:return self.rpc('authorize',owner,lease=r['lease'])
  except urllib.error.HTTPError as e:
   if e.code in (403,409):raise PermissionError('Inactive scheduler lease') from e
   raise

 def attachment(self,key):
  with self.lock:
   row=self.db.execute('SELECT * FROM attachments WHERE id=?',(key,)).fetchone();return dict(row) if row else None
 def mark_started(self,key):
  with self.lock,self.db:self.db.execute('INSERT OR IGNORE INTO activations VALUES(?)',(key,))
 def started(self,key):
  with self.lock:return self.db.execute('SELECT 1 FROM activations WHERE id=?',(key,)).fetchone() is not None
