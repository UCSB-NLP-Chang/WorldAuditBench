import json
import plan_addition_routes as q
refs={t['id']:t for t in json.loads((q.B/'reference-provenance.json').read_text())['tasks']}
rows=[]
for tid in ['S01','S03']:
 for t in json.loads((q.B/'draft-compositions'/tid/'targets.json').read_text())['additions']:rows.append(q.plan(refs[tid],t))
q.write(q.B/'subway-addition-plan-status.json',{'tasks':rows,'models_started':0})
