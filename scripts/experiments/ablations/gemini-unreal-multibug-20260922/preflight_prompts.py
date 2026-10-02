"""Prepare all anchor configurations with --dry-run; never invoke a model."""
from pathlib import Path
import hashlib,json,os,subprocess,time
B=Path(__file__).resolve().parent
OLD=Path('/home/ec2-user/gemini-medieval-20260919')
env={**os.environ,'PATH':str(OLD/'node-v22.23.2-linux-x64/bin')+':'+os.environ['PATH']}
for key in ['OPENAI_API_KEY','ANTHROPIC_API_KEY','OPENROUTER_API_KEY','GOOGLE_API_KEY','GEMINI_API_KEY','GOOGLE_APPLICATION_CREDENTIALS']:env.pop(key,None)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 dest=B/'prompt-preflight-v2';dest.mkdir(exist_ok=False)
 results=[]
 for t in json.loads((B/'candidate-anchors.json').read_text())['tasks']:
  source=Path(t['source_remote']);ref=(source/'cases'/t['id']/'run').resolve();episode=json.loads((ref/'episode-config.json').read_text());run=dest/t['id']
  cmd=[str(source/'code/out/native-agents/venv/bin/python'),str(B/'launch_composition.py'),'--source-batch',str(source),'gemini','--icl-dir',str(ref/'icl'),'--environment','unreal-http','--env-url','http://127.0.0.1:51920','--task',t['id'],'--task-catalog',str(source/'task-subcategories.json'),'--scene-catalog',str(source/'task-scenes.json'),'--model','gemini-3.8-flash','--gemini-thinking','medium','--max-actions','40','--max-tool-calls','400','--observation','on-demand','--gemini-auth','gemini-api-key','--gemini-api-key-file',str(OLD/'.gemini-api-key'),'--run-dir',str(run),'--instruction',episode['instruction'],'--require-full-budget','--cli',str(OLD/'cli/node_modules/.bin/gemini'),'--dry-run']
  r=subprocess.run(cmd,env=env,capture_output=True,text=True)
  result={'id':t['id'],'exit_code':r.returncode,'reference_run':str(ref)}
  if r.returncode:result['error']=r.stderr[-6000:]
  else:
   assert sha(run/'prompt.txt')==sha(ref/'prompt.txt')
   result.update(prompt_file_sha256=sha(run/'prompt.txt'),launch_sha256=sha(run/'launch.json'),settings_sha256=sha(run/'gemini-settings.json'),icl_verified=True)
  results.append(result)
  (B/'prompt-preflight-v2.json').write_text(json.dumps({'time':time.time(),'status':'passed' if len(results)==21 and all(t['exit_code']==0 for t in results) else 'in_progress' if r.returncode==0 else 'needs_resolution','tasks':results,'model_requests':0},indent=2))
  if r.returncode:raise RuntimeError('Prompt preflight failed for '+t['id'])
if __name__=='__main__':main()
