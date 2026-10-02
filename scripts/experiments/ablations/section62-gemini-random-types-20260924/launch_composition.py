"""Use the original Gemini launcher with exactly the selected anchor prompt/settings."""
from pathlib import Path
import hashlib,importlib.util,json,sys
assert sys.argv[1]=='--source-batch'
source=Path(sys.argv[2]);del sys.argv[1:3]
f=source/'code/scripts/native-agents/launch.py'
spec=importlib.util.spec_from_file_location('frozen_launch',f);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
original=module.prepare
def prepare(args):
 assert args.client=='gemini' and args.model=='gemini-3.8-flash' and args.gemini_thinking=='medium'
 assert args.max_actions==40 and args.max_tool_calls==400 and args.require_full_budget
 run,command,env,prompt,manifest=original(args)
 ref=(source/'cases'/args.task/'run').resolve(strict=True)
 baseline=json.loads((ref/'gemini-settings.json').read_text());settings=json.loads((run/'gemini-settings.json').read_text())
 for key in ['model','tools','mcp','security','context','modelConfigs','hooksConfig']:
  assert key in baseline;settings[key]=baseline[key]
 (run/'gemini-settings.json').write_text(json.dumps(settings,indent=2))
 episode=json.loads((run/'episode-config.json').read_text());reference=json.loads((ref/'episode-config.json').read_text())
 # The frozen launcher persists prompt + one newline, but sends prompt itself.
 assert (run/'prompt.txt').read_bytes()==(ref/'prompt.txt').read_bytes(),'Composition changed original model prompt file'
 assert prompt+'\n'==(ref/'prompt.txt').read_text(),'Unexpected prompt serialization'
 assert manifest['prompt_sha256']==json.loads((ref/'launch.json').read_text())['prompt_sha256'],'Composition changed sent model prompt'
 for key in ['max_actions','max_tool_calls','observation','instruction','scene_description','icl']:
  assert episode[key]==reference[key],key
 assert episode['icl']['enabled']
 protocol={k:v for k,v in episode.items() if k not in {'upstream','run_dir','environment_url','icl_directory'}}
 protocol.update(cli_loop_detection=not settings['model'].get('disableLoopDetection',False),upstream_revision=manifest['upstream_revision'],prompt_sha256=manifest['prompt_sha256'],mcp_implementation_sha256=manifest['mcp_implementation_sha256'])
 manifest.update(protocol_sha256=hashlib.sha256(json.dumps(protocol,sort_keys=True).encode()).hexdigest(),reference_run=str(ref),ablation='Multiple concurrent bugs; original anchor prompt, ICL, settings and budget retained',reference_settings_sha256=hashlib.sha256((ref/'gemini-settings.json').read_bytes()).hexdigest())
 (run/'launch.json').write_text(json.dumps(manifest,indent=2))
 return run,command,env,prompt,manifest
module.prepare=prepare
module.main()
