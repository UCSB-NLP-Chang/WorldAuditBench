"""Loopback-only shared resource scheduler API for authenticated service adapters.

Not a public browser endpoint. Review and Explore must both use this coordinator
before enabling it against shared physical GPU slots.
"""
import argparse
import hmac
import json
import pathlib
import threading
import signal
import time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from .cost_scheduler import Scheduler,ScheduleError
from .scheduler_worker import SupervisorDriver,Worker

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,status,data):
        body=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_POST(self):
        try:
            if self.path!='/scheduler':return self.reply(404,{'error':'Not found'})
            credential=self.headers.get('Authorization','').removeprefix('Bearer ')
            matches=[(name,c) for name,c in self.server.clients.items() if hmac.compare_digest(credential,c['token'])]
            if len(matches)!=1:return self.reply(403,{'error':'Unauthorized'})
            service,client=matches[0]
            n=int(self.headers.get('Content-Length','0'))
            if not 0<n<=262144:raise ScheduleError('Invalid request size')
            data=json.loads(self.rfile.read(n));owner=data.get('owner');op=data.get('operation')
            if not isinstance(owner,str) or not 1<=len(owner)<=200:raise ScheduleError('Invalid owner')
            s=self.server.scheduler
            if op=='capacity':result=s.capacity()
            elif op=='resume':result=s.resume(service,owner,data['lease'])
            elif op=='request':
                tasks=data['candidates']
                if not isinstance(tasks,list) or not tasks or not all(isinstance(t,str) and t in client['tasks'] for t in tasks):raise ScheduleError('Task access denied')
                result=s.request(service,owner,tasks,request_id=service+':'+data['request_id'],cohort=data.get('cohort','human'),mode=data.get('mode','auto'))
            elif op in ('status','heartbeat','cancel'):
                rid=data['request_id']
                result=getattr(s,op)(service,owner,rid)
            elif op in ('activate','authorize'):result=getattr(s,op)(service,owner,data['lease'])
            elif op in ('finish','complete_report'):result=getattr(s,op)(service,owner,data['lease'],data['outcome'])
            else:raise ScheduleError('Unknown operation')
            self.reply(200,{'result':result})
        except (ScheduleError,KeyError,ValueError,TypeError):self.reply(409,{'error':'Invalid request or conflicting scheduler state'})
        except Exception:self.reply(503,{'error':'Scheduler unavailable'})

def make_server(scheduler,clients,port=0):
    tokens=[c.get('token') for c in clients.values()]
    if not tokens or any(not isinstance(t,str) or len(t)<32 for t in tokens) or len(set(tokens))!=len(tokens):raise ValueError('Distinct strong per-service credentials required')
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.scheduler=scheduler;server.clients=clients;return server

class Client:
    def __init__(self,url,token,*,rpc=None):
        from .delivery import request_json
        self.url=url;self.token=token;self.rpc=rpc or request_json
    def call(self,operation,owner,**data):
        return self.rpc(self.url+'/scheduler',dict(data,operation=operation,owner=owner),self.token,timeout=20)['result']

def main():
    p=argparse.ArgumentParser();p.add_argument('config');a=p.parse_args();c=json.loads(pathlib.Path(a.config).read_text())
    if c.get('shared_pool_exclusive') is not True:raise ValueError('Both services must relinquish independent control of these GPU slots before enablement')
    if c['limits'].get('gpu_devices'):
        runtime=json.loads(pathlib.Path(c['runtime_config']).read_text())
        if runtime.get('capacity')!=c['limits']['slots'] or runtime.get('slot_gpus')!=c['limits']['slot_gpus']:
            raise ValueError('Scheduler and runtime GPU topology must match')
    scheduler=Scheduler(c['database'],c['tasks'],**c['limits'])
    if c.get('history_file'):scheduler.seed_history(json.loads(pathlib.Path(c['history_file']).read_text()))
    fence=None
    if c.get('transport_fence'):
        from .delivery import request_json
        def fence(slot):
            f=c['transport_fence'];result=request_json(f['url'],{'slot':slot},f['token'],timeout=15)
            if result.get('fenced') is not True:raise RuntimeError('Transport fence not confirmed')
    driver=SupervisorDriver(c['supervisor'],scheduler.tasks,fence=fence)
    worker=Worker(scheduler,driver);stop=threading.Event()
    server=make_server(scheduler,c['clients'],c['port'])
    def loop():
        next_gpu_sample=0
        while not stop.wait(.5):
            try:
                if scheduler.gpu_devices and time.monotonic()>=next_gpu_sample:
                    from .gpu_resources import sample_gpus
                    try:scheduler.update_gpus(sample_gpus())
                    except Exception:scheduler.update_gpus({})
                    next_gpu_sample=time.monotonic()+2
                worker.tick()
            except Exception:
                import traceback;traceback.print_exc()
    thread=threading.Thread(target=loop,daemon=True);thread.start()
    def terminate(*args):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,terminate)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        server.server_close();stop.set();thread.join(timeout=30)
        if not thread.is_alive():
            scheduler.drain();deadline=time.monotonic()+30
            while scheduler.commands() and time.monotonic()<deadline:
                worker.tick();time.sleep(.2)
            scheduler.close()
if __name__=='__main__':main()
