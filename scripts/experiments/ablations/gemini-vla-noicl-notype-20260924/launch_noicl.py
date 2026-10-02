from pathlib import Path
import importlib.util,json
B=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('native_launch',B/'code/scripts/native-agents/launch.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
original=m.prepare
def prepare(args):
 assert args.no_icl and args.environment=='vla-replay' and args.replay_mode=='vqa'
 run,cmd,env,prompt,manifest=original(args)
 # The native server omits read_example when ICL is disabled. Match its allowlist.
 manifest['tools']=[t for t in manifest['tools'] if t!='read_example']
 settings=json.loads((run/'gemini-settings.json').read_text());settings['mcpServers']['world_audit']['includeTools']=manifest['tools']
 (run/'gemini-settings.json').write_text(json.dumps(settings,indent=2)+'\n')
 (run/'launch.json').write_text(json.dumps(manifest,indent=2)+'\n')
 return run,cmd,env,prompt,manifest
m.prepare=prepare
m.main()
