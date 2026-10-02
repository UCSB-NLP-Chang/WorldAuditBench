"""Persistent shared scheduling policy. Only trusted service adapters call this API.

No process is reused unless both task profiles explicitly certify that transition.
A physical slot is reusable only after a worker acknowledges its fencing/teardown.
"""
import contextlib
import fcntl
import hashlib
import json
import math
import secrets
import sqlite3
import threading
import time


class ScheduleError(ValueError):
    pass


class Scheduler:
    def __init__(self, path, tasks, **options):
        self._owner_lock=open(str(path)+'.owner.lock','a')
        try:
            fcntl.flock(self._owner_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self._initialize(path,tasks,**options)
        except BaseException:
            self.close();raise

    def _initialize(self, path, tasks, *, slots=1, memory_mb=12000, reserve_seconds=45,
                 heartbeat_seconds=180, warm_seconds=30, batch_tasks=3,
                 batch_seconds=900, max_run_seconds=3600, launch_seconds=120,
                 failure_limit=3, coverage_band=1, repeat_services=(), clock=time.time,
                 gpu_devices=None, slot_gpus=None, gpu_max_utilization=95, gpu_sample_ttl=10, submission_targets=None):
        numbers=(slots,memory_mb,reserve_seconds,heartbeat_seconds,warm_seconds,
                 batch_tasks,batch_seconds,max_run_seconds,launch_seconds,failure_limit)
        if any(not isinstance(n,(int,float)) or not math.isfinite(n) or n<=0 for n in numbers):
            raise ScheduleError('Positive finite scheduler limits required')
        if type(slots) is not int or not 1<=slots<=32 or coverage_band<0:
            raise ScheduleError('Invalid slot count or coverage band')
        self.repeat_services=set(repeat_services)
        self.submission_targets=dict(submission_targets or {})
        if any(not isinstance(k,str) or not k or type(v) is not int or v<1 for k,v in self.submission_targets.items()):raise ScheduleError('Invalid submission target')
        self.tasks={t['id']:dict(t) for t in tasks}
        if len(self.tasks)!=len(tasks):raise ScheduleError('Duplicate task IDs')
        for t in self.tasks.values():
            if t.get('kind') not in ('browser','unreal'):raise ScheduleError('Task kind required')
            for k in ('id','case_key','scene','category'):
                if not isinstance(t.get(k),str) or not t[k]:raise ScheduleError('Missing '+k)
            if t['kind']=='unreal':
                if not isinstance(t.get('group'),str) or not t['group']:raise ScheduleError('Verified runtime group required')
                if not isinstance(t.get('memory_mb'),(int,float)) or not 0<t['memory_mb']<=memory_mb:raise ScheduleError('Invalid task memory budget')
            for key in ('cold_seconds','switch_seconds'):
                if key in t and (not isinstance(t[key],(int,float)) or not math.isfinite(t[key]) or t[key]<0):raise ScheduleError('Invalid cost estimate')
            if type(t.get('target',3)) is not int or t.get('target',3)<1:raise ScheduleError('Invalid coverage target')
        self.clock=clock;self.lock=threading.RLock();self.memory_mb=memory_mb
        self.gpu_devices={d['index']:dict(d) for d in (gpu_devices or [])}
        self.slot_gpus=slot_gpus
        self.gpu_sample={};self.gpu_sample_time=None
        self.gpu_max_utilization=gpu_max_utilization;self.gpu_sample_ttl=gpu_sample_ttl
        if self.gpu_devices:
            if len(self.gpu_devices)!=len(gpu_devices) or not isinstance(slot_gpus,list) or len(slot_gpus)!=slots:
                raise ScheduleError('Explicit GPU mapping required for every slot')
            if any(type(g)!=int or g not in self.gpu_devices for g in slot_gpus):raise ScheduleError('Unknown slot GPU')
            for g,d in self.gpu_devices.items():
                if type(g)!=int or g<0 or not isinstance(d.get('uuid'),str) or not d['uuid'].startswith('GPU-') or not 0<d.get('memory_mb',0)<=memory_mb:
                    raise ScheduleError('Invalid physical GPU budget')
            if not 0<gpu_max_utilization<=100 or not 0<gpu_sample_ttl<=60:raise ScheduleError('Invalid GPU telemetry limits')
        elif slot_gpus is not None:raise ScheduleError('GPU devices required')
        self.reserve_seconds=reserve_seconds;self.heartbeat_seconds=heartbeat_seconds
        self.warm_seconds=warm_seconds;self.batch_tasks=batch_tasks;self.batch_seconds=batch_seconds
        self.max_run_seconds=max_run_seconds;self.launch_seconds=launch_seconds
        self.failure_limit=failure_limit;self.coverage_band=coverage_band
        self.db=sqlite3.connect(path,check_same_thread=False,isolation_level=None)
        self.db.row_factory=sqlite3.Row
        self.db.executescript('''PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS slots(id INTEGER PRIMARY KEY,state TEXT NOT NULL,task TEXT,lease TEXT,
          last_owner TEXT,batch_tasks INTEGER NOT NULL DEFAULT 0,batch_seconds REAL NOT NULL DEFAULT 0,
          warm_until REAL,generation INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,owner TEXT NOT NULL,service TEXT NOT NULL,
          cohort TEXT NOT NULL,mode TEXT NOT NULL,candidates TEXT NOT NULL,fingerprint TEXT NOT NULL,
          created REAL NOT NULL,heartbeat REAL NOT NULL,state TEXT NOT NULL,lease TEXT);
        CREATE UNIQUE INDEX IF NOT EXISTS one_waiter ON requests(service,owner) WHERE state='waiting';
        CREATE TABLE IF NOT EXISTS leases(id TEXT PRIMARY KEY,request TEXT UNIQUE NOT NULL,owner TEXT NOT NULL,
          service TEXT NOT NULL,cohort TEXT NOT NULL,task TEXT NOT NULL,case_key TEXT NOT NULL,
          slot INTEGER,state TEXT NOT NULL,created REAL NOT NULL,heartbeat REAL NOT NULL,
          ready_at REAL,ended REAL,outcome TEXT,reason TEXT);
        CREATE UNIQUE INDEX IF NOT EXISTS one_live_owner ON leases(service,owner)
          WHERE state IN ('reserved','starting','running');
        CREATE UNIQUE INDEX IF NOT EXISTS one_live_case ON leases(service,cohort,case_key)
          WHERE state IN ('reserved','starting','running');
        CREATE TABLE IF NOT EXISTS commands(id TEXT PRIMARY KEY,slot INTEGER NOT NULL,generation INTEGER NOT NULL,
          lease TEXT,action TEXT NOT NULL,source TEXT,target TEXT,state TEXT NOT NULL,created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS faults(task TEXT PRIMARY KEY,count INTEGER NOT NULL,quarantined INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS costs(source TEXT NOT NULL,target TEXT NOT NULL,seconds REAL NOT NULL,
          samples INTEGER NOT NULL,PRIMARY KEY(source,target));
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,time REAL NOT NULL,kind TEXT NOT NULL,data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS history(id TEXT PRIMARY KEY,service TEXT,owner TEXT,cohort TEXT,task TEXT,case_key TEXT,outcome TEXT);
        CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        ''')
        with self.tx():
            digest=hashlib.sha256(json.dumps(self.tasks,sort_keys=True).encode()).hexdigest()
            old=self.db.execute("SELECT value FROM metadata WHERE key='catalog'").fetchone()
            if old and old['value']!=digest:raise ScheduleError('Catalog changed: migrate explicitly, do not reinterpret existing leases')
            self.db.execute("INSERT OR IGNORE INTO metadata VALUES('catalog',?)",(digest,))
            count=self.db.execute('SELECT count(*) FROM slots').fetchone()[0]
            if count and count!=slots:raise ScheduleError('Slot count changed: drain before migration')
            topology=json.dumps({'devices':gpu_devices,'slots':slot_gpus},sort_keys=True)
            previous=self.db.execute("SELECT value FROM metadata WHERE key='gpu_topology'").fetchone()
            if previous and previous['value']!=topology:raise ScheduleError('GPU topology changed: migrate explicitly')
            if not previous and self.gpu_devices and self.db.execute("SELECT 1 FROM slots WHERE state!='free'").fetchone():raise ScheduleError('Drain legacy slots before enabling GPU mapping')
            self.db.execute("INSERT OR IGNORE INTO metadata VALUES('gpu_topology',?)",(topology,))
            for i in range(slots):self.db.execute("INSERT OR IGNORE INTO slots(id,state) VALUES(?,'free')",(i,))
            # Supervisor state may have survived this process. Never assume its GPU is free.
            for s in self.db.execute("SELECT * FROM slots WHERE state!='free'").fetchall():
                self._end(s['lease'],'interrupted','coordinator restarted')
                self.db.execute("UPDATE commands SET state='obsolete' WHERE slot=? AND state='pending'",(s['id'],))
                self._command(s,'stop',None,None)
            for l in self.db.execute("SELECT id FROM leases WHERE slot IS NULL AND state IN ('reserved','starting','running')").fetchall():
                self._end(l['id'],'interrupted','coordinator restarted')

    @contextlib.contextmanager
    def tx(self):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:yield;self.db.execute('COMMIT')
            except BaseException:self.db.execute('ROLLBACK');raise

    def _event(self,kind,**data):
        self.db.execute('INSERT INTO events(time,kind,data) VALUES(?,?,?)',(self.clock(),kind,json.dumps(data,sort_keys=True)))

    def _row(self,table,id):
        row=self.db.execute('SELECT * FROM '+table+' WHERE id=?',(id,)).fetchone()
        if row is None:raise ScheduleError('Unknown '+table)
        return dict(row)

    def _owned(self,lease,service,owner):
        l=self._row('leases',lease)
        if (l['service'],l['owner'])!=(service,owner):raise ScheduleError('Lease owner mismatch')
        return l

    def _end(self,lease,outcome,reason=None):
        if not lease:return
        self.db.execute("UPDATE leases SET state='ended',ended=?,outcome=?,reason=? WHERE id=? AND state!='ended'",(self.clock(),outcome,reason,lease))
        self.db.execute("UPDATE requests SET state='finished' WHERE lease=?",(lease,))

    def _command(self,slot,action,target,lease):
        generation=slot['generation']+1
        self.db.execute("UPDATE slots SET state=?,generation=?,lease=? WHERE id=?",('stopping' if action=='stop' else 'starting',generation,lease,slot['id']))
        self.db.execute('INSERT INTO commands VALUES(?,?,?,?,?,?,?,?,?)',(secrets.token_hex(16),slot['id'],generation,lease,action,slot['task'],target,'pending',self.clock()))
        self._event('command',slot=slot['id'],generation=generation,action=action,target=target)

    def request(self,service,owner,candidates,*,request_id,cohort='human',mode='auto'):
        """Adapters derive candidate grants server-side; never trust browser candidate IDs."""
        if mode not in ('auto','unreal','browser') or not service or not owner or not request_id:raise ScheduleError('Invalid request')
        candidates=sorted(set(candidates))
        if not candidates or any(t not in self.tasks for t in candidates):raise ScheduleError('Invalid candidates')
        encoded=json.dumps(candidates);fingerprint=json.dumps([service,owner,cohort,mode,candidates])
        with self.tx():
            old=self.db.execute('SELECT * FROM requests WHERE id=?',(request_id,)).fetchone()
            if old:
                if old['fingerprint']!=fingerprint:raise ScheduleError('Idempotency key reused with different input')
                return dict(old)
            existing=self.db.execute("SELECT * FROM requests WHERE service=? AND owner=? AND state IN ('waiting','allocated')",(service,owner)).fetchone()
            if existing:return dict(existing)
            now=self.clock()
            self.db.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,?,?,?,?,?)',(request_id,owner,service,cohort,mode,encoded,fingerprint,now,now,'waiting',None))
            self._event('request',request=request_id,service=service,mode=mode)
            return self._row('requests',request_id)

    def heartbeat(self,service,owner,request_id):
        with self.tx():
            r=self._row('requests',request_id)
            if (r['service'],r['owner'])!=(service,owner):raise ScheduleError('Request owner mismatch')
            self.db.execute('UPDATE requests SET heartbeat=? WHERE id=?',(self.clock(),request_id))
            if r['lease']:self.db.execute('UPDATE leases SET heartbeat=? WHERE id=? AND state!=\'ended\'',(self.clock(),r['lease']))

    def cancel(self,service,owner,request_id):
        with self.tx():
            r=self._row('requests',request_id)
            if (r['service'],r['owner'])!=(service,owner):raise ScheduleError('Request owner mismatch')
            if r['state']=='waiting':self.db.execute("UPDATE requests SET state='cancelled' WHERE id=?",(request_id,))
            elif r['state']=='allocated':self._finish(self._owned(r['lease'],service,owner),'cancelled')

    def _eligible(self,r):
        busy={x[0] for x in self.db.execute("SELECT case_key FROM leases WHERE service=? AND cohort=? AND state IN ('reserved','starting','running')",(r['service'],r['cohort']))}
        # Technical failure is retryable; completed independent participation is not.
        done={x[0] for x in self.db.execute("SELECT case_key FROM leases WHERE service=? AND owner=? AND outcome IN ('submitted','not_found','writing')",(r['service'],r['owner']))}
        done.update(x[0] for x in self.db.execute("SELECT case_key FROM history WHERE service=? AND owner=? AND outcome IN ('submitted','not_found')",(r['service'],r['owner'])))
        if r['service'] in self.repeat_services:done=set()
        bad={x[0] for x in self.db.execute('SELECT task FROM faults WHERE quarantined=1')}
        eligible = [self.tasks[i] for i in json.loads(r['candidates']) if i not in bad and self.tasks[i]['case_key'] not in busy|done and (r['mode']=='auto' or self.tasks[i]['kind']==r['mode'])]
        if eligible and r['service'] in self.submission_targets:
            # Rank coverage across engines before dispatch splits GPU/browser work.
            # Only available, permitted cases participate in this priority tier.
            scored=[(t,self._coverage(r,t)) for t in eligible]
            deficit=max(n for _,n in scored)
            return [t for t,n in scored if n==deficit]
        return eligible

    def _coverage(self,r,t):
        if r['service'] in self.submission_targets:
            n=self.db.execute("SELECT count(DISTINCT owner) FROM (SELECT owner FROM leases WHERE service=? AND cohort=? AND case_key=? AND outcome='submitted' UNION SELECT owner FROM history WHERE service=? AND cohort=? AND case_key=? AND outcome='submitted')",(r['service'],r['cohort'],t['case_key'])*2).fetchone()[0]
            return max(0,self.submission_targets[r['service']]-n)
        n=self.db.execute("SELECT count(DISTINCT owner) FROM (SELECT owner FROM leases WHERE service=? AND cohort=? AND case_key=? AND (outcome IN ('submitted','not_found','writing') OR state IN ('reserved','starting','running')) UNION SELECT owner FROM history WHERE service=? AND cohort=? AND case_key=? AND outcome IN ('submitted','not_found'))",(r['service'],r['cohort'],t['case_key'])*2).fetchone()[0]
        return max(0,t.get('target',3)-n)

    def _can_reuse(self,s,t):
        if not s or not s['task'] or s['task'] not in self.tasks:return False
        a=self.tasks[s['task']]
        return a.get('group')==t.get('group') and a.get('reuse_verified') is True and t.get('reuse_verified') is True

    def _cost(self,s,t,owner=None):
        if not s or not self._can_reuse(s,t) or (owner is not None and s['last_owner']!=owner and not t.get('handoff_verified')):return t.get('cold_seconds',30)
        sample=self.db.execute('SELECT seconds FROM costs WHERE source=? AND target=?',(s['task'],t['id'])).fetchone()
        return sample[0] if sample else t.get('switch_seconds',5)

    def _choose(self,r,tasks,slot=None):
        if not tasks:return None
        deficit=max(self._coverage(r,t) for t in tasks)
        band=0 if r['service'] in self.submission_targets else self.coverage_band
        tasks=[t for t in tasks if self._coverage(r,t)>=deficit-band]
        history=self.db.execute("SELECT task FROM leases WHERE service=? AND owner=? AND outcome IN ('submitted','not_found','writing')",(r['service'],r['owner'])).fetchall()
        history+=self.db.execute("SELECT task FROM history WHERE service=? AND owner=? AND outcome IN ('submitted','not_found')",(r['service'],r['owner'])).fetchall()
        def rank(t):
            exposures=sum(self.tasks[h['task']]['scene']==t['scene'] for h in history)
            category=sum(self.tasks[h['task']]['category']==t['category'] for h in history)
            # Stable per-request lottery instead of global ID bias.
            lottery=hashlib.sha256((r['id']+t['id']).encode()).hexdigest()
            return self._cost(slot,t,r['service']+':'+r['owner']),exposures,category,lottery
        return min(tasks,key=rank)

    def _slot_memory(self,s):
        if s['state']=='quarantined':return self.memory_mb
        current=self.tasks.get(s['task'],{}).get('memory_mb',0)
        if s['lease']:
            l=self._row('leases',s['lease']);target=self.tasks[l['task']]
            if l['state'] in ('reserved','starting'):
                return target['memory_mb']+(current if self._can_reuse(s,target) else 0)
        return current

    def _memory(self,s,t):
        if self.gpu_devices:
            gpu=self.slot_gpus[s['id']];sample=self._gpu_sample(gpu)
            if sample is None or sample['utilization']>=self.gpu_max_utilization:return False
            # Reservations count before processes allocate memory. Observed usage also
            # covers non-service processes and underestimated runtime footprints.
            current=self._gpu_reserved(gpu)
            budget=min(self.gpu_devices[gpu]['memory_mb'],sample['total_mb']-1536)
            return max(current,sample['used_mb'])+t['memory_mb']<=budget
        others=sum(self._slot_memory(dict(x)) for x in self.db.execute("SELECT * FROM slots WHERE id!=? AND state!='free'",(s['id'],)))
        old=self.tasks.get(s['task'],{}).get('memory_mb',0)
        extra=old if self._can_reuse(s,t) else 0
        return others+t['memory_mb']+extra<=self.memory_mb

    def update_gpus(self,samples):
        with self.lock:
            self.gpu_sample={int(k):dict(v) for k,v in samples.items()}
            self.gpu_sample_time=self.clock()

    def _gpu_sample(self,gpu):
        if self.gpu_sample_time is None or not 0<=self.clock()-self.gpu_sample_time<=self.gpu_sample_ttl:return None
        sample=self.gpu_sample.get(gpu)
        if not sample or sample.get('uuid')!=self.gpu_devices[gpu]['uuid']:return None
        if any(not isinstance(sample.get(k),(int,float)) or not math.isfinite(sample[k]) for k in ('used_mb','total_mb','utilization')):return None
        if not 0<=sample['used_mb']<=sample['total_mb'] or not 0<=sample['utilization']<=100:return None
        return sample

    def _gpu_reserved(self,gpu):
        return sum(self._slot_memory(dict(s)) for s in self.db.execute("SELECT * FROM slots WHERE state!='free'") if self.slot_gpus[s['id']]==gpu)

    def _slot_rank(self,s):
        if not self.gpu_devices:return (s['id'],)
        gpu=self.slot_gpus[s['id']];sample=self._gpu_sample(gpu)
        if sample is None:return (float('inf'),float('inf'),s['id'])
        budget=self.gpu_devices[gpu]['memory_mb']
        pressure=max(self._gpu_reserved(gpu)/budget,sample['used_mb']/budget,sample['utilization']/100)
        return (pressure,self._gpu_reserved(gpu),s['id'])

    def _allocate(self,r,t,s=None):
        lid=secrets.token_hex(16);now=self.clock()
        self.db.execute('INSERT INTO leases VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(lid,r['id'],r['owner'],r['service'],r['cohort'],t['id'],t['case_key'],s['id'] if s else None,'reserved',now,now,None,None,None,None))
        self.db.execute("UPDATE requests SET state='allocated',lease=? WHERE id=?",(lid,r['id']))
        if s:self.db.execute("UPDATE slots SET state='reserved',lease=? WHERE id=?",(lid,s['id']))
        self._event('allocated',request=r['id'],lease=lid,task=t['id'],slot=s['id'] if s else None,wait_seconds=now-r['created'])

    def dispatch(self):
        with self.tx():
            self._expire()
            waiting=[dict(x) for x in self.db.execute("SELECT * FROM requests WHERE state='waiting' ORDER BY created,id")]
            slots=[dict(x) for x in self.db.execute("SELECT * FROM slots WHERE state IN ('free','warm') ORDER BY id")]
            cooldown=self.db.execute("SELECT value FROM metadata WHERE key='admission_until'").fetchone()
            if cooldown and float(cooldown[0])>self.clock():slots=[]
            allocated=set()
            while slots:
                # Re-rank after every allocation so simultaneous requests spread
                # across idle GPUs even before the next nvidia-smi sample arrives.
                s=min(slots,key=self._slot_rank);slots.remove(s)
                options=[]
                for r in waiting:
                    if r['id'] in allocated:continue
                    ts=[t for t in self._eligible(r) if t['kind']=='unreal' and self._memory(s,t)]
                    t=self._choose(r,ts,s)
                    if t:options.append((r,t))
                if not options:
                    # A warm process must not block an otherwise runnable request by consuming memory.
                    if s['state']=='warm' and any(self._eligible(r) for r in waiting):self._command(s,'stop',None,None)
                    continue
                selected=options[0]
                if s['state']=='warm' and s['batch_tasks']<self.batch_tasks and s['batch_seconds']<self.batch_seconds:
                    same=[(r,t) for r,t in options if s['last_owner']==r['service']+':'+r['owner'] and self._can_reuse(s,t)]
                    # Absolute waiting bound prevents low-cost continuations starving others.
                    if same and self.clock()-options[0][0]['created']<self.batch_seconds:selected=same[0]
                r,t=selected;self._allocate(r,t,s);allocated.add(r['id'])
            for r in waiting:
                if r['id'] not in allocated:
                    t=self._choose(r,[t for t in self._eligible(r) if t['kind']=='browser'])
                    if t:self._allocate(r,t)

    def activate(self,service,owner,lease):
        with self.tx():
            l=self._owned(lease,service,owner)
            if l['state'] in ('starting','running'):return l
            if l['state']!='reserved' or self.clock()-l['created']>=self.reserve_seconds:raise ScheduleError('Reservation expired')
            if l['slot'] is None:
                self.db.execute("UPDATE leases SET state='running',ready_at=? WHERE id=?",(self.clock(),lease))
            else:
                s=self._row('slots',l['slot']);t=self.tasks[l['task']]
                action='switch' if self._can_reuse(s,t) else 'replace'
                # Cross-user warm reuse requires transport fencing as well as scene reset certification.
                if s['last_owner']!=service+':'+owner and not t.get('handoff_verified',False):action='replace'
                self.db.execute("UPDATE leases SET state='starting' WHERE id=?",(lease,))
                self._command(s,action,l['task'],lease)
            return self._row('leases',lease)

    def commands(self):
        with self.lock:return [dict(x) for x in self.db.execute("SELECT * FROM commands WHERE state='pending' ORDER BY created,id")]

    def acknowledge(self,command,*,ready=False,stopped=False,error=None,teardown_confirmed=False,reused=None,failure_kind='infrastructure'):
        """Worker acknowledges only after stream fencing, scene ACK and health checks."""
        with self.tx():
            c=self._row('commands',command);s=self._row('slots',c['slot'])
            if c['state']!='pending' or s['generation']!=c['generation']:return False
            if c['action']=='stop':
                if not stopped:return self._quarantine(c,s,error or 'Teardown not confirmed')
                self.db.execute("UPDATE slots SET state='free',task=NULL,lease=NULL,last_owner=NULL,batch_tasks=0,batch_seconds=0,warm_until=NULL WHERE id=?",(s['id'],))
            elif not ready:
                self._end(c['lease'],'technical',error or 'Launch failed')
                if failure_kind=='task':
                    self.db.execute('INSERT INTO faults VALUES(?,1,0) ON CONFLICT(task) DO UPDATE SET count=count+1',(c['target'],))
                    self.db.execute('UPDATE faults SET quarantined=(count>=?) WHERE task=?',(self.failure_limit,c['target']))
                else:
                    old=self.db.execute("SELECT value FROM metadata WHERE key='infra_failures'").fetchone()
                    failures=min(6,int(old[0])+1 if old else 1)
                    for key,value in [('infra_failures',str(failures)),('admission_until',str(self.clock()+min(300,5*2**failures)))]:
                        self.db.execute('INSERT INTO metadata VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,value))
                if not teardown_confirmed:return self._quarantine(c,s,error or 'Launch failed; teardown uncertain')
                self.db.execute("UPDATE slots SET state='free',task=NULL,lease=NULL,last_owner=NULL,batch_tasks=0,batch_seconds=0 WHERE id=?",(s['id'],))
            else:
                self.db.execute("DELETE FROM metadata WHERE key IN ('infra_failures','admission_until')")
                l=self._row('leases',c['lease'])
                if l['state']!='starting':raise ScheduleError('Stale activation')
                same=s['last_owner']==l['service']+':'+l['owner']
                self.db.execute("UPDATE slots SET state='running',task=?,last_owner=?,batch_tasks=?,batch_seconds=? WHERE id=?",(l['task'],l['service']+':'+l['owner'],s['batch_tasks']+1 if same else 1,s['batch_seconds'] if same else 0,s['id']))
                self.db.execute("UPDATE leases SET state='running',ready_at=?,heartbeat=? WHERE id=?",(self.clock(),self.clock(),l['id']))
                if c['action']=='switch' and reused is True:
                    seconds=max(0,self.clock()-c['created'])
                    self.db.execute('INSERT INTO costs VALUES(?,?,?,1) ON CONFLICT(source,target) DO UPDATE SET seconds=.8*seconds+.2*excluded.seconds,samples=samples+1',(c['source'],c['target'],seconds))
            self.db.execute("UPDATE commands SET state='done' WHERE id=?",(command,))
            self._event('command_ack',command=command,ready=ready,stopped=stopped,error=error,reused=reused)
            return True

    def _quarantine(self,c,s,error):
        self.db.execute("UPDATE slots SET state='quarantined',task=COALESCE(?,task) WHERE id=?",(c['target'],s['id']))
        self.db.execute("UPDATE commands SET state='failed' WHERE id=?",(c['id'],))
        self._event('slot_quarantined',slot=s['id'],error=error)
        return False

    def recover_slot(self,slot):
        with self.tx():
            s=self._row('slots',slot)
            if s['state']!='quarantined':raise ScheduleError('Only quarantined slots can be recovered')
            self._command(s,'stop',None,None)

    def restore_task(self,task):
        with self.tx():
            if task not in self.tasks:raise ScheduleError('Unknown task')
            self.db.execute('DELETE FROM faults WHERE task=?',(task,));self._event('task_restored',task=task)

    def _finish(self,l,outcome):
        if l['state']=='ended':return
        if outcome in ('submitted','not_found') and l['state']!='running':raise ScheduleError('Cannot count unexplored work as completed')
        self._end(l['id'],outcome)
        if l['slot'] is not None:
            s=self._row('slots',l['slot'])
            if s['lease']!=l['id']:raise ScheduleError('Slot ownership changed')
            seconds=max(0,self.clock()-l['ready_at']) if l['ready_at'] is not None else 0
            self.db.execute('UPDATE slots SET batch_seconds=batch_seconds+? WHERE id=?',(seconds,s['id']))
            # Revoke the public lease immediately. The worker must fence transport before reusing.
            if s['state']=='running':
                self.db.execute("UPDATE slots SET state='warm',lease=NULL,warm_until=? WHERE id=?",(self.clock()+self.warm_seconds,s['id']))
            else:
                self.db.execute("UPDATE commands SET state='obsolete' WHERE slot=? AND state='pending'",(s['id'],))
                self._command(s,'stop',None,None)
        self._event('finished',lease=l['id'],outcome=outcome)

    def finish(self,service,owner,lease,outcome):
        if outcome not in ('submitted','not_found','skipped','technical','writing','cancelled'):raise ScheduleError('Invalid outcome')
        with self.tx():self._finish(self._owned(lease,service,owner),outcome)

    def complete_report(self,service,owner,lease,outcome):
        """Trusted adapter calls only after durable report submission; no GPU needed."""
        if outcome not in ('submitted','not_found','skipped','technical'):raise ScheduleError('Invalid outcome')
        with self.tx():
            l=self._owned(lease,service,owner)
            if l['outcome']==outcome:return
            if l['state']!='ended' or l['outcome'] not in ('writing','paused','interrupted','cancelled','technical') or l['ready_at'] is None:raise ScheduleError('No completed exploration awaiting a report')
            self.db.execute('UPDATE leases SET outcome=? WHERE id=?',(outcome,lease));self._event('report_completed',lease=lease,outcome=outcome)

    def _expire(self):
        now=self.clock()
        self.db.execute("UPDATE requests SET state='expired' WHERE state='waiting' AND heartbeat<=?",(now-self.heartbeat_seconds,))
        for l in self.db.execute("SELECT * FROM leases WHERE state IN ('reserved','starting','running')").fetchall():
            if l['state']=='reserved':expired=now-l['created']>=self.reserve_seconds
            elif l['state']=='starting':
                command=self.db.execute("SELECT created FROM commands WHERE lease=? AND state='pending'",(l['id'],)).fetchone()
                expired=bool(command and now-command['created']>=self.launch_seconds)
            else:expired=now-l['heartbeat']>=self.heartbeat_seconds or now-l['ready_at']>=self.max_run_seconds
            if expired:self._finish(dict(l),'cancelled')
        for s in self.db.execute("SELECT * FROM slots WHERE state='warm' AND warm_until<=?",(now,)).fetchall():self._command(dict(s),'stop',None,None)

    def status(self,service,owner,request_id):
        with self.lock:
            r=self._row('requests',request_id)
            if (r['service'],r['owner'])!=(service,owner):raise ScheduleError('Request owner mismatch')
            l=self._row('leases',r['lease']) if r['lease'] else None
            ahead=self.db.execute("SELECT count(*) FROM requests WHERE state='waiting' AND (created<? OR (created=? AND id<?))",(r['created'],r['created'],r['id'])).fetchone()[0] if r['state']=='waiting' else None
            return {'request':r['id'],'state':r['state'],'queue_position':ahead+1 if ahead is not None else None,'lease':l}

    def authorize(self,service,owner,lease):
        with self.lock:
            l=self._owned(lease,service,owner)
            if l['state']!='running':raise ScheduleError('Stream lease is not active')
            return {'slot':l['slot'],'task':l['task'],'lease':l['id']}

    def seed_history(self,rows):
        with self.tx():
            for r in rows:
                if r['task'] not in self.tasks or r['outcome'] not in ('submitted','not_found','skipped','technical'):raise ScheduleError('Invalid imported history')
                self.db.execute('INSERT OR IGNORE INTO history VALUES(?,?,?,?,?,?,?)',(r['id'],r['service'],r['owner'],r['cohort'],r['task'],self.tasks[r['task']]['case_key'],r['outcome']))

    def running_slots(self):
        with self.lock:return [dict(r) for r in self.db.execute("SELECT * FROM slots WHERE state='running'")]

    def runtime_failed(self,lease):
        with self.tx():
            l=self._row('leases',lease)
            if l['state']!='running':return
            self._finish(l,'technical')
            if l['slot'] is not None:self._command(self._row('slots',l['slot']),'stop',None,None)
            self._event('runtime_health_failed',lease=lease)

    def capacity(self):
        with self.lock:
            slots=[dict(r) for r in self.db.execute('SELECT * FROM slots')]
            result={'capacity':len(slots),'running':sum(r['state'] not in ('free','warm') for r in slots),
                'warm':sum(r['state']=='warm' for r in slots),'queued':self.db.execute("SELECT count(*) FROM requests WHERE state='waiting'").fetchone()[0]}
            if self.gpu_devices:
                result['gpus']=[{'index':g,'budget_mb':d['memory_mb'],'reserved_mb':self._gpu_reserved(g),
                    'available':self._gpu_sample(g) is not None,
                    'used_mb':(self._gpu_sample(g) or {}).get('used_mb'),
                    'utilization':(self._gpu_sample(g) or {}).get('utilization'),
                    'running':sum(s['state'] not in ('free','warm') and self.slot_gpus[s['id']]==g for s in slots)} for g,d in self.gpu_devices.items()]
            return result

    def resume(self,service,owner,lease):
        with self.tx():
            l=self._owned(lease,service,owner)
            if l['state']=='ended' and l['outcome']=='writing':
                self.db.execute("UPDATE leases SET outcome='paused' WHERE id=?",(lease,))

    def drain(self):
        """Stop admissions before process exit; physical cleanup still requires worker ACKs."""
        with self.tx():
            self.db.execute("UPDATE requests SET state='cancelled' WHERE state='waiting'")
            for l in self.db.execute("SELECT id FROM leases WHERE state!='ended'").fetchall():self._end(l['id'],'interrupted','scheduler draining')
            for row in self.db.execute("SELECT * FROM slots WHERE state!='free'").fetchall():
                s=dict(row)
                self.db.execute("UPDATE commands SET state='obsolete' WHERE slot=? AND state='pending'",(s['id'],))
                self._command(s,'stop',None,None)

    def close(self):
        if hasattr(self,'db'):self.db.close()
        if hasattr(self,'_owner_lock') and not self._owner_lock.closed:self._owner_lock.close()
