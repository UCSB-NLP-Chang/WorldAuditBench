from pathlib import Path
import json,time,hashlib,importlib.util,sys
B=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text())
def summarize(rows):
 assert len(rows)==63
 out={}
 for c in ['A','AB','ABC']:
  group=[r for r in rows if r['condition']==c];assert len(group)==len({r['anchor'] for r in group})==21
  out[c]={'scheduled':21,'completed':sum(r['status']=='completed' for r in group),'failed':sum(r['status']=='failed' for r in group),'anchor_success':sum(r['metrics']['anchor_success'] or 0 for r in group),'all_success':sum(r['metrics']['all_target_success'] or 0 for r in group),'matched_targets':sum(r['metrics']['matched_targets'] or 0 for r in group),'total_targets':21*len(c)}
  out[c].update(anchor_sr=100*out[c]['anchor_success']/21,all_sr=100*out[c]['all_success']/21,target_recall=100*out[c]['matched_targets']/(21*len(c)))
 return {'time':time.time(),'conditions':out,'rows':rows,'runs':1,'failure_policy':'Fixed denominator 21. Failed raw grades remain null; no invented judge result.','scope':'Random other-category additions under original anchor-directed instructions; same-category runs excluded.'}
def main():
 rows=[]
 for t in read(B/'original-results.json')['tasks']:
  a=t['A'];assert a in [0,1]
  rows.append({'condition':'A','anchor':t['anchor'],'status':'completed','metrics':{'anchor_success':a,'all_target_success':a,'matched_targets':a,'target_count':1},'source':'original frozen single-anomaly baseline'})
 progress=read(B/'progress.json')['tasks']
 for t in read(B/'episodes-selection.json')['tasks']:
  v=progress[t['id']];assert v['status'] in ['completed','failed']
  metrics=read(B/'judge/cases'/t['id']/'metrics.json') if v['status']=='completed' else {'anchor_success':None,'all_target_success':None,'matched_targets':None,'target_count':len(t['condition'])}
  rows.append({'condition':t['condition'],'anchor':t['task_id'],'status':v['status'],'metrics':metrics,'source':t['id']})
 result=summarize(rows);code=B.parent/'section61-gemini-unreal-20260923/code';sys.path.insert(0,str(code));sp=importlib.util.spec_from_file_location('cost',code/'scripts/native-agents/summarize_batch.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
 costs=[]
 for attempt in (B/'cases').glob('*/attempt-*'):
  p=attempt/'run/native-events.jsonl'
  h=hashlib.sha256();stats={}
  if not p.exists():
   costs.append({'path':str(p),'sha256':None,'stats':{},'api_equivalent':{'estimated_usd':None,'reason':'No usage log; unknown, not zero'}});continue
  with p.open('rb') as f:
   for line in f:
    h.update(line)
    try:e=json.loads(line)
    except ValueError:continue
    if e.get('type')=='result':stats=e.get('stats',{})
  costs.append({'path':str(p),'sha256':h.hexdigest(),'stats':stats,'api_equivalent':m.estimate_cost(stats) if stats else {'estimated_usd':None,'reason':'No terminal usage stats; unknown, not zero'}})
 result['cost']={'known_api_equivalent_usd':sum(c['api_equivalent']['estimated_usd'] for c in costs if c['api_equivalent']['estimated_usd'] is not None),'unknown_attempts':sum(c['api_equivalent']['estimated_usd'] is None for c in costs),'excludes':'judge and GPU infrastructure'}
 (B/'all-attempt-usage.json').write_text(json.dumps(costs,indent=2)+'\n')
 (B/'verified-results.json').write_text(json.dumps(result,indent=2)+'\n')
 (B/'verified.finished.json').write_text(json.dumps({k:v for k,v in result.items() if k!='rows'},indent=2)+'\n');print(json.dumps(result['conditions']))
if __name__=='__main__':main()
