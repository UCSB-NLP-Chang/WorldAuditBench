import json
import plan_addition_routes as q
refs={r['id']:r for r in json.loads((q.B/'reference-provenance.json').read_text())['tasks']}
rows=[]
for tid in ['S06','H01','H03','H04']:
 for t in json.loads((q.B/'draft-compositions'/tid/'targets.json').read_text())['additions']:
  r=q.plan(refs[tid],t)
  if r['status']=='needs_resolution':r=q.plan(refs[tid],t,100)
  rows.append(r)
  q.write(q.B/'s06-indoor-plans-status.json',{'model_calls':0,'tasks':rows})
