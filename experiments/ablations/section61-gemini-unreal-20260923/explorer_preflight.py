from pathlib import Path
import json,subprocess,os,signal,time
B=Path(__file__).resolve().parent
from batch_reservation import Reservation
r=Reservation('/home/ec2-user/gemini-unreal-nomap-20260919/pinned-production',B/'explorer-preflight-reservation.json',[3])
script='''import sys,json
from pathlib import Path
B=Path('/mnt/auditor-build/experiment-runs/section61-gemini-unreal-20260923');sys.path.insert(0,str(B/'code'))
from harness.vla_ue import P2PClient,small_jpeg_png,launch
p=P2PClient(gpu='3',size='1200M',eager=True)
try:
 raw=Path('/home/ec2-user/vla-recordings/vla-ue-v1/A01/f00000.jpg').read_bytes()
 p.reset();action=p.act(small_jpeg_png(raw),'Explore this place. Walk around and look at everything.')
 assert all(k in action for k in ['keys','buttons','dx','dy']);print('EXPLORER_PASS',json.dumps(action),flush=True)
finally:p.close()
'''
proc=None
try:
 r.acquire()
 env=dict(os.environ,P2P_ROOT='/home/ec2-user/tools/open-p2p',P2P_PY='/home/ec2-user/tools/open-p2p/.venv/bin/python',GA_ICLR=str(B/'code'),HF_HOME='/home/ec2-user/.cache/huggingface',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
 with (B/'explorer-preflight-worker.log').open('x') as log:
  proc=subprocess.Popen([str(B/'code/out/native-agents/venv/bin/python'),'-u','-c',script],cwd=B,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
  rc=proc.wait(timeout=900)
 assert rc==0 and 'EXPLORER_PASS' in (B/'explorer-preflight-worker.log').read_text()
 (B/'explorer-preflight.json').write_text(json.dumps({'passed':True,'time':time.time(),'real_local_model':True,'model':'open-p2p-1.2B','api_calls':0}))
except BaseException as e:
 (B/'explorer-preflight.json').write_text(json.dumps({'passed':False,'time':time.time(),'error':repr(e)}));raise
finally:
 if proc and proc.poll() is None:
  os.killpg(proc.pid,signal.SIGTERM)
  try:proc.wait(timeout=15)
  except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
 r.release()
