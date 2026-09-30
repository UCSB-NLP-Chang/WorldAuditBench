from pathlib import Path
import os,sys,json,math,time
B=Path(__file__).resolve().parent;C=B/'code';sys.path.insert(0,str(C));os.environ['GA_ICLR']=str(C);os.environ['VLA_UE_MAXFPS']='20'
from batch_reservation import Reservation
from harness import vla_ue as v
r=Reservation('/home/ec2-user/gemini-unreal-nomap-20260919/pinned-production',B/'native-preflight-reservation.json',[3]);original=v.TaskBackend.__init__
def init(self,binary,map_name,task,arguments,root,**kw):return original(self,binary,map_name,task,list(arguments)+['-graphicsadapter=3'],root,**kw)
v.TaskBackend.__init__=init
root=B/'native-preflight';root.mkdir();rows=[]
try:
 r.acquire();tasks,profiles=v.load_catalog(B/'02-vla-near/profiles.json')
 for tid in ['A01','U011']:
  backend,map_name,native,prof=v.launch(tid,tasks,profiles,root)
  try:
   state=backend.exchange('reset',map=map_name,task=native,seed=0)
   pos=state.get('position_cm') or state.get('camera_position_cm');yaw=state.get('yaw_degree',state.get('yaw',0))
   pol=prof['policy'];dist=math.hypot(pos[0]-pol['spawn'][0],pos[1]-pol['spawn'][1]);dyaw=abs((yaw-pol['yaw']+180)%360-180)
   ready='AUDITOR_EXPLORATION_READY' in backend.log_text();assert dist<=30 and dyaw<=2 and ready,(tid,dist,dyaw,ready)
   image=backend.png();(root/(tid+'.png')).write_bytes(image)
   rows.append({'task':tid,'passed':True,'start_cm_error':dist,'yaw_error':dyaw,'ready':ready,'build_sha256':prof['build_sha256'],'gpu':3})
  finally:backend.close()
 (B/'native-preflight.json').write_text(json.dumps({'passed':True,'time':time.time(),'tasks':rows,'model_calls':0},indent=2));print(rows)
finally:r.release()
