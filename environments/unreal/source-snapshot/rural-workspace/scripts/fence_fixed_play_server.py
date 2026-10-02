"""Private, loopback-only Pixel Streaming QA without touching review sessions."""
from pathlib import Path
import json,sys,subprocess,uuid,time
from http.server import BaseHTTPRequestHandler,HTTPServer
root=Path('/home/ubuntu/unreal-auditor');work=root/'rural-workspace';out=work/'out/fence-v7/play';out.mkdir(parents=True,exist_ok=True)
release=subprocess.check_output(['systemctl','show','urban-review-pilot.service','-p','WorkingDirectory','--value'],text=True).strip();sys.path.insert(0,release+'/runtime')
from mac_supervisor import Supervisor
c=json.loads((root/'review-service/state/runtime.json').read_text());c.update(capacity=1,state_dir=str(out/'runtime'),streamer_port=18888,player_port=18080,sfu_port=18889)
c['manifest']=release+'/tasks.json'
for p in c['launch_profiles'].values():
 if p.get('family')=='rural':p['binary']=str(work/'dist/rural-linux-v7/Linux/RuralAustralia/Binaries/Linux/RuralAustralia');p['extra_args']=['-AuditorReviewDiagnostics']
sup=Supervisor(c);sid=uuid.uuid4().hex;map='/Game/Auditor/RuralAustralia/RoadBend'
sup.run(dict(operation='start',session_id=sid,map=map+'?Task=R04',slot=0));ipc=out/'runtime'/sid/'review-ipc'
def request(**fields):
 id=uuid.uuid4().hex;ipc.mkdir(exist_ok=True);p=ipc/'command.tmp';p.write_text(json.dumps(dict(request_id=id,**fields)));p.replace(ipc/'command.json')
 for _ in range(650):
  try:
   d=json.loads((ipc/'response.json').read_text())
   if d['request_id']==id and d['status']=='ready':return d
  except (FileNotFoundError,ValueError):pass
  time.sleep(.1)
 raise RuntimeError('IPC timeout')
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  try:
   if self.path=='/snapshot':d=request(action='snapshot')
   elif self.path.startswith('/switch/'):
    task=self.path.split('/')[-1];assert task in ('baseline','R02','R03','R04','R05');d=request(action='switch',map=map,task=task)
   else:raise ValueError('Unknown route')
   b=json.dumps(d).encode();self.send_response(200)
  except Exception as e:b=json.dumps({'error':str(e)}).encode();self.send_response(500)
  self.send_header('Content-Type','application/json');self.send_header('Content-Length',len(b));self.end_headers();self.wfile.write(b)
server=HTTPServer(('127.0.0.1',18081),Handler)
print('PRIVATE_VARIETY_PLAY_READY',sid,flush=True)
try:server.serve_forever()
finally:server.server_close();sup.close()
