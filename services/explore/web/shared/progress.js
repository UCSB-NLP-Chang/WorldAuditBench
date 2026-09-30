import {api, $, element, message} from '/static/common.js';
import {groupCases} from '/static/case-progress.js';

const stateNames = {not_started:'未开始',draft:'草稿待提交',submitted:'已提交',technical:'技术问题',skipped:'已放弃（未找到）',pending:'待领取',in_progress:'评测中',complete:'已完成'};
const verdictNames = {correct:'正确',partial:'部分正确',incorrect:'不正确',insufficient:'证据不足',additional_bug:'额外 bug',correct_none:'正确未发现',missed:'漏检',uncertain:'无法确定',not_applicable:'不适用',not_reviewed:'历史未复核'};
const number = value => value == null ? '—' : String(value);
const ratio = (a,b) => a == null || b == null ? '—' : a+' / '+b;
const date = value => value ? new Date(value * 1000).toLocaleString() : '—';
function table(headers, rows) {
  const wrapper = element('div', undefined, 'progress-table-wrap'), grid = element('table', undefined, 'progress-table');
  const head = element('tr'); headers.forEach(title => head.append(element('th', title)));
  const thead = element('thead'); thead.append(head); const body = element('tbody');
  rows.forEach(values => { const row = element('tr'); values.forEach((value,index) => { const cell = element('td');cell.dataset.label=headers[index]; if (value instanceof Node) cell.append(value); else cell.textContent = value ?? '—'; row.append(cell); }); body.append(row); });
  grid.append(thead, body); wrapper.append(grid); return wrapper;
}
function summaryCards(summary, app) {
  const cards = element('div', undefined, 'progress-cards');
  const pairs = [['总数',summary.total],['完成比例',summary.completion_percent + '%'],...(app==='exploration'?['not_started','draft','submitted','technical']:['pending','in_progress','complete']).map(key=>[stateNames[key],summary.states[key]||0])];
  for (const [title, value] of pairs) { const card=element('div',undefined,'card'); card.append(element('span',title,'muted'),element('strong',String(value))); cards.append(card); }
  return cards;
}
export function setupProgress({app, user, onOpen, onLeave = async()=>{}, onNext=null}) {
  const root=$('workspace'), work=element('div'); work.id='work-view';
  while(root.firstChild) work.append(root.firstChild);
  const navigation=element('nav',undefined,'platform-nav'), dashboard=element('section',undefined,'progress-dashboard');
  root.append(navigation,dashboard,work);
  let mode='overview', data, busy=false;
  const openCases=new Set();
  const filters={title:'',status:'',owner:'',reviewer:'',cohort:user.is_admin?'0':user.is_test?'1':'0'};
  const buttons=new Map();
  const choices=[['overview','概览 · Overview'],['mine','任务进度 · Task progress'],['tasks',app==='exploration'?'探索任务 · Explore tasks':'复核任务 · Review tasks']];
  if(user.is_admin) choices.push(['all','人员与整体进度']);
  for(const [id,label] of choices) { const button=element('button',label); button.onclick=()=>navigate(id); navigation.append(button);buttons.set(id,button);button.setAttribute('aria-pressed',String(id===mode)); }
  async function nextTask(){try{await onLeave();if(await onNext())showWork();}catch(error){message(error.message,true);}}
  if(app==='exploration'&&onNext){const next=element('button','自动领取下一题 · Next','primary');next.onclick=nextTask;navigation.append(next);}
  const heading=element('h2'), note=element('p',undefined,'muted'), toolbar=element('div',undefined,'progress-filters'), content=element('div');
  const status=element('p','正在加载…','muted');
  const pageHeading=element('div',undefined,'overview-heading'); const headingCopy=element('div'); const eyebrow=element('span',app==='exploration'?'EXPLORATION WORKSPACE':'EVALUATION WORKSPACE','eyebrow'); headingCopy.append(eyebrow,heading,note); pageHeading.append(headingCopy,status); dashboard.append(pageHeading,toolbar,content);
  const back=element('button','← 返回任务列表','back-to-tasks'); back.onclick=()=>navigate('tasks'); work.prepend(back);
  function scope(){return mode==='overview'?'overview':mode==='all'?'all':'assigned';}
  async function refresh(){
    if(busy || dashboard.hidden)return;busy=true;status.textContent='正在刷新…';
    try { data=await api('/api/progress?scope='+scope()+'&cohort='+filters.cohort); render();status.textContent='更新时间：'+new Date().toLocaleTimeString(); }
    catch(error){status.textContent=error.message;message(error.message,true);}finally{busy=false;}
  }
  async function navigate(next){
    try {
      if(next==='work'){ if(work.dataset.open){showWork();return;} next='tasks'; }
      await onLeave();
      if (next !== mode) { filters.owner='';filters.reviewer='';filters.status=''; if(next==='all'||['overview','mine'].includes(next)&&user.is_admin)filters.cohort='0';else filters.cohort=user.is_test?'1':'0'; }
      mode=next;work.hidden=true;dashboard.hidden=false;for(const [key,button] of buttons)button.setAttribute('aria-pressed',String(key===mode));
      content.replaceChildren();await refresh();
    }catch(error){message(error.message,true);}
  }
  function showWork(){work.dataset.open='1';work.hidden=false;dashboard.hidden=true;for(const [key,button]of buttons)button.setAttribute('aria-pressed',String(key==='tasks'));}
  function filter(key,label,values){
    const field=element('label',label),select=element('select');select.setAttribute('aria-label',label);
    select.append(new Option('全部',''));for(const value of [...new Set(values.filter(Boolean))].sort())select.append(new Option(key==='status'?(stateNames[value]||value):value,value));
    if (filters[key] && !values.includes(filters[key])) filters[key]='';
    select.value=filters[key];select.onchange=()=>{filters[key]=select.value;render();};field.append(select);toolbar.append(field);
  }
  function render(){
    dashboard.dataset.view=mode; heading.textContent=mode==='overview'?'一起推进场景探索与复核。':mode==='mine'?'题目进度':mode==='tasks'?(app==='exploration'?'探索任务':'复核任务'):'人员与整体进度';
    note.textContent=app==='exploration'?'按已分配 case 统计；重复探索不重复计为完成。技术问题单列。':'按已接收的最终答案统计，全部报告评完才算完成；不包含尚未提交的探索任务。';
    toolbar.replaceChildren(); toolbar.hidden=false;
    if(mode==='mine'){const cases=groupCases(data.group,data.rows);filter('title','环境',cases.map(row=>row.title));filter('status','题目状态',cases.map(row=>row.status));}
    else if(mode!=='overview'){filter('title','环境',data.rows.map(row=>row.title));filter('status','状态',data.rows.map(row=>row.status));}
    if(!['overview','mine'].includes(mode)&&(mode==='all'||app==='evaluation'))filter('owner','探索者',data.rows.map(row=>row.owner));
    if(!['overview','mine'].includes(mode)&&app==='evaluation')filter('reviewer','复核员',data.rows.map(row=>row.reviewer));
    if(user.is_admin){const field=element('label','数据组'),select=element('select');select.append(new Option('正式人员','0'),new Option('QA / 验收','1'));select.value=filters.cohort;select.onchange=()=>{filters.cohort=select.value;refresh();};field.append(select);toolbar.append(field);}
    const reload=element('button','刷新');reload.onclick=refresh;toolbar.append(reload);
    let rows=data.rows.filter(row=>['title','status','owner','reviewer'].every(key=>!filters[key]||row[key]===filters[key]));
    // Queue excludes completed rows by default; completed work stays in My reviews.
    if(app==='exploration'&&data.guided_exploration&&mode==='tasks')rows=rows.filter(row=>row.human_eligible);
    if(app==='evaluation'&&mode==='tasks'&&!filters.status)rows=rows.filter(row=>row.status!=='complete');
    content.replaceChildren();
    if(mode==='mine'){renderCaseProgress();return;}
    if(mode==='all'){
      if(app==='exploration'){note.textContent='总体进度按不同题目统计：至少一人正常提交即计入探索覆盖，不要求所有有权限的人完成。下方仅列实际参与记录，筛选只影响记录列表。';renderGroupOverview();}
      else content.append(summaryCards(data.summary,app));
    }
    if(mode==='overview'){
      heading.textContent='团队完成概览';
      note.textContent=(data.cohort?'QA / 验收':'正式人员')+' · 当前可访问题目的团队进度。人数按完成提交去重；领取或打开不算完成。';
      if(app==='exploration'){
        heading.textContent='探索环境，发现并记录 bug';
        note.textContent='根据本题的 bug 类型提示自由探索，提交截图与描述；未找到可以放弃，再领取下一题。';
        renderExplorerWelcome();
        const statistics=element('details',undefined,'team-statistics');statistics.append(element('summary','查看团队进度与环境排队情况'));
        const first=content.childNodes.length;renderGroupOverview();while(content.childNodes.length>first)statistics.append(content.childNodes[first]);
        content.append(statistics);return;
      }
      renderGroupOverview();
      const next=element('section',undefined,'overview-next card');const copy=element('div');copy.append(element('h3',app==='exploration'?'开始一次探索':'开始一份复核'),element('p',app==='exploration'?'任务列表保留你的草稿和历史提交，可随时继续。':'任务进度按题目汇总；展开题目后查看答案及复核状态。','muted'));const open=element('button',app==='exploration'?'浏览探索任务 →':'浏览复核任务 →','primary');open.onclick=()=>navigate('tasks');next.append(copy,open);content.append(next);return;
    }
    if(app==='evaluation'&&mode!=='tasks'){
      const distributions=element('div',undefined,'progress-distributions');
      for(const [key,title]of [['bugs','Bug 判定（按报告）'],['categories','类别复核（按报告）'],['no_bug','未发现 bug 的答案']]){
        const block=element('section',undefined,'card');block.append(element('h3',title));const entries=Object.entries(data.distribution[key]),total=entries.reduce((n,[,v])=>n+v,0);
        if(!total)block.append(element('p','暂无已保存判定','muted'));
        for(const [value,n]of entries)block.append(element('p',(verdictNames[value]||value)+'：'+n+'（'+(100*n/total).toFixed(1)+'%）'));
        distributions.append(block);
      }const details=element('details',undefined,'distribution-details');details.append(element('summary','查看判定分布'),distributions);content.append(details);
    }
    if(app==='exploration'&&mode==='tasks')note.textContent='优先点击 Next 自动领取有效提交不足两人的题目。领取后请提交或放弃，再领取下一题；草稿与历史答案可在下方查看。控制题仅保留历史记录，不再分配。';
    if(app==='exploration'&&mode==='all')rows=rows.filter(row=>row.status!=='not_started');
    content.append(element('p','共 '+rows.length+' 条'+(mode==='all'?(app==='exploration'?' 条件内的实际参与记录；同一题可有多人参与':' · 概览统计当前页面范围的全部记录'):''),'muted'));
    const values=rows.map(row=>{
      const action=element('button',app==='exploration'?(row.latest_status==='draft'?'继续探索':row.attempt_id?'查看答案':'开始探索'):(row.status==='complete'?'查看 / 修订':row.mine?'继续复核':'领取'));
      action.disabled=!row.can_open || (row.human_eligible===false&&!row.attempt_id);action.onclick=async()=>{action.disabled=true;try{await onLeave();await onOpen(row);showWork();}catch(error){message(error.message,true);}finally{action.disabled=!row.can_open;}};
      const actions=element('div');actions.append(action);
      if(app==='exploration'&&row.history?.length>1&&row.can_open){
        const history=element('details');history.append(element('summary','历史尝试（'+row.history.length+'）'));
        for(const attempt of row.history){const open=element('button',stateNames[attempt.status]+' · '+date(attempt.created));open.onclick=async()=>{try{await onLeave();await onOpen({...row,attempt_id:attempt.id});showWork();}catch(error){message(error.message,true);}};history.append(open);}
        actions.append(history);
      }
      if(app==='exploration'&&mode==='tasks')return [actions,row.title,row.id.slice(0,8).toUpperCase(),stateNames[row.status],row.report_count+' / '+row.flag_count,date(row.updated)];
      return app==='exploration'?[row.id.slice(0,8).toUpperCase(),row.title,...(mode==='all'?[row.owner]:[]),stateNames[row.status],number(row.case_progress?.completed_explorers),number(row.case_progress?.reviewer_count),row.report_count+' / '+row.flag_count,date(row.updated),date(row.submitted_at),actions]:
        [row.id.slice(0,8).toUpperCase(),row.title+' / '+row.case_id,row.owner,row.outcome==='none'?'未发现 bug':row.report_count+' 条报告',stateNames[row.status],row.reviewer||'—',number(row.case_progress?.reviewer_count),ratio(row.case_progress?.reviewed_answers,row.case_progress?.received_answers),date(row.submitted_at),date(row.updated),actions];
    });
    if(app==='exploration'&&mode==='tasks'){const list=table(['操作','环境','任务编号','状态','报告 / 截图','最近活动'],values);list.classList.add('personal-task-list');content.append(list);}
    else content.append(table(app==='exploration'?['任务','环境',...(mode==='all'?['探索者']:[]),'状态','已提交探索人数','本题复核人数','报告 / 截图','最近活动','提交时间','操作']:['答案','环境 / case','探索者','内容','状态','复核员','本题复核人数','复核答案（完成 / 收到）','提交时间','最近活动','操作'],values));
    if(!rows.length)content.append(element('p',app==='exploration'&&mode==='all'?'当前筛选下暂无实际参与记录。拥有题目访问权限不计为开始或完成。':'当前没有符合条件的任务。尚未分配任务的账号可以登录，但无法进入环境或读取参考答案。','empty'));
    if(mode==='all'){
      content.append(element('h3',app==='exploration'?'人员参与情况':'人员进度'));
      if(app==='exploration'){
        content.append(table(['用户','已提交题目数','草稿题目数','技术问题','最近活动'],data.people.filter(person=>person.assigned_cases>0||person.completed>0||person.technical_count>0).map(person=>{
          const name=element('button',person.name);name.onclick=()=>{filters.owner=person.name;render();};
          return [name,person.completed,person.states.draft||0,person.technical_count,date(person.last_activity)];
        })));
        content.append(element('p','人数与参与记录只描述实际投入，不设每人或每题的完成配额。','muted'));
      } else {
      content.append(table(['用户','已分配 case','当前记录数','已完成','进行中','技术问题','完成比例','最近活动'],data.people.map(person=>{
        const name=element('button',person.name);name.onclick=()=>{filters[app==='exploration'?'owner':'reviewer']=person.name;render();};
        return [name,person.assigned_cases,person.total,person.completed,(person.states.draft||0)+(person.states.in_progress||0),person.technical_count,person.completion_percent+'%',date(person.last_activity||person.last_seen)];
      })));
      content.append(element('p','复核按 case 分配到复核组，答案领取后归具体复核员；未领取答案不会重复计入每个人的待办。','muted'));
      }
    }
  }
  function renderExplorerWelcome(){
    const intro=element('section',undefined,'explorer-welcome card');
    intro.append(element('h3','第一次使用？按这四步完成一份探索'),element('p','自动分配的每道题都有已标注的 bug。任务页提供真实 bug 类型和该类定义，你需要自行定位、验证并记录证据。','muted'));
    const steps=element('ol',undefined,'explorer-steps');
    for(const [title,description,english] of [
      ['选择一道题','点击 Next 自动领取题目，系统优先补齐两位不同用户的有效提交；阅读 bug 类型提示后点击 Start session。','Select Next for an assigned task. Read the ground-truth category hint, then select Start session.'],
      ['自由探索并保存证据','点击场景控制角色，W/A/S/D 移动、鼠标观察。发现疑似异常时按 F 或点击 Flag 截图；Esc 释放鼠标。','Explore with WASD and the mouse. Use F / Flag for evidence; Esc releases the mouse.'],
      ['描述发现并关联截图','每个独立异常添加一条报告，选择 bug 类型，写清位置、复现步骤、实际与预期表现，并勾选证据截图。','Add one report per issue, select its category, describe reproduction and expected behavior, and attach screenshots.'],
      ['结束会话，再提交答案','End session 释放环境，草稿和截图保留。默认填写并提交 bug 报告；未找到时可放弃本题。提交或放弃后自动分配下一题，已提交答案不能修改。','End session releases the environment without submitting. Submit your report or give up if you cannot find the bug; the next task is then assigned.']
    ]){const item=element('li');item.append(element('strong',title),element('p',description),element('small',english,'muted'));steps.append(item);}
    const choose=element('button','自动领取下一题 · Next','primary');choose.onclick=onNext?nextTask:()=>navigate('tasks');intro.append(choose,steps);
    intro.append(element('p','建议使用 Next，每题以两位不同用户的有效正式提交为目标；草稿、运行中、放弃和技术问题不计入。领取后请提交或放弃，再切换题目。详细说明可下载给 LLM agent。','muted'));
    content.append(intro);
  }
  function openRecord(row,label){
    const button=element('button',label);button.disabled=!row.can_open;
    button.onclick=async()=>{button.disabled=true;try{await onLeave();await onOpen(row);showWork();}catch(error){message(error.message,true);}finally{button.disabled=!row.can_open;}};
    return button;
  }
  function caseRecords(item){
    const section=element('section',undefined,'case-records');
    section.append(element('h3',app==='exploration'?'我的探索记录':'本题的答案与复核记录'));
    section.append(element('p',app==='exploration'?'此处只显示你自己的记录；上方人数统计包含该题的所有参与者。':'每份答案独立领取和复核；同一题可以有多份答案。这里只显示当前账号有权访问的记录。','muted'));
    if(!item.records.length){section.append(element('p',app==='exploration'?'你还没有开始这道题，可到探索任务页开始。':item.received_answers>0?'本题已有答案，但当前账号没有可查看的记录。':'尚未收到这道题的答案。','empty'));return section;}
    const rows=[];
    for(const row of item.records){
      if(app==='exploration'){
        const attempts=row.history?.length?row.history:[null];
        for(const attempt of attempts){
          const record=attempt?{...row,attempt_id:attempt.id}:row;
          const state=attempt?.status || row.latest_status || row.status;
          rows.push([attempt?attempt.id.slice(0,8).toUpperCase():'尚未开始',stateNames[state]||state,date(attempt?.created || row.updated),openRecord(record,state==='draft'?'继续探索':attempt?'查看我的答案':'开始探索')]);
        }
      } else {
        const label=!row.can_open?'其他人负责':row.status==='complete'?'查看 / 修订':row.mine?'继续复核':'领取答案';
        rows.push([row.id.slice(0,8).toUpperCase(),row.owner,stateNames[row.status],row.reviewer||'—',date(row.submitted_at),openRecord(row,label)]);
      }
    }
    section.append(table(app==='exploration'?['我的尝试','状态','时间','操作']:['答案','提交者','复核状态','复核员','提交时间','操作'],rows));
    return section;
  }
  function renderCaseProgress(){
    note.textContent=(data.cohort?'QA / 验收':'正式人员')+' · 一道题一行，汇总多人探索和多份答案的复核进度。展开后查看个人记录。';
    const all=groupCases(data.group,data.rows),cases=all.filter(row=>(!filters.title||row.title===filters.title)&&(!filters.status||row.status===filters.status));
    content.append(element('p','共 '+all.length+' 题，当前显示 '+cases.length+' 题。人数按不同账号去重，优先补齐每题两位不同用户的有效正式提交。“当前答案已复核”仅表示现有提交均已送达并复核，仍可继续探索和提交。','muted'));
    if(data.group&&!data.group.peer_available)content.append(element('p','部分统计暂不可用，以 — 显示。','muted'));
    const wrapper=element('div',undefined,'progress-table-wrap'),grid=element('table',undefined,'progress-table case-progress-table');
    const head=element('tr');for(const label of ['题目','环境','已提交探索人数','提交答案数','已复核 / 收到答案','复核人数','题目状态','记录'])head.append(element('th',label));
    const thead=element('thead');thead.append(head);grid.append(thead);const body=element('tbody');
    for(const item of cases){
      const row=element('tr'),toggle=element('button',openCases.has(item.id)?'收起记录':'展开记录');toggle.setAttribute('aria-label','展开题目 '+item.id.slice(0,8).toUpperCase()+' 的记录');
      const details=element('tr',undefined,'case-detail-row'),cell=element('td');cell.colSpan=8;cell.append(caseRecords(item));details.append(cell);details.hidden=!openCases.has(item.id);
      const detailId='case-records-'+item.id;details.id=detailId;toggle.setAttribute('aria-controls',detailId);toggle.setAttribute('aria-expanded',String(!details.hidden));
      toggle.onclick=()=>{details.hidden=!details.hidden;toggle.textContent=details.hidden?'展开记录':'收起记录';toggle.setAttribute('aria-expanded',String(!details.hidden));if(details.hidden)openCases.delete(item.id);else openCases.add(item.id);};
      for(const value of [item.id.slice(0,8).toUpperCase(),item.title,number(item.completed_explorers),number(item.submitted_answers),ratio(item.reviewed_answers,item.received_answers),number(item.reviewer_count),item.status,toggle]){const td=element('td');if(value instanceof Node)td.append(value);else td.textContent=value;row.append(td);}body.append(row,details);
    }
    grid.append(body);wrapper.append(grid);content.append(wrapper);
    if(!cases.length)content.append(element('p','当前没有符合条件的题目。','empty'));
  }
  function renderGroupOverview(){
    const group=data.group;if(!group)return;
    const summary=group.summary;
    // completed_explorers is already deduplicated by account in the API.
    const coverageKnown=group.cases.every(row=>row.completed_explorers!=null);
    const twoPersonCases=coverageKnown?group.cases.filter(row=>row.completed_explorers>=2).length:null;
    const onePersonCases=coverageKnown?group.cases.filter(row=>row.completed_explorers===1).length:null;
    const zeroPersonCases=coverageKnown?group.cases.filter(row=>row.completed_explorers===0).length:null;
    const twoPersonPercent=twoPersonCases==null?'—':(summary.total_cases?100*twoPersonCases/summary.total_cases:0).toFixed(1)+'%';
    if(data.runtime_capacity){const c=data.runtime_capacity;content.append(element('h3','Unreal live queue'),element('p',c.running+' / '+c.capacity+' slots in use · 排队 '+c.queued+' 人'+(c.legacy_busy?' · audit 使用 GPU，探索等待中':'')+'。Three.js 不占 GPU 槽位；每账号同时一个会话。','muted'));}
    if(!group.peer_available)content.append(element('p','另一平台的统计暂时不可用，相关数据以 — 显示；不会记为 0。','muted'));
    function section(title,pairs){
      content.append(element('h3',title,'group-section-title'));
      const cards=element('div',undefined,'progress-cards');
      for(const [label,value,hint] of pairs){const card=element('div',undefined,'card');card.append(element('span',label,'muted'),element('strong',value),element('small',hint,'muted'));cards.append(card);}content.append(cards);
    }
    section('探索完成情况',[
      ['题目总数',number(summary.total_cases),'当前可访问的不同题目'],
      ...(app==='exploration'?[
        ['两人完成题数',ratio(twoPersonCases,summary.total_cases),'至少两位不同用户已正式提交；草稿、放弃和技术问题不计入'],
        ['两人完成率',twoPersonPercent,'已有两位不同用户提交的题目 / 题目总数'],
        ['还差一人',number(onePersonCases),'恰好一位用户已正式提交'],
        ['尚无人提交',number(zeroPersonCases),'尚无有效正式提交的题目']
      ]:[]),
      ['已有人完成探索',ratio(summary.explored_cases,summary.total_cases),'至少一位探索者已提交'],
      ['当前答案全部已复核',ratio(summary.fully_reviewed_cases,summary.total_cases),'已有提交且全部送达并复核；允许继续提交'],
      ['放弃人次',number(summary.skipped_explorers),'未找到并放弃，不计入已提交覆盖'],
      ['探索参与人次',number(summary.completed_explorers),'同一人、同一题只计一次；目标为每题两位不同用户'],
      ['探索覆盖率',summary.exploration_percent==null?'—':summary.exploration_percent+'%','已有探索提交的题目 / 题目总数']
    ]);
    section('复核完成情况',[
      ['已有人完成复核',ratio(summary.reviewed_cases,summary.total_cases),'至少一位复核员已保存判定'],
      ['已复核答案',ratio(summary.reviewed_answers,summary.received_answers),'按收到的最终答案统计'],
      ['待领取答案',number(summary.pending_answers),'尚无有效领取者'],
      ['正在复核',number(summary.active_reviews),'已领取，尚未完成'],
      ['复核完成率',summary.review_percent==null?'—':summary.review_percent+'%','已复核答案占收到答案的比例']
    ]);
    const environments=new Map();
    for(const row of group.cases){let e=environments.get(row.title);if(!e){e={title:row.title,total:0,explored:0,reviewed:0};environments.set(row.title,e);}e.total++;e.explored+=row.completed_explorers>0?1:0;e.reviewed+=row.reviewer_count>0?1:0;}
    content.append(element('h3','按环境查看','group-section-title'));
    content.append(table(['环境','题目数','已有探索提交','已有复核'],[...environments.values()].map(e=>[e.title,e.total,summary.explored_cases==null?'—':ratio(e.explored,e.total),summary.reviewed_cases==null?'—':ratio(e.reviewed,e.total)])));
    const browse=element('button','查看逐题进度 →','primary');browse.onclick=()=>navigate('mine');content.append(browse);
  }
  work.hidden=true;refresh();setInterval(refresh,30000);
  return {refresh,showWork,navigate};
}
