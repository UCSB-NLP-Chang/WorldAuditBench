"""Bounded FIFO leases: one visitor controls one Unreal instance at a time."""
import secrets, time

class Sessions:
    def __init__(self, limit=16, idle=45, duration=600, clock=time.monotonic):
        self.entries={}; self.limit=limit; self.idle=idle; self.duration=duration; self.clock=clock

    def create(self, case):
        if len(self.entries)>=self.limit: raise ValueError('The queue is full. Please try again shortly.')
        id=secrets.token_hex(16)
        self.entries[id]={'id':id,'token':secrets.token_urlsafe(32),'case':case,
            'heartbeat':self.clock(),'started':None,'state':'queued'}
        return self.entries[id]

    def owner(self,id,token):
        item=self.entries.get(id)
        if not item or not secrets.compare_digest(item['token'],token): raise PermissionError('Session expired. Start a new exploration.')
        return item

    def expired(self):
        now=self.clock()
        return [s for s in self.entries.values() if now-s['heartbeat']>self.idle or
                (s['started'] is not None and now-s['started']>self.duration)]

    def public(self,s):
        waiting=[x['id'] for x in self.entries.values() if x['state']=='queued']
        return {'id':s['id'],'case_id':s['case']['id'],'state':s['state'],
            'position':waiting.index(s['id'])+1 if s['id'] in waiting else 0,
            'seconds_left':max(0,int(self.duration-(self.clock()-s['started']))) if s['started'] is not None else None}
