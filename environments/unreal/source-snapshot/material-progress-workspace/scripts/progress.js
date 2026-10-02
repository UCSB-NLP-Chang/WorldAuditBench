function syncProgressOptions(select, entries, emptyLabel){
 const current=select.value;
 const signature=JSON.stringify(entries);
 if(select.dataset.entries===signature)return;
 select.replaceChildren(new Option(emptyLabel,''));
 for(const [value,label] of entries)select.append(new Option(label,value));
 select.value=entries.some(([value])=>value===current)?current:'';
 select.dataset.entries=signature;
}
function progressEnvironmentName(family){return ({subway:'Subway',indoor:'Indoor',urban:'Urban',ancient:'Ancient Chinese City',medieval:'Medieval Village',rural:'Rural Australia',industrial:'Industrial',threejs_sponza:'Three.js · Sponza',threejs_cottage:'Three.js · Mistwood Cottage',threejs_airfield:'Three.js · Airfield',threejs_house:'Three.js · Family House',threejs_reef:'Three.js · Reef Dive',threejs_wilderness:'Three.js · Wilderness'}[family]||family);}
function renderProgress(){
 if(!dashboardData)return;
 const engine=$('progress-engine').value;
 const families=[...new Set(dashboardData.tasks.filter(t=>!engine||engineOf(t)===engine).map(t=>taskFamily(t)))];
 syncProgressOptions($('progress-environment'),families.map(f=>[f,progressEnvironmentName(f)]),'All environments');
 syncProgressOptions($('progress-reviewer'),(dashboardData.reviewer_options||[]).map(r=>[r.id,r.name+(r.mine?' (you)':'')]),'All reviewers');
 const reviewer=$('progress-reviewer').value,environment=$('progress-environment').value;
 const person=dashboardData.reviewer_options?.find(r=>r.id===reviewer);
 $('progress-review-heading').textContent=person?person.name+' · Review':'Your review';
 const body=$('progress-rows'),filter=$('progress-filter').value,selectedType=$('progress-taxonomy').value;
 body.replaceChildren();
 for(const task of dashboardData.tasks){
  if(engine&&engineOf(task)!==engine)continue;
  if(environment&&taskFamily(task)!==environment)continue;
  if(selectedType==='baseline'?task.case_type!=='baseline':selectedType&&(task.case_type==='baseline'||task.taxonomy?.code!==selectedType))continue;
  if(filter==='review'&&task.accepted||filter==='accepted'&&!task.accepted)continue;
  const quality=reviewer?task.reviewer_results?.find(r=>r.id===reviewer)?.quality:task.my_quality;
  if(reviewer&&!quality)continue;
  const row=document.createElement('tr');row.dataset.taskId=task.id;
  const id=textElement('td',displayTaskId(task));
  const world=textElement('td',progressEnvironmentName(taskFamily(task))+' / '+sceneName(task.scene));
  const approval=textElement('td',task.approvals+' / 2');
  if(task.reviewers.length)approval.append(textElement('small',task.reviewers.join(', '),'approval-names'));
  const status=document.createElement('td');status.append(textElement('span',task.accepted?'Accepted':'Review',task.accepted?'status-pill accepted':'status-pill'));
  const result=textElement('td',quality?{pass:'Pass',fail:'Fail',uncertain:'Uncertain'}[quality]:'—','progress-quality '+(quality||''));
  const actionCell=document.createElement('td'),button=textElement('button','Review →','quiet');
  button.disabled=Boolean(active())||state.busy;button.onclick=()=>{$('environment-select').value='';populateTasks(task.id);renderCase();controls();showView('review');};actionCell.append(button);
  const bugType=textElement('td','','progress-bug-type');renderProgressType(bugType,task);
  const totalReviews=textElement('td',String(task.total_reviews??0));totalReviews.title='Number of review tags: one per reviewer and reviewed version; repeated edits count once';
  row.append(id,world,bugType,approval,totalReviews,status,result,actionCell);body.append(row);
 }
 $('progress-result-count').textContent=body.children.length+' of '+dashboardData.tasks.length+' review entries'+(person?' · '+person.name+'’s reviewed tasks':'');
 if(!body.children.length){const row=document.createElement('tr'),cell=textElement('td',person?'No reviewed tasks match these filters.':'No tasks in this view.');cell.colSpan=8;row.append(cell);body.append(row);}
}
$('progress-engine').onchange=renderProgress;
for(const id of ['progress-environment','progress-reviewer','progress-filter','progress-taxonomy'])$(id).onchange=renderProgress;
