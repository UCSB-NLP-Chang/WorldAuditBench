"""Prepare private Near/Medium policies and episode identities; never launch models."""
from pathlib import Path
import copy,json,hashlib,time,shutil
B=Path(__file__).resolve().parent;S=json.loads((B/'selection.json').read_text())
def read(p):return json.loads(p.read_text())
def write(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,indent=2))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 episodes=[];proof=[];sources=sorted({t['source_remote'] for t in S['tasks']})
 for arm in ['near','medium']:
  for source in sources:
   group='urban' if 'urban-nomap' in source else 'nonurban';old=Path(source)/'pinned-production';dest=B/'private-runtime'/arm/group;selected=[t for t in S['tasks'] if t['source_remote']==source];policies={}
   for h in sorted({t['policy_sha256'] for t in selected}):
    original=read(old/'policies'/h);updated=copy.deepcopy(original);diffs=[]
    for t in selected:
     if t['policy_sha256']!=h:continue
     geometry=read(B/'route-preparation'/t['id']/'result.json');assert geometry['status']=='candidate_geometry_prepared'
     orig=original['tasks'][t['id']];new=geometry['arms'][arm]['policy'];keys=set(orig)|set(new);changed=[k for k in keys if orig.get(k)!=new.get(k)];assert set(changed)<= {'spawn','route_to_old_spawn'},(t['id'],changed)
     assert new['yaw']==orig['yaw'] and new['bounds_min']==orig['bounds_min'] and new['bounds_max']==orig['bounds_max'] and new['focus']==orig['focus']
     updated['tasks'][t['id']]=new;diffs.append({'id':t['id'],'changed_keys':sorted(changed),'spawn':new['spawn'],'remaining_route_cm':geometry['arms'][arm]['remaining_route_cm'],'far_route_cm':geometry['far_distance_cm']})
    temp=dest/'policies'/(h+'.candidate.json');write(temp,updated);newhash=digest(temp);p=temp.parent/newhash
    if p.exists():assert digest(p)==newhash;temp.unlink()
    else:temp.rename(p)
    policies[h]=(p,newhash);proof.append({'arm':arm,'source':source,'old_policy_sha256':h,'new_policy_sha256':newhash,'diffs':diffs})
   for rel in ['audit/tasks.json','audit/runtime.json','shared/runtime-prod.json']:
    value=read(old/rel)
    if 'runtime' in rel:
     for profile in value['launch_profiles'].values():
      args=profile.get('extra_args',[])
      for i,arg in enumerate(args):
       if arg.startswith('-AuditorExplorationPolicy='):
        originalpath=Path(arg.split('=',1)[1]);h=digest(originalpath)
        if h in policies:args[i]='-AuditorExplorationPolicy='+str(policies[h][0])
    write(dest/rel,value)
   for t in selected:
    e=copy.deepcopy(t);e.update(id=arm+'__'+t['id'],task_id=t['id'],distance_condition=arm,private_production=str(dest),original_policy_sha256=t['policy_sha256'],policy_sha256=policies[t['policy_sha256']][1],reference_run=str(Path(source)/'cases'/t['id']/'run'),ready_for_model=False);episodes.append(e)
 assert len(episodes)==2*len(S['tasks']) and len({t['id'] for t in episodes})==2*len(S['tasks'])
 value={k:v for k,v in S.items() if k!='tasks'};value.update(tasks=episodes,total=len(episodes),parallelism=8,gpus=[0,1,2,3],icl_enabled=True,ready_for_model=False)
 write(B/'episodes-selection.json',value);write(B/'private-runtime-preparation.json',{'time':time.time(),'episodes':len(episodes),'policy_proof':proof,'ready_for_model':False,'pending':['rendered route QA','target visibility QA','trigger-state equivalence QA','distance coordinator/launch preflight']});print('Full-cohort private runtime configurations prepared; no model launches; all QA gates remain closed')
if __name__=='__main__':main()
