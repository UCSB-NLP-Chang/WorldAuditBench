import json
import plan_addition_routes as q
r=next(t for t in json.loads((q.B/'reference-provenance.json').read_text())['tasks'] if t['id']=='S03')
t=json.loads((q.B/'draft-compositions/S03/targets.json').read_text())['additions'][1]
q.plan(r,t,100)
