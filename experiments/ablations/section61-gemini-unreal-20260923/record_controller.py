from pathlib import Path
import sys,os,json,time,subprocess,signal
B=Path(__file__).resolve().parent;P=B/sys.argv[1]
from batch_reservation import Reservation
assert not (B/'STOP.json').exists() and not (P/'STOP.json').exists()
assert json.loads((B/'recording-preflight.json').read_text())['passed']
# Never acquire GPUs held by another experiment or a human session.
reservation=Reservation('/home/ec2-user/gemini-unreal-nomap-20260919/pinned-production',P/'reservation.json',[0,1,2,3])
procs=[];stopping=False
def stop(*_):
 global stopping
 stopping=True
for sig in [signal.SIGTERM,signal.SIGINT]:signal.signal(sig,stop)
try:
 assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip(),'GPUs are not idle'
 reservation.acquire()
 with (P/'recording-admission.consumed').open('x') as f:f.write(str(os.getpid()))
 for gpu in range(4):
  log=(P/f'worker-{gpu}.log').open('x')
  p=subprocess.Popen([str(B/'code/out/native-agents/venv/bin/python'),'-u',str(B/'record_worker.py'),P.name,str(gpu)],cwd=B,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);procs.append(p)
  time.sleep(2)
 while any(p.poll() is None for p in procs):
  if stopping or (B/'STOP.json').exists() or (P/'STOP.json').exists():raise RuntimeError('Recording stopped')
  for gpu,p in enumerate(procs):
   if p.poll() not in [None,0]:raise RuntimeError('Recording worker failed: '+str(gpu))
   f=P/f'worker-{gpu}.json'
   if f.exists():
    s=json.loads(f.read_text());start=s.get('started_at',s.get('time',time.time()))
    if s['status'] not in ['completed','stopped'] and time.time()-start>5400:raise TimeoutError('90-minute recording infrastructure limit')
  time.sleep(5)
 assert all(p.returncode==0 for p in procs)
 tasks=json.loads((P/'profiles.json').read_text())['tasks']
 assert len(tasks)==126 and all((P/'recordings'/t/'verification.json').exists() for t in tasks)
 (P/'recordings.finished.json').write_text(json.dumps({'time':time.time(),'completed':126,'verified':126}))
except BaseException as e:
 (P/'STOP.json').write_text(json.dumps({'time':time.time(),'reason':repr(e)}));raise
finally:
 for p in procs:
  if p.poll() is None:
   os.killpg(p.pid,signal.SIGCONT);os.killpg(p.pid,signal.SIGTERM)
 for p in procs:
  try:p.wait(timeout=30)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
 # Games own separate process groups; verify this phase has no leftover engine.
 for proc in Path('/proc').iterdir():
  if not proc.name.isdigit():continue
  try:raw=(proc/'cmdline').read_bytes()
  except OSError:continue
  if ('-AuditorIPC='+str(P/'ue-state')).encode() in raw:
   try:os.kill(int(proc.name),signal.SIGCONT);os.kill(int(proc.name),signal.SIGTERM)
   except ProcessLookupError:pass
 time.sleep(2)
 for proc in Path('/proc').iterdir():
  if not proc.name.isdigit():continue
  try:raw=(proc/'cmdline').read_bytes()
  except OSError:continue
  if ('-AuditorIPC='+str(P/'ue-state')).encode() in raw:
   try:os.kill(int(proc.name),signal.SIGKILL)
   except ProcessLookupError:pass
 reservation.release()
