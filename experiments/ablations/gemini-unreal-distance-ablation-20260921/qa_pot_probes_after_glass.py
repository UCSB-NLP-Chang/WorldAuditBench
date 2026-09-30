from pathlib import Path
import json,time,sys,os,subprocess,fcntl
B=Path(__file__).resolve().parent;sys.path.insert(0,str(B.parent/'gemini-unreal-icl-ablation-20260921/code'))
from batch_reservation import Reservation
def read(p):
 try:return json.loads(p.read_text())
 except (OSError,ValueError):return {}
def state(s,**kw):(B/'pot-probe-handoff.json').write_text(json.dumps(dict(time=time.time(),pid=os.getpid(),status=s,model_calls=0,ready_for_model=False,**kw),indent=2))
lock=(B/'pot-probe-handoff.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
while True:
 f=read(B/'glass-probe.finished');r=read(B/'glass-probe-reservation.json');state('waiting_trigger_release',processed=f.get('processed'),reservation=r.get('status'))
 if f.get('processed')==3 and not f.get('stopped') and r.get('status')=='released':break
 time.sleep(10)
r=Reservation('/home/ec2-user/unreal-production',B/'pot-probe-reservation.json',[0,1,2,3]);r.acquire()
try:
 state('native_final_probes_running')
 subprocess.run([sys.executable,'-u',str(B/'qa_pot_probes.py')],check=True)
 state('native_probes_finished_requires_visual_review')
finally:r.release()
