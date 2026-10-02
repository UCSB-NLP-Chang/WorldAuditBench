from pathlib import Path
import sys,json,ast,subprocess,hashlib,concurrent.futures,time,shutil,os
B=Path(__file__).resolve().parent;sys.path.insert(0,str(B));import coordinator as m
from repeat_admission import digest
S=m.S

def check(t,run):
 ref=Path(t['reference_run']);cfg=json.loads((run/'episode-config.json').read_text());old=json.loads((ref/'episode-config.json').read_text())
 assert (run/'prompt.txt').read_bytes()==(ref/'prompt.txt').read_bytes()
 for k in ['max_actions','max_tool_calls','require_full_budget','seed','instruction','scene_description','icl']:assert cfg[k]==old[k],(t['id'],k)
 settings=json.loads((run/'gemini-settings.json').read_text());baseline=json.loads((ref/'gemini-settings.json').read_text())
 for k in ['model','tools','mcp','security','context','modelConfigs','hooksConfig']:assert settings[k]==baseline[k],(t['id'],k)
 assert digest(run/'after-agent.py')==digest(ref/'after-agent.py')
 assert not (run/'native-events.jsonl').exists()
 return {'id':t['id'],'passed':True,'prompt_sha256':digest(run/'prompt.txt'),'hook_sha256':digest(run/'after-agent.py'),'model_calls':0}

def main():
 assert len(S['tasks'])==42 and not (B/'admission.consumed.json').exists()
 assert shutil.which('codex'),'Real judge CLI missing'
 old=Path('/mnt/auditor-build/experiment-runs/gemini-unreal-multibug-20260922')
 for t in S['tasks']:
  if t['condition']!='A':
   assert digest(Path(t['composition_spec_absolute']))==t['composition_sha256']
 tree=ast.parse((B/'coordinator.py').read_text());fun=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='attempt')
 assignments=[x for x in ast.walk(fun) if isinstance(x,ast.Assign) and any(isinstance(v,ast.Name) and v.id in ['instruction','cmd'] for v in x.targets)]
 code=compile(ast.Module(body=assignments,type_ignores=[]),'<actual coordinator native command>','exec')
 def dry(t):
  job=B/'preflight-dry'/t['id'];job.mkdir(parents=True,exist_ok=False)
  c=Path(t['source_remote'])/'code';ns={'t':t,'job':job,'B':B,'C':c,'PYTHON':c/'out/native-agents/venv/bin/python','OLD':m.OLD,'task_id':t['task_id'],'url':'http://127.0.0.1:1','json':json,'Path':Path}
  exec(code,ns);cmd=ns['cmd']+['--dry-run']
  r=subprocess.run(cmd,cwd=c,env=m.ENV,capture_output=True,text=True,timeout=180)
  assert r.returncode==0,(t['id'],r.stderr[-500:]);return check(t,job/'run')
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:dry_results=list(pool.map(dry,S['tasks']))
 print('42 native dry configurations passed; zero model calls',flush=True)
 result={'time':time.time(),'passed':True,'model_calls':0,'dry':dry_results,'native_evidence':'See separately validated native QA and assistant image review'}
 (B/'preflight.json').write_text(json.dumps(result,indent=2)+'\n');print('42 exact configuration/prompt/ICL/hook dry runs passed; zero model calls',flush=True)
 m.JUDGE_POOL.shutdown(wait=True)
if __name__=='__main__':main()
