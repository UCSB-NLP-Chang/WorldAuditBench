"""Single-worker command executor; state transitions stay in the scheduler journal."""
import hashlib
import time
from .delivery import request_json

class SupervisorDriver:
    def __init__(self,config,tasks,*,rpc=request_json,fence=None):
        self.config=config;self.tasks=tasks;self.rpc=rpc;self.fence=fence;self.pending={}
        if not config.get('namespace'):raise ValueError('A stable, exclusive supervisor namespace is required')
        self.same_owner_reuse=config.get('same_owner_reuse_verified') is True
        if self.same_owner_reuse and any(t.get('handoff_verified') for t in tasks.values()):raise ValueError('Unfenced cross-owner reuse forbidden')
        self.fallback=next((t['map'] for t in tasks.values() if t['kind']=='unreal'),None)
        if not self.fallback:raise ValueError('At least one Unreal profile required')

    def call(self,op,c,task):
        sid=hashlib.sha256((self.config['namespace']+':'+str(c['slot'])).encode()).hexdigest()[:32]
        return self.rpc(self.config['supervisor_url']+'/runtime',{'operation':op,'session_id':sid,
            'map':self.tasks[task]['map'] if task else self.fallback,'slot':c['slot']},self.config['secret'],timeout=15)

    def step(self,c):
        if c['action']=='stop':
            return {'stopped':self.call('stop',c,c['source']).get('stopped') is True}
        target=c['target']
        try:
            if c['id'] not in self.pending:
                reuse=c['action']=='switch' and (self.fence is not None or self.same_owner_reuse) and c['source'] is not None
                # Same-map supervisor switch is a no-op, not a certified reset.
                reuse=reuse and self.tasks[c['source']].get('runtime_map',self.tasks[c['source']]['map'])!=self.tasks[target].get('runtime_map',self.tasks[target]['map'])
                if reuse:
                    if self.fence:self.fence(c['slot'])
                else:
                    if not self.call('stop',c,c['source']) .get('stopped'):
                        return {'error':'Previous process teardown unconfirmed','teardown_confirmed':False}
                self.pending[c['id']]=reuse
                result=self.call('switch' if reuse else 'start',c,target)
            else:result=self.call('status',c,target)
            if result.get('ready') is True:
                reused=self.pending.pop(c['id'],False);return {'ready':True,'reused':reused}
            if result.get('game_running') is False:raise RuntimeError('Runtime exited')
            return None
        except Exception:
            self.pending.pop(c['id'],None)
            try:stopped=self.call('stop',c,target).get('stopped') is True
            except Exception:stopped=False
            return {'error':'Runtime operation failed','teardown_confirmed':stopped}


class Worker:
    def __init__(self,scheduler,driver):self.scheduler=scheduler;self.driver=driver;self.checked={};self.unhealthy={}
    def tick(self):
        self.scheduler.dispatch()
        if isinstance(self.driver,SupervisorDriver):
            now=time.monotonic()
            for slot in self.scheduler.running_slots():
                if now-self.checked.get(slot['lease'],0)<5:continue
                self.checked[slot['lease']]=now
                try:
                    health=self.driver.call('status',dict(slot=slot['id']),slot['task'])
                    ok=health.get('ready') is True
                except Exception:ok=False
                count=0 if ok else self.unhealthy.get(slot['lease'],0)+1
                self.unhealthy[slot['lease']]=count
                if count>=3:self.scheduler.runtime_failed(slot['lease'])
        commands=self.scheduler.commands()
        if isinstance(getattr(self.driver,'pending',None),dict):
            active={c['id'] for c in commands}
            for key in list(self.driver.pending):
                if key not in active:self.driver.pending.pop(key,None)
        for command in commands:
            # Call serially; never race start, switch and teardown on one slot.
            try:result=self.driver.step(command)
            except Exception:result={'error':'Worker operation failed'}
            if result is not None:self.scheduler.acknowledge(command['id'],**result)
        self.scheduler.dispatch()

