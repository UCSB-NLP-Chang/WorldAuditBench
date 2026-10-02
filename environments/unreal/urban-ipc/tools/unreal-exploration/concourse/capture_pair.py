from pathlib import Path
import json,subprocess,time,os,signal,shutil
w=Path("/home/ubuntu/unreal-auditor/subway-workspace/review-concourse-20260917");root=Path("/home/ubuntu/unreal-auditor/exploration-v2-20260917");build=json.loads((w/"out/build.json").read_text());reports=[]
for case,task in [("normal","B01"),("bug","S22")]:
 for view,spawn,yaw in [("front",[0,5100,512.7],90),("back",[0,5900,677.853],-90)]:
  d=w/"out"/(case+"-"+view);d.mkdir(exist_ok=True);policy=json.loads((root/"policy.json").read_text());e=dict(policy["tasks"]["B01"]);e.update(id=task,case_type="baseline" if task=="B01" else "bug",spawn=spawn,yaw=yaw,bounds_min=[-1650,1850,-150],bounds_max=[1650,6250,1050]);policy["tasks"][task]=e;(d/"policy.json").write_text(json.dumps(policy))
  cmd=[build["binary"],"/Game/Auditor/Subway/Concourse?Task="+("baseline" if task=="B01" else task),"-RenderOffscreen","-windowed","-ResX=1280","-ResY=720","-nosound","-unattended","-AuditorServe","-AuditorIPC="+str(d),"-AuditorExplorationPolicy="+str(d/"policy.json"),"-AuditorExplorationTask="+task,"-AuditorExplorationReport="+str(d/"validation.json"),"-abslog="+str(d/"native.log"),"-graphicsadapter=0","-vulkan","-sm6"]
  p=subprocess.Popen(cmd,stdout=(d/"stdout.log").open("w"),stderr=subprocess.STDOUT,start_new_session=True)
  try:
   for _ in range(600):
    if (d/"observation.png").exists():break
    if p.poll() is not None:raise RuntimeError("Native process exited: "+str(d))
    time.sleep(.25)
   assert (d/"observation.png").exists();reports.append({"case":case,"view":view,"status":"PASS","image":str(d/"observation.png")});print(case,view,"PASS",flush=True)
  finally:
   if p.poll() is None:
    os.killpg(p.pid,signal.SIGTERM)
    try:p.wait(timeout=10)
    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
(w/"out/pair-captures.json").write_text(json.dumps(reports,indent=2))
