"""Journaled reservation of idle scheduler GPUs for a private native batch."""
from pathlib import Path
import json,os,sqlite3,time,uuid

def owned(entry):
 with sqlite3.connect(entry['database'],timeout=10) as db:
  return db.execute("SELECT 1 FROM slots WHERE id=? AND state='quarantined' AND last_owner=? AND task IS NULL AND lease IS NULL",(entry['saved']['id'],entry['owner'])).fetchone() is not None

def verify(path,gpu):
 d=json.loads(Path(path).read_text());os.kill(d['pid'],0)
 if d.get('status')!='active':raise RuntimeError('Batch GPU reservation is not active')
 entry=next(e for e in d['entries'] if e['gpu']==gpu)
 if not owned(entry):raise RuntimeError('Batch lost its GPU reservation')
 return entry

class Reservation:
 def __init__(self,production,journal,gpus):
  self.journal=Path(journal);self.data={'pid':os.getpid(),'status':'acquiring','entries':[],'created_at':time.time()};self.production=Path(production);self.gpus=gpus
 def save(self):
  p=self.journal.with_suffix('.tmp');p.write_text(json.dumps(self.data,indent=2));p.replace(self.journal)
 def acquire(self):
  if self.journal.exists():raise RuntimeError('Reservation journal already exists; inspect/recover explicitly')
  self.save()
  try:
   for gpu in self.gpus:
    configs=[json.loads((self.production/n).read_text()) for n in ['audit/runtime.json','shared/runtime-prod.json']]
    matches=[r for r in configs if gpu in r['slot_gpus']]
    if len(matches)!=1:raise RuntimeError('GPU must have exactly one scheduler')
    r=matches[0];scheduler=json.loads(Path(r['scheduler_config']).read_text());slots=[i for i,g in enumerate(r['slot_gpus']) if g==gpu]
    with sqlite3.connect(scheduler['database'],timeout=10) as db:
     db.row_factory=sqlite3.Row;db.execute('BEGIN IMMEDIATE');rows=[dict(x) for x in db.execute('SELECT * FROM slots') if x['id'] in slots]
     if len(rows)!=len(slots) or any(x['state']!='free' or x['task'] or x['lease'] for x in rows):raise RuntimeError('GPU has an active/warm/reserved human session')
     if db.execute("SELECT 1 FROM requests WHERE state='waiting' LIMIT 1").fetchone():raise RuntimeError('Human requests are waiting; admission deferred')
     placeholders=','.join('?' for _ in slots)
     if db.execute(f"SELECT 1 FROM commands WHERE state='pending' AND slot IN ({placeholders})",slots).fetchone():raise RuntimeError('GPU has pending runtime commands')
     entry={'gpu':gpu,'database':scheduler['database'],'saved':rows[0],'owner':'native-nomap-batch:'+uuid.uuid4().hex}
     self.data['entries'].append(entry);self.save()
     db.execute("UPDATE slots SET state='quarantined',last_owner=? WHERE id=?",(entry['owner'],rows[0]['id']))
   self.data['status']='active';self.save()
  except BaseException:self.release();raise
 def release(self):
  for e in self.data['entries']:
   with sqlite3.connect(e['database'],timeout=10) as db:
    db.execute('BEGIN IMMEDIATE');db.execute("UPDATE slots SET state=?,last_owner=? WHERE id=? AND state='quarantined' AND last_owner=? AND task IS NULL AND lease IS NULL",(e['saved']['state'],e['saved']['last_owner'],e['saved']['id'],e['owner']))
  self.data.update(status='released',released_at=time.time());self.save()
