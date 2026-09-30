from pathlib import Path
import json,hashlib,subprocess,os,sys,time
B=Path(__file__).resolve().parent;S=json.loads((B/'selection.json').read_text());rows=[]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
for t in S['tasks']:
 source=Path(t['source_remote']);r=source/'cases'/t['id']/'run';m=json.loads((r/'episode/meta.json').read_text());lc=json.loads((r/'launch.json').read_text());cfg=json.loads((r/'episode-config.json').read_text());health=json.loads((r.resolve().parent/'health.json').read_text());calls=[json.loads(l) for l in (r/'episode/mcp-calls.jsonl').read_text().splitlines()]
 assert lc['client']=='gemini' and lc['model_requested']=='gemini-3.8-flash' and lc['reasoning_requested']=='medium' and lc['native_exit_code']==0 and lc['cli_version']=='0.34.0'
 assert m['status']=='completed' and m['actions_used']==40 and m['done_summary'] and m['icl_complete']
 assert m['backend']['minimap_policy']=='masked-before-archive-v1' and cfg['observation']=='on-demand' and cfg['max_tool_calls']==400 and cfg['max_actions']==40 and cfg['seed']==0
 read=next(i for i,c in enumerate(calls) if c['tool']=='read_example' and not c['is_error'] and c['images']);obs=next(i for i,c in enumerate(calls) if c['tool']=='observe' and not c['is_error']);assert read<obs
 for k in ['build_sha256','policy_sha256']:assert health[k]==t[k],(t['id'],k)
 code=source/'code';impl=hashlib.sha256(b'\n'.join(p.read_bytes() for p in sorted((code/'auditor/mcp_agent').glob('*.py')))).hexdigest();assert impl==lc['mcp_implementation_sha256'],t['id']
 assert sha(r/'after-agent.py')==sha(code/'scripts/native-agents/after_agent.py'),(t['id'],'hook changed')
 ex=json.loads((r/'icl/context.json').read_text())['messages'][0]['content'][0]['text'];definition='\n\n'.join(ex.split('\n\n')[:2])
 run=B/'preflight'/t['id'];instruction=cfg['instruction']
 cmd=[str(code/'out/native-agents/venv/bin/python'),str(B/'launch_no_icl.py'),'--source-batch',str(source),'gemini','--no-icl','--environment','unreal-http','--env-url','http://127.0.0.1:50120','--task',t['id'],'--task-catalog',str(source/'task-subcategories.json'),'--scene-catalog',str(source/'task-scenes.json'),'--model','gemini-3.8-flash','--gemini-thinking','medium','--max-actions','40','--observation','on-demand','--run-dir',str(run),'--instruction',instruction,'--require-full-budget','--dry-run','--gemini-auth','gemini-api-key']
 p=subprocess.run(cmd,capture_output=True,text=True,timeout=30)
 assert p.returncode==0,(t['id'],p.stdout[-1000:],p.stderr[-1000:])
 now=json.loads((run/'episode-config.json').read_text());newlaunch=json.loads((run/'launch.json').read_text());newsettings=json.loads((run/'gemini-settings.json').read_text());oldsettings=json.loads((r/'gemini-settings.json').read_text())
 for k in ['environment','task','max_actions','max_tool_calls','require_full_budget','seed','observation','scene_description','allow_icl_overlap']:assert now[k]==cfg[k],(t['id'],k)
 for k in ['model','tools','mcp','security','context','modelConfigs','hooksConfig']:assert newsettings[k]==oldsettings[k],(t['id'],k)
 assert newlaunch['tools']==lc['tools'] and newlaunch['mcp_implementation_sha256']==lc['mcp_implementation_sha256'] and newlaunch['upstream_revision']==lc['upstream_revision']
 assert now['icl']=={'enabled':False} and now['icl_directory'] is None and not (run/'icl').exists()
 assert now['subcategory'] is None and now['instruction']==cfg['instruction']
 prompt=(run/'prompt.txt').read_text();assert 'specific subcategory' not in prompt and definition not in prompt
 assert 'zero-shot run with no ICL examples' in prompt
 rows.append({'id':t['id'],'passed':True,'reference_run':str(r.resolve()),'reference_launch_sha256':sha(r/'launch.json'),'reference_meta_sha256':sha(r/'episode/meta.json'),'reference_settings_sha256':sha(r/'gemini-settings.json'),'build_sha256':t['build_sha256'],'policy_sha256':t['policy_sha256'],'mcp_implementation_sha256':impl,'dry_protocol_sha256':newlaunch['protocol_sha256'],'loop_detection':not newsettings['model'].get('disableLoopDetection',False)})
 print(t['id'],'passed',flush=True)
key=Path('/home/ec2-user/gemini-medieval-20260919/.gemini-api-key')
a={'passed':True,'time':time.time(),'tasks':rows,'credential_sha256':sha(key),'credential_source':'Same explicit private Gemini API key path as the original authorized Gemini experiment; no shared OAuth fallback','sampling_sha256':S['sampled_ids_sha256']}
(B/'preflight.json').write_text(json.dumps(a,indent=2));print('ALL 126 PAIRED PROTOCOL CHECKS PASSED')
