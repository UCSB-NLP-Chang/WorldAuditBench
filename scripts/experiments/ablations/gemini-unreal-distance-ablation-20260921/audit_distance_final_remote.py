import json,time,hashlib,subprocess
from pathlib import Path
from collections import Counter
B=Path('/mnt/auditor-build/experiment-runs/gemini-unreal-distance-ablation-20260921');p=json.loads((B/'progress.json').read_text());print('utc',time.strftime('%H:%M:%S',time.gmtime()),'counts',dict(Counter(v['status'] for v in p['tasks'].values())))
if not (B/'batch.finished').exists() or any(v['status'] not in ('completed','failed') for v in p['tasks'].values()):raise SystemExit(0)
assert json.loads((B/'reservation.json').read_text())['status']=='released'
f=json.loads((B/'batch.finished').read_text());assert not f.get('stopped') and not f.get('drained')
errors=[];rows=[]
for k,v in p['tasks'].items():
 case=B/'cases'/k;attempts=list(case.glob('attempt-*'));r=Path(v['run_dir']);e=r/'episode';m=json.loads((e/'meta.json').read_text());row={'id':k,'status':v['status'],'attempt_count':len(attempts),'meta_sha256':hashlib.sha256((e/'meta.json').read_bytes()).hexdigest(),'native_events_sha256':hashlib.sha256((r/'native-events.jsonl').read_bytes()).hexdigest()}
 if len(attempts)!=1 or v['attempt']!=1:errors.append(k+':attempt_count')
 for n in ['native-events.jsonl','episode/meta.json','episode/mcp-calls.jsonl','episode/actions.jsonl','episode/trajectory.jsonl','episode/frames.jsonl']:
  if not (r/n).is_file() or not (r/n).stat().st_size:errors.append(k+':missing '+n)
 frames=[json.loads(x)['file'] for x in (e/'frames.jsonl').read_text().splitlines() if x.strip()];row['indexed_frames']=len(frames)
 for n in frames:
  if not (e/n).is_file() or not (e/n).stat().st_size:errors.append(k+':missing frame '+n)
 if v['status']=='completed':
  if not(m['status']=='completed' and m['actions_used']==40 and m.get('done_summary') and m.get('icl_complete') and m.get('icl_examples_delivered')):errors.append(k+':incomplete report')
  if m['backend'].get('minimap_policy')!='masked-before-archive-v1':errors.append(k+':minimap')
  if not (case/'run').is_symlink() or (case/'run').resolve()!=r.resolve():errors.append(k+':official link')
 else:
  if (case/'run').exists() or (case/'run').is_symlink():errors.append(k+':failed official link')
  if not (case/'model-early-stop-audit.json').is_file():errors.append(k+':failed missing audit')
 rows.append(row)
for pid in [4164661,4164702]:
 if Path('/proc/'+str(pid)).exists():errors.append('controller still exists:'+str(pid))
a={'checked_at':time.time(),'passed':not errors,'errors':errors,'assigned':len(rows),'completed':sum(r['status']=='completed' for r in rows),'failed':sum(r['status']=='failed' for r in rows),'scope':'Single attempts, terminal statuses, completed report/ICL/minimap metadata, official links, nonempty native/action/trajectory/MCP records and every indexed frame; failed audits retained. No semantic rejudging. Optional chat history gap remains documented.','rows':rows}
(B/'final-runtime-audit.json').write_text(json.dumps(a,indent=2)+'\n');print('audit',{k:v for k,v in a.items() if k!='rows'})
subprocess.run(['python3.12',str(B.parent/'monitor_cost_progress.py'),str(B),'--kind','gemini'],stdout=subprocess.DEVNULL,check=True)
print('cost',{k:v for k,v in json.loads((B/'cost-progress.json').read_text()).items() if not isinstance(v,(dict,list))})
