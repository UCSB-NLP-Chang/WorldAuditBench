from pathlib import Path
import json,hashlib,subprocess,sqlite3,datetime,sys,time
w=Path('/home/ubuntu/unreal-auditor/indoor-cabinet-range-workspace');svc=w.parent/'review-service';state=svc/'state'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
p=read(w/'out/proof.json');source=Path(p['source_release']);stage=Path(p['stage'])
assert subprocess.check_output(['systemctl','show','urban-review-pilot.service','-p','WorkingDirectory','--value'],text=True).strip()==str(source)
for n,h in p['source_hashes'].items():assert sha(source/n)==h,('Source changed',n)
for n,h in p['state_hashes'].items():assert sha(state/n)==h,('State changed',n)
v=read(w/'out/validation.json');assert v['result']=='PASS';assert read(w/'out/acceptance.json')['result']=='PASS'
for n,h in v['candidate_hashes'].items():assert sha(stage/n)==h,('Candidate changed',n)
b=svc/'backups'/('pre-authorized-h09-cabinet-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S'));b.mkdir(mode=0o700)
with sqlite3.connect('file:'+str(state/'review.sqlite3')+'?mode=ro',uri=True) as db:
 with sqlite3.connect(b/'review.sqlite3') as dst:db.backup(dst)
print('Preflight and backup passed',flush=True)
sys.path.insert(0,str(source));from server import Store
subprocess.run(['sudo','systemctl','stop','urban-review-pilot.service'],check=True)
aux=None
try:
 # Keep only the runtime cleanup endpoint alive while admission stays stopped.
 log=(w/'out/drain-supervisor.log').open('w')
 aux=subprocess.Popen(['python3',str(source/'runtime/mac_supervisor.py'),str(state/'runtime.json')],stdout=log,stderr=subprocess.STDOUT)
 import socket
 port=read(state/'runtime.json')['supervisor_port']
 for attempt in range(50):
  try:
   with socket.create_connection(('127.0.0.1',port),timeout=.2):break
  except OSError:time.sleep(.1)
 assert aux.poll() is None, 'Cleanup supervisor failed to start'
 env=read(state/'service-env.json')
 store=Store(state/'review.sqlite3',read(state/'tasks.json'),mode='external',capacity=3,tokens=json.loads(env['REVIEW_TOKENS_JSON']),runner=json.loads(env['REVIEW_RUNNER_JSON']),build_sha=env['REVIEW_BUILD_SHA256'])
 for attempt in range(60):
  store.tick()
  if store.db.execute("select count(*) from sessions where status in ('queued','starting','ready','resetting','switching','closing')").fetchone()[0]==0:break
  time.sleep(1)
 remaining=store.db.execute("select count(*) from sessions where status in ('queued','starting','ready','resetting','switching','closing')").fetchone()[0];store.db.close();assert remaining==0,('Shutdown pending',remaining)
 aux.terminate();aux.wait(timeout=20);log.close();aux=None
 subprocess.run(['python3',str(w/'scripts/publish.py')],check=True)
except Exception:
 if aux is not None:
  aux.terminate()
  try:aux.wait(timeout=20)
  except subprocess.TimeoutExpired:aux.kill();aux.wait()
 subprocess.run(['sudo','systemctl','start','urban-review-pilot.service'],check=True);raise
