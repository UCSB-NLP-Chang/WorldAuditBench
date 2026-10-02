"""Dry-run all distance launches against original WITH-ICL settings; no GPU or model call."""
from pathlib import Path
import json,hashlib,subprocess,time
B=Path(__file__).resolve().parent;S=json.loads((B/'episodes-selection.json').read_text());rows=[]
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for t in S['tasks']:
 ref=Path(t['reference_run']);cfg=read(ref/'episode-config.json');lc=read(ref/'launch.json');code=Path(t['source_remote'])/'code';run=B/'preflight'/t['id'];row={'id':t['id'],'passed':False}
 try:
  args=[str(code/'out/native-agents/venv/bin/python'),str(B/'launch_distance.py'),'--source-batch',t['source_remote'],'gemini','--icl-dir',str(ref/'icl'),'--environment','unreal-http','--env-url','http://127.0.0.1:50120','--task',t['task_id'],'--task-catalog',str(Path(t['source_remote'])/'task-subcategories.json'),'--scene-catalog',str(Path(t['source_remote'])/'task-scenes.json'),'--model','gemini-3.8-flash','--gemini-thinking','medium','--max-actions','40','--observation','on-demand','--run-dir',str(run),'--instruction',cfg['instruction'],'--require-full-budget','--dry-run','--gemini-auth','gemini-api-key']
  if not (run/'launch.json').exists():
   p=subprocess.run(args,capture_output=True,text=True,timeout=40);assert p.returncode==0,p.stderr[-1600:]
  now=read(run/'episode-config.json');launch=read(run/'launch.json');oldsettings=read(ref/'gemini-settings.json');newsettings=read(run/'gemini-settings.json')
  for k in ['task','max_actions','max_tool_calls','require_full_budget','seed','observation','scene_description','allow_icl_overlap','instruction','icl','subcategory']:assert now[k]==cfg[k],k
  for k in ['model','tools','mcp','security','context','modelConfigs','hooksConfig']:assert newsettings[k]==oldsettings[k],k
  for k in ['model_requested','reasoning_requested','tools','upstream_revision','mcp_implementation_sha256','prompt_sha256']:assert launch[k]==lc[k],k
  assert now['icl']['enabled']
  production=Path(t['private_production']);profiles=[]
  for name in ['audit/runtime.json','shared/runtime-prod.json']:
   for p in read(production/name)['launch_profiles'].values():
    if p.get('build_sha256')==t['build_sha256'] and '-AuditorExplorationTask='+t['task_id'] in p.get('extra_args',[]):
     if p not in profiles:profiles.append(p)
  assert len(profiles)==1,(t['id'],'profile ambiguous')
  paths=[Path(x.split('=',1)[1]) for x in profiles[0]['extra_args'] if x.startswith('-AuditorExplorationPolicy=')];assert len(paths)==1 and sha(paths[0])==t['policy_sha256']
  row.update(passed=True,policy_sha256=t['policy_sha256'],build_sha256=t['build_sha256'],prompt_sha256=launch['prompt_sha256'],icl_sha256=now['icl']['sha256'],loop_detection=not newsettings['model'].get('disableLoopDetection',False))
 except Exception as exc:row['error']=str(exc)
 rows.append(row);print(t['id'],row['passed'],row.get('error',''),flush=True)
 result={'updated_at':time.time(),'passed':len(rows)==len(S['tasks']) and all(r['passed'] for r in rows),'processed':len(rows),'tasks':rows,'credential_sha256':read(B.parent/'gemini-unreal-icl-ablation-20260921/preflight.json')['credential_sha256'],'model_calls':0,'gpu_used':False,'ready_for_model':False,'remaining_gate':'Rendered traversal, target visibility and trigger-state QA'}
 q=B/'preflight.json.tmp';q.write_text(json.dumps(result,indent=2));q.replace(B/'preflight.json')
