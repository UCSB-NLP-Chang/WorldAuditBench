from pathlib import Path
import json,time,collections,subprocess,os,hashlib
B=Path(__file__).resolve().parent

def read(p):return json.loads(p.read_text())
progress=read(B/'progress.json');rows=[]
for tid,t in progress['tasks'].items():
 if t['status']=='queued':continue
 run=B/'cases'/tid/'attempt-1/run';row={'id':tid,'status':t['status'],'gpu':t.get('gpu'),'slot':t.get('slot'),'attempt':t.get('attempt'),'actions':t.get('actions_used',0)}
 p=run/'episode-config.json'
 if p.exists():
  cfg=read(p);row['configuration']={k:cfg.get(k) for k in ['model','max_actions','max_tool_calls','require_full_budget']}
 p=run/'episode/meta.json'
 if p.exists():
  m=read(p);row.update(actions=m.get('actions_used',0),icl_complete=m.get('icl_complete'),icl_examples_delivered=m.get('icl_examples_delivered'),minimap=m.get('backend',{}).get('minimap_policy'))
 p=run/'episode/mcp-calls.jsonl'
 if p.exists():
  calls=[json.loads(l) for l in p.read_text().splitlines()];row['first_tools']=[c.get('tool') for c in calls[:5]];reads=[i for i,c in enumerate(calls) if c.get('tool')=='read_example' and c.get('images') and not c.get('is_error')];obs=[i for i,c in enumerate(calls) if c.get('tool')=='observe' and not c.get('is_error')];row['image_example_before_observe']=bool(reads and obs and reads[0]<obs[0]);row['mcp_call_count']=len(calls)
 p=run/'native-events.jsonl'
 if p.exists():
  types=collections.Counter();models=set();roles=collections.Counter()
  with p.open() as f:
   for line in f:
    try:e=json.loads(line)
    except ValueError:continue
    types[e.get('type')]+=1
    if e.get('model'):models.add(str(e['model']))
    if e.get('role'):roles[e['role']]+=1
  row.update(event_types=dict(types),event_models=sorted(models),roles=dict(roles),last_native_event_write=p.stat().st_mtime)
 p=run/'native-stderr.log';row['stderr_bytes']=p.stat().st_size if p.exists() else None
 p=run.parent/'composition-verification.json';row['composition_verified_before_model']=p.exists() and read(p).get('verified_before_model') is True
 rows.append(row)
v=os.statvfs(B);out={'time':time.time(),'coordinator_pid':int((B/'coordinator.pid').read_text()),'counts':dict(collections.Counter(t['status'] for t in progress['tasks'].values())),'graded':len(list((B/'judge/cases').glob('*/metrics.json'))),'tasks':rows,'controls':{n:(B/n).exists() for n in ['SYSTEM_STOP','STOP.json','DRAIN.json','API_QUOTA_OR_AUTH_STOP','batch.finished']},'free_disk_bytes':v.f_frsize*v.f_bavail,'free_inodes':v.f_favail,'gpu':subprocess.check_output(['nvidia-smi','--query-gpu=index,utilization.gpu,memory.used','--format=csv,noheader'],text=True),'baseline_A_reused':21,'new_episodes':42,'new_model':'gemini-3.8-flash','judge':'gpt-6-astra medium; original primary + joint-target judge, streaming after completion'}
(B/'live-verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
