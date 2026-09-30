"""Native frozen-spawn validation for a complete Review-only policy."""
import concurrent.futures,hashlib,json,math,os,pathlib,signal,subprocess,sys,time
root=pathlib.Path(sys.argv[1]);policy=root/'policy.json'
while not (root/'refine-summary.json').exists():time.sleep(1)
p=json.loads(policy.read_text());inventory=json.loads((root/'inventory.json').read_text());assert set(p['tasks'])=={r['id'] for r in inventory}
for row in inventory:
 e=p['tasks'][row['id']];assert e['focus']==row['entry']['focus'] and e['map']==row['entry']['map']
 assert math.dist(e['spawn'][:2],e['focus'][:2])+.1>=row['current_cm']
 for i in [0,1]:assert e['bounds_min'][i]<=row['entry']['bounds_min'][i] and e['bounds_max'][i]>=row['entry']['bounds_max'][i]
 if e.get('revision_exception') is None:
  ref=json.loads((root/'refined'/(row['id']+'.json')).read_text());r=json.loads(pathlib.Path(ref['report_path']).read_text());assert r['status']=='planned' and math.dist(e['spawn'],r['spawn'])<.1;assert len(e['route_to_old_spawn'])>=2

def run(row):
 tid=row['id'];e=p['tasks'][tid];d=root/'validation'/tid;d.mkdir(parents=True,exist_ok=True);rfile=d/'native.json'
 cmd=[row['profile']['binary'],e['map']+'?Task='+('baseline' if e['case_type']!='bug' else tid),'-nullrhi','-nosound','-unattended','-AuditorRemoteInput','-AuditorSkipSceneMenu','-AuditorExplorationPolicy='+str(policy),'-AuditorExplorationTask='+tid,'-AuditorExplorationReport='+str(rfile),'-abslog='+str(d/'native.log'),'-UserDir='+str(d/'userdata'),'-NoSaveConfig','-ExecCmds=t.MaxFPS 15']
 with (d/'stdout.log').open('w') as log:
  q=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);start=time.monotonic()
  try:
   while not rfile.exists() and q.poll() is None and time.monotonic()-start<60:time.sleep(.15)
   r=json.loads(rfile.read_text());assert r['id']==tid and r['status']=='validated';assert math.dist(r['spawn'],e['spawn'])<.1 and abs(r['yaw']-e['yaw'])<.1;assert r['bounds_min']==e['bounds_min'] and r['bounds_max']==e['bounds_max'];out={'id':tid,'status':'PASS','distance_cm':r['distance_cm'],'old_distance_cm':r['old_distance_cm']}
  except Exception as exc:out={'id':tid,'status':'FAIL','error':str(exc)}
  finally:
   if q.poll() is None:
    os.killpg(q.pid,signal.SIGTERM)
    try:q.wait(timeout=5)
    except subprocess.TimeoutExpired:os.killpg(q.pid,signal.SIGKILL);q.wait()
 print(json.dumps(out),flush=True);return out
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(run,inventory))
report={'status':'PASS' if all(r['status']=='PASS' for r in results) else 'FAIL','tasks':results,'policy_sha256':hashlib.sha256(policy.read_bytes()).hexdigest()};(root/'validation.json').write_text(json.dumps(report,indent=2));print('VALIDATED',len(results),report['status'],flush=True)
