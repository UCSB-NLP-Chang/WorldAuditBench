from pathlib import Path
import json,copy,subprocess,os,signal,time,math,hashlib,concurrent.futures
w=Path("/home/ubuntu/unreal-auditor/subway-workspace/review-concourse-20260917");policy=w/"out/policy.json";p=json.loads(policy.read_text());e=copy.deepcopy(p["tasks"]["B01"]);e.update(id="S22",case_type="bug",target="Actor_Deco_Fountain_C_2",focus=[-10,5550,700],focus_source="authored waterfall feature");p["tasks"]["S22"]=e;policy.write_text(json.dumps(p,indent=2)+"\n");b=json.loads((w/"out/build.json").read_text());ids=[k for k,e in p["tasks"].items() if e["family"]=="subway" and e["map"].endswith("/Concourse")]
def run(t):
 d=w/"out/validation"/t;d.mkdir(parents=True,exist_ok=True);e=p["tasks"][t]
 cmd=[b["binary"],e["map"]+"?Task="+("baseline" if t=="B01" else t),"-nullrhi","-nosound","-unattended","-AuditorRemoteInput","-AuditorSkipSceneMenu","-AuditorExplorationPolicy="+str(policy),"-AuditorExplorationTask="+t,"-AuditorExplorationReport="+str(d/"native.json"),"-abslog="+str(d/"native.log")]
 q=subprocess.Popen(cmd,stdout=(d/"stdout.log").open("w"),stderr=subprocess.STDOUT,start_new_session=True)
 try:
  for _ in range(240):
   if (d/"native.json").exists() or q.poll() is not None:break
   time.sleep(.25)
  r=json.loads((d/"native.json").read_text());assert r["status"]=="validated" and r["id"]==t and math.dist(r["spawn"],e["spawn"])<.1
  result={"id":t,"status":"PASS"}
 except Exception as exc:result={"id":t,"status":"FAIL","error":str(exc)}
 finally:
  if q.poll() is None:
   os.killpg(q.pid,signal.SIGTERM)
   try:q.wait(timeout=5)
   except subprocess.TimeoutExpired:os.killpg(q.pid,signal.SIGKILL);q.wait()
 print(result,flush=True);return result
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(run,ids))
report={"status":"PASS" if all(r["status"]=="PASS" for r in results) else "FAIL","policy_sha256":hashlib.sha256(policy.read_bytes()).hexdigest(),"binary_sha256":b["binary_sha256"],"tasks":results};(w/"out/validation.json").write_text(json.dumps(report,indent=2));assert report["status"]=="PASS"
