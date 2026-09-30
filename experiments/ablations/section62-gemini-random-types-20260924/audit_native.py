from pathlib import Path
import json,math,time,hashlib
B=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text())
def audit(t):
 tid=t['task_id'];root=B/'qa/composition-rendered-routes'/tid;issues=[];collisions=[];anchor=None
 for cond,labels in [('A','BC'),('AB','AB'),('ABC','ABC')]:
  for label in labels:
   d=root/cond/label
   if not (d/'result.json').exists():return None
   r=read(d/'result.json')
   if r['status']!='traversed_pending_visual_review':
    approvals=read(B/'alternate-view-reviews.json').get('cases',{}) if (B/'alternate-view-reviews.json').exists() else {}
    approval=approvals.get(tid+'/'+cond+'/'+label,{})
    accepted=approval.get('approved') and str(r.get('error','')).startswith('Replayed route endpoint drift') and approval.get('result_sha256')==hashlib.sha256((d/'result.json').read_bytes()).hexdigest() and approval.get('image_sha256')==hashlib.sha256((d/'target-view.png').read_bytes()).hexdigest()
    if accepted:
     for rel,h in approval.get('additional_evidence',{}).items():assert hashlib.sha256((B/rel).read_bytes()).hexdigest()==h
    else:issues.append([cond,label,r.get('error')]);continue
   state=r['anchor_before_injection']
   if anchor is None:anchor=state
   assert state==anchor,(tid,cond,label,'anchor state changed')
   if cond=='A':continue
   before={x['actor']:x for x in read(d/'composition-before.json')['meshes']};applied=read(d/'composition-status.json');sp=read(B/'specs'/tid/(cond+'.json'))
   assert applied['specification']==str(B/'specs'/tid/(cond+'.json')) and len(applied['additions'])==len(cond)-1
   for current,change in zip(applied['additions'],sp['additions']):
    original=before[current['actor']];assert current['actor']==change['actor'] and current['actor']!=anchor['actor']
    if change['operation']=='offset':assert math.dist(current['position'],[x+y for x,y in zip(original['position'],change['offset'])])<.01
    elif change['operation']=='scale':
     assert math.dist(current['scale'],[x*change['factor'] for x in original['scale']])<.001
     assert abs(current['center'][2]-current['extent'][2]-original['center'][2]+original['extent'][2])<.01
    else:assert original['collision'] and original['pawn_response']==2 and not current['collision']
 for target in t['targets']['targets'][1:]:
  if target['subcategory']!='C1':continue
  label=target['label'];normal=read(root/'A'/label/'result.json');mutated=read(root/'ABC'/label/'result.json')
  if 'collision_trace' not in normal or 'collision_trace' not in mutated:issues.append(['C1',label,'missing collision trace']);continue
  normal_min=min(x['distance_to_center'] for x in normal['collision_trace']);active_min=min(x['distance_to_center'] for x in mutated['collision_trace'])
  difference=normal_min-active_min
  entry={'label':label,'normal_min_center_distance':normal_min,'mutated_min_center_distance':active_min,'difference_cm':difference,'normal_final':normal['collision_probe']['after'],'mutated_final':mutated['collision_probe']['after']};collisions.append(entry)
  # Low walkable objects can be stepped over in the normal scene: compare height
  # at matched XY samples instead of wrongly requiring a horizontal blockage.
  pairs=[]
  for active in mutated['collision_trace']:
   if active['distance_to_center']>min(target['normal_state']['extent'][:2])/2:continue
   baseline=min(normal['collision_trace'],key=lambda x:math.dist(x['position_cm'][:2],active['position_cm'][:2]))
   xy=math.dist(baseline['position_cm'][:2],active['position_cm'][:2]);dz=baseline['position_cm'][2]-active['position_cm'][2]
   if xy<=1:pairs.append({'normal_position':baseline['position_cm'],'mutated_position':active['position_cm'],'xy_difference_cm':xy,'height_difference_cm':dz})
  vertical_proof=len([p for p in pairs if p['height_difference_cm']>=15])>=2
  entry['matched_xy_height_pairs']=pairs;entry['observable_missing_collision']=difference>=15 or vertical_proof
  if not entry['observable_missing_collision']:issues.append(['C1',label,'probe does not establish distinct solid-object penetration or loss of support at matched XY',entry])
 return {'task':tid,'issues':issues,'collision_checks':collisions,'native_checks_passed':not issues,'visual_review_required':True}
def main():
 s=read(B/'episodes-selection.json');rows=[]
 for t in s['tasks']:
  if t['condition']!='ABC':continue
  try:r=audit(t)
  except Exception as e:r={'task':t['task_id'],'native_checks_passed':False,'issues':[repr(e)]}
  if r:rows.append(r)
 result={'time':time.time(),'model_calls':0,'ready':len(rows),'passed':sum(r['native_checks_passed'] for r in rows),'tasks':rows}
 (B/'native-audit.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
