from pathlib import Path
import tempfile,json,copy,math
from repeat_admission import validate,consume
from summarize_random import summarize

def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x))
def fixture(b):
 refs=[{'id':f'T{i:02d}'} for i in range(21)]
 tasks=[{'id':c+'__'+t['id'],'task_id':t['id'],'condition':c,'subcategory':'G1','targets':{'targets':[{'subcategory':'G1'}]+[{'subcategory':'G3'} for _ in c[1:]]}} for c in ['AB','ABC'] for t in refs]
 write(b/'reference-provenance.json',{'tasks':refs});write(b/'episodes-selection.json',{'model':'gemini-3.8-flash','thinking_level':'medium','max_actions':40,'max_tool_calls':400,'tasks':tasks})
 write(b/'admission.json',{'approved':True,'schema':'section62-random-types-one-round-v1','files':{}});write(b/'protected-source-hashes.json',{});write(b/'preflight.json',{'passed':True,'model_calls':0});write(b/'qa-review.json',{'passed':True,'model_calls':0,'anchors':{t['id']:{'native_checks_passed':True,'visual_review_passed':True} for t in refs}})
 return tasks
results=[]
for name in ['valid','wrong_model','wrong_budget','duplicate_task','missing_task','manual_stop','old_attempt','consumed','changed_source']:
 with tempfile.TemporaryDirectory() as d:
  b=Path(d);tasks=fixture(b);p=b/'episodes-selection.json';s=json.loads(p.read_text())
  if name=='wrong_model':s['model']='other'
  if name=='wrong_budget':s['max_actions']=60
  if name=='duplicate_task':s['tasks'][-1]=s['tasks'][0]
  if name=='missing_task':s['tasks'].pop()
  write(p,s)
  if name=='manual_stop':write(b/'SYSTEM_STOP',{})
  if name=='old_attempt':(b/'cases'/tasks[0]['id']).mkdir(parents=True)
  if name=='consumed':write(b/'admission.consumed.json',{})
  if name=='changed_source':write(b/'protected-source-hashes.json',{str(p):'bad'})
  if name=='valid':
   validate(b);consume(b)
   try:consume(b);raise RuntimeError('Duplicate consume accepted')
   except AssertionError:pass
  else:
   try:validate(b);raise RuntimeError('Negative case accepted: '+name)
   except AssertionError:pass
  results.append(name)
rows=[{'condition':c,'anchor':f'T{i:02d}','status':'completed','metrics':{'anchor_success':int(i<9),'all_target_success':int(i<3),'matched_targets':int(i<9),'target_count':len(c)}} for c in ['A','AB','ABC'] for i in range(21)]
s=summarize(rows);assert s['conditions']['A']['anchor_sr']==100*9/21
rows[0]['status']='failed';rows[0]['metrics'].update(anchor_success=None,all_target_success=None,matched_targets=None)
s=summarize(rows);assert s['conditions']['A']['anchor_sr']==100*8/21 and rows[0]['metrics']['anchor_success'] is None
print(json.dumps({'passed':True,'model_calls':0,'admission_cases':results,'aggregation_checks':['fixed denominator 21','one round only','failed raw grades remain null']}))
