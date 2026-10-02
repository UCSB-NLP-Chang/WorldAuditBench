from pathlib import Path
import json,hashlib,shutil,time
B=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text())
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
assert not (B/'admission.consumed.json').exists() and not (B/'cases').exists()
s=read(B/'episodes-selection.json');draws=read(B/'random-draws.json');revisions=read(B/'ineligible-candidate-revisions.json');old=B/'qa-initial-candidates'
assert not (old/'S06').exists()
shutil.copy2(B/'episodes-selection.json',old/'before-S06-selection.json')
shutil.move(str(B/'qa/composition-rendered-routes/S06'),str(old/'S06'))
for cond in ['AB','ABC']:
 p=B/'specs/S06'/(cond+'.json');shutil.copy2(p,old/('S06-'+cond+'.json'));sp=read(p)
 t=next(t for t in s['tasks'] if t['id']==cond+'__S06');target=t['targets']['targets'][1];assert target['subcategory']=='G3'
 target.update(subcategory='G1',rubrics={'expected':'The object rests on its normal supporting surface.','criteria':'The specified object floats with a visible unsupported gap below it.'})
 sp['additions'][0].pop('factor');sp['additions'][0].update(operation='offset',offset=[0,0,60]);write(p,sp);t['composition_sha256']=hashlib.sha256(p.read_bytes()).hexdigest();write(B/'rubrics'/(t['id']+'.json'),t['targets'])
d=next(d for d in draws['draws'] if d['anchor']=='S06' and d['label']=='B');d.update(initial_selected='G3',excluded_after_zero_model_QA=['G3'],eligible=['G1'],selected='G1')
revisions['records'].append({'task':'S06','label':'B','initial':'G3','selected':'G1','eligible_after_native_QA':['G1'],'reason':'Enlarged neighboring vending machine occludes original anchor inspection; excluded by visual/native scene QA before any model outcome.','old_evidence':str(old/'S06')})
for n,v in [('episodes-selection.json',s),('random-draws.json',draws),('ineligible-candidate-revisions.json',revisions)]:write(B/n,v)
