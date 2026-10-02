from pathlib import Path
import importlib.util,sys,json,hashlib
# Re-check retry evidence at native admission, including already-running coordinators.
if '--run-dir' in sys.argv:
 run=Path(sys.argv[sys.argv.index('--run-dir')+1]);job=run.parent
 if job.name.startswith('attempt-') and int(job.name.split('-')[-1])>1:
  from retry_gate import verify_retry
  verify_retry(job)
assert sys.argv[1]=='--source-batch'
source=Path(sys.argv[2]);del sys.argv[1:3]
p=source/'code/scripts/native-agents/launch.py'
spec=importlib.util.spec_from_file_location('frozen_launch',p);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
original=module.prepare
def prepare(args):
 run,command,env,prompt,manifest=original(args)
 ref=source/'cases'/args.task/'run'
 baseline=json.loads((ref/'gemini-settings.json').read_text())
 settings=json.loads((run/'gemini-settings.json').read_text())
 for key in ['model','tools','mcp','security','context','modelConfigs','hooksConfig']:
  assert key in baseline
  settings[key]=baseline[key]
 (run/'gemini-settings.json').write_text(json.dumps(settings,indent=2))
 episode=json.loads((run/'episode-config.json').read_text())
 protocol={k:v for k,v in episode.items() if k not in {'upstream','run_dir','environment_url','icl_directory'}}
 protocol.update(cli_loop_detection=not settings['model'].get('disableLoopDetection',False),upstream_revision=manifest['upstream_revision'],prompt_sha256=manifest['prompt_sha256'],mcp_implementation_sha256=manifest['mcp_implementation_sha256'])
 manifest.update(protocol_sha256=hashlib.sha256(json.dumps(protocol,sort_keys=True).encode()).hexdigest(),reference_run=str(ref),ablation='ICL images and demonstration text removed; category identity and definition preserved',reference_settings_sha256=hashlib.sha256((ref/'gemini-settings.json').read_bytes()).hexdigest())
 (run/'launch.json').write_text(json.dumps(manifest,indent=2))
 return run,command,env,prompt,manifest
module.prepare=prepare
module.main()
