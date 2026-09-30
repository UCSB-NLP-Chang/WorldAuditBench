from pathlib import Path
import json
w=Path('/home/ubuntu/unreal-auditor/configuration-workspace');stage=w/'configuration-tasks-20260913-v1';runtime=json.loads((stage/'candidate-runtime.json').read_text());tasks=json.loads((stage/'tasks.json').read_text())['tasks']
(stage/'industrial-runtime-profiles.json').write_text(json.dumps({t['map']:runtime['launch_profiles'][t['map']] for t in tasks if t.get('family')=='industrial'},indent=2)+'\n')
