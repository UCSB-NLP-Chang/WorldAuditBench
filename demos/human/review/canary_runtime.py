from pathlib import Path
import re,json,sys
root=Path('/home/ubuntu/unreal-auditor/review-service/state');sid=sys.argv[1];assert re.fullmatch('[0-9a-f]{32}',sid)
d=Path(json.loads((root/'runtime.json').read_text())['state_dir'])/sid/'review-ipc'
data=json.loads((d/'response.json').read_text())
# Read only: writing a diagnostic command would replace the supervisor's
# expected acknowledgement and correctly fail its scene identity check.
print(json.dumps({k:data[k] for k in ('pid','generation','map','task','status','position')}))

