"""Exclude four physically inaccessible collision candidates, before any model call."""
from pathlib import Path
import json,hashlib,shutil,time,random
B=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text())
def write(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
assert not (B/'admission.consumed.json').exists() and not (B/'cases').exists()
assert not (B/'ineligible-candidate-revisions.json').exists()
s=read(B/'episodes-selection.json');draws=read(B/'random-draws.json');audit=read(B/'native-audit.json');old=B/'qa-initial-candidates';old.mkdir(exist_ok=False)
for name in ['episodes-selection.json','random-draws.json','native-audit.json']:shutil.copy2(B/name,old/name)
records=[]
for tid in ['A05','H03']:
 row=next(x for x in audit['tasks'] if x['task']==tid);assert not row['native_checks_passed']
 shutil.move(str(B/'qa/composition-rendered-routes'/tid),str(old/tid))
 for cond in ['AB','ABC']:
  sp=B/'specs'/tid/(cond+'.json');shutil.copy2(sp,old/(tid+'-'+cond+'.json'));spec=read(sp)
  task=next(t for t in s['tasks'] if t['id']==cond+'__'+tid);targets=task['targets']['targets']
  for target,addition in zip(targets[1:],spec['additions']):
   assert target['subcategory']=='C1' and task['subcategory']=='G3'
   target.update(subcategory='G1',rubrics={'expected':'The object rests on its normal supporting surface.','criteria':'The specified object floats with a visible unsupported gap below it.'})
   addition.pop('factor',None);addition.update(operation='offset',offset=[0,0,60])
  write(sp,spec);task['composition_sha256']=hashlib.sha256(sp.read_bytes()).hexdigest();write(B/'rubrics'/(task['id']+'.json'),task['targets'])
 for label in ['B','C']:
  draw=next(d for d in draws['draws'] if d['anchor']==tid and d['label']==label);draw['initial_selected']=draw['selected'];draw['excluded_after_zero_model_QA']=['C1'];draw['eligible']=[x for x in draw['eligible'] if x!='C1'];assert draw['eligible']==['G1'];draw['selected']='G1'
  records.append({'task':tid,'label':label,'initial':'C1','eligible_after_native_QA':['G1'],'selected':'G1','reason':'Paired fine-grained native probes did not establish meaningful collision penetration; small/blocked furniture object. Exclude this object-category combination without using model outcomes.','old_evidence':str(old/tid)})
write(B/'episodes-selection.json',s);write(B/'random-draws.json',draws)
write(B/'ineligible-candidate-revisions.json',{'time':time.time(),'model_calls':0,'records':records,'preserved_initial_candidates':str(old),'rerender_required':True})
print('Excluded four infeasible C1 object-category combinations; 14 replacement native QA cases required; no model calls.')
