from pathlib import Path
import sys,json,copy,concurrent.futures,time,hashlib,importlib.util,collections
B=Path(__file__).resolve().parent;P=B/sys.argv[1];C=B/'code';sys.path.insert(0,str(C))
spec=importlib.util.spec_from_file_location('base_replay',C/'agent/vla/replay.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
tasks=json.loads((B/'tasks.json').read_text());profiles=json.loads((B/'profiles.json').read_text())['tasks'];progress=json.loads((P/'progress.json').read_text());state=progress['tasks']
assert len(state)==126 and all(x['status'] in ['completed','failed','interrupted'] for x in state.values())
a=m.cli().parse_args(['--recordings',str(P/'replay-recordings'),'--batch',str(P),'--client','gemini','--model','gemini-3.8-flash','--replay-mode','vqa','--judge-python',str(C/'.venv/bin/python')])
def grade(t):
 tid=t['id'];v=state[tid]
 if v['status']!='completed':return tid,None,None
 run=P/'cases'/tid/'run' if P.name=='03-vlm-60steps' else Path(v.get('run_dir') or str(P/'cases'/tid/'run'));job=run.parent
 ga=copy.copy(a);ga.batch=job.parent.parent
 try:
  j=json.loads((job/'judge.json').read_text()) if (job/'judge.json').exists() else m.Batch(ga).grade(t,profiles)
  assert j['score'] in [0,1] and j['reason'];return tid,j,None
 except Exception as e:return tid,None,repr(e)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 for tid,j,e in pool.map(grade,tasks):
  if j:state[tid].update(judge=j,judge_error=None)
  elif e:state[tid]['judge_error']=e
progress['updated_at']=time.time();(P/'progress.json').write_text(json.dumps(progress,indent=2))
rows=[{'id':t['id'],'family':t['family'],'subcategory':t['subcategory'],**state[t['id']]} for t in tasks]
completed=[r for r in rows if r['status']=='completed'];graded=[r for r in completed if r.get('judge')]
counts=dict(collections.Counter(r['status'] for r in rows));success=sum(r['judge']['score'] for r in graded)
summary={'time':time.time(),'phase':P.name,'model':'gemini-3.8-flash','thinking':'medium','cohort':126,'counts':counts,'graded':len(graded),'successes':success,'success_rate_full_cohort':success/126,'tasks':rows,'runtime_snapshot':'90363176cb183809ae6b28ab57ea94e30c74b525','historical_attempts_preserved':True}
# Account for every attempt, including failed/interrupted runs, from real native usage.
cspec=importlib.util.spec_from_file_location('native_cost',C/'scripts/experiments/summarize_batch.py');cm=importlib.util.module_from_spec(cspec);cspec.loader.exec_module(cm)
usage_rows=[]
for events in P.rglob('native-events.jsonl'):
 stats={};h=hashlib.sha256()
 with events.open('rb') as f:
  for raw in f:
   h.update(raw)
   try:e=json.loads(raw)
   except (ValueError,UnicodeDecodeError):continue
   if e.get('type')=='result':stats=e.get('stats',{})
 cost=cm.estimate_cost(stats)
 usage_rows.append({'run':str(events.parent),'native_events_sha256':h.hexdigest(),'native_stats':stats,'api_equivalent_cost':cost})
summary['cost']={'known_api_equivalent_usd':sum(r['api_equivalent_cost']['estimated_usd'] for r in usage_rows if r['api_equivalent_cost']['estimated_usd'] is not None),'unknown_attempts':sum(r['api_equivalent_cost']['estimated_usd'] is None for r in usage_rows),'attempts':len(usage_rows),'excludes':'judge and GPU infrastructure','unknown_is_not_zero':True}
(P/'all-attempt-usage.json').write_text(json.dumps(usage_rows,indent=2))
(P/'verified-results.json').write_text(json.dumps(summary,indent=2))
files=[]
for r in rows:
 run=P/'cases'/r['id']/'run' if P.name=='03-vlm-60steps' else Path(r.get('run_dir') or str(P/'cases'/r['id']/'run'));job=run.parent
 for p in [run/'launch.json',run/'episode/meta.json',job/'judge.json',job/'judge-input.json',job/'judge-provenance.json',job/'rubric.json']:
  if p.is_file():files.append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(P/'verified-artifact-hashes.json').write_text(json.dumps(files,indent=2));print(json.dumps({k:v for k,v in summary.items() if k!='tasks'}))
assert len(graded)==len(completed),'Real judge has missing grades; do not advance phase'
(P/'verified.finished.json').write_text(json.dumps({'time':time.time(),'counts':counts,'graded':len(graded),'successes':success}))
