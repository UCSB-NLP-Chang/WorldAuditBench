import {api, $, element, message} from '/static/common.js';
import {groupCases} from '/static/case-progress.js';

const stateNames = {not_started:'未开始',draft:'探索中',submitted:'已提交',technical:'技术问题',pending:'待领取',in_progress:'评测中',complete:'已完成'};
const verdictNames = {correct:'正确',partial:'部分正确',incorrect:'不正确',insufficient:'证据不足',additional_bug:'额外 bug',correct_none:'正确未发现',missed:'漏检',uncertain:'无法确定',not_applicable:'不适用',not_reviewed:'历史未复核'};
const number = value => value == null ? '—' : String(value);
const ratio = (a,b) => a == null || b == null ? '—' : a+' / '+b;
const date = value => value ? new Date(value * 1000).toLocaleString() : '—';
function table(headers, rows) {
  const wrapper = element('div', undefined, 'progress-table-wrap'), grid = element('table', undefined, 'progress-table');
  const head = element('tr'); headers.forEach(title => head.append(element('th', title)));
  const thead = element('thead'); thead.append(head); const body = element('tbody');
  rows.forEach(values => { const row = element('tr'); values.forEach(value => { const cell = element('td'); if (value instanceof Node) cell.append(value); else cell.textContent = value ?? '—'; row.append(cell); }); body.append(row); });
  grid.append(thead, body); wrapper.append(grid); return wrapper;
}
function summaryCards(summary, app) {
  const cards = element('div', undefined, 'progress-cards');
  const pairs = [['总数',summary.total],['完成比例',summary.completion_percent + '%'],...(app==='exploration'?['not_started','draft','submitted','technical']:['pending','in_progress','complete']).map(key=>[stateNames[key],summary.states[key]||0])];
  for (const [title, value] of pairs) { const card=element('div',undefined,'card'); card.append(element('span',title,'muted'),element('strong',String(value))); cards.append(card); }
  return cards;
}
export function setupProgress({app, user, onOpen, onLeave = async()=>{}}) {
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
    if(app==='evaluation'&&mode==='tasks'&&!filters.status)rows=rows.filter(row=>row.status!=='complete');
    content.replaceChildren();
    if(mode==='mine'){renderCaseProgress();return;}
    if(mode==='all')content.append(summaryCards(data.summary,app));
    if(mode==='overview'){
      heading.textContent='团队完成概览';
      note.textContent=(data.cohort?'QA / 验收':'正式人员')+' · 当前可访问题目的团队进度。人数按完成提交去重；领取或打开不算完成。';
      renderGroupOverview();
      const next=element('section',undefined,'overview-next card');const copy=element('div');copy.append(element('h3',app==='exploration'?'开始一次探索':'开始一份复核'),element('p',app==='exploration'?'任务列表保留你的草稿和历史提交，可随时继续。':'任务进度按题目汇总；展开题目后查看答案及复核状态。','muted'));const open=element('button',app==='exploration'?'浏览探索任务 →':'浏览复核任务 →','primary');open.onclick=()=>navigate('tasks');next.append(copy,open);content.append(next);return;
    }
    if(app==='evaluation'&&mode!=='tasks'){
      const distributions=element('div',undefined,'progress-distributions');
      for(const [key,title]of [['bugs','Bug 判定（按报告）'],['no_bug','未发现 bug 的答案']]){
        const block=element('section',undefined,'card');block.append(element('h3',title));const entries=Object.entries(data.distribution[key]),total=entries.reduce((n,[,v])=>n+v,0);
        if(!total)block.append(element('p','暂无已保存判定','muted'));
        for(const [value,n]of entries)block.append(element('p',(verdictNames[value]||value)+'：'+n+'（'+(100*n/total).toFixed(1)+'%）'));
        distributions.append(block);
      }const details=element('details',undefined,'distribution-details');details.append(element('summary','查看判定分布'),distributions);content.append(details);
    }
    content.append(element('p','共 '+rows.length+' 条'+(mode==='all'?' · 概览统计当前页面范围的全部记录':''),'muted'));
    const values=rows.map(row=>{
      const action=element('button',app==='exploration'?(row.latest_status==='draft'?'继续探索':row.attempt_id?'查看答案':'开始探索'):(row.status==='complete'?'查看 / 修订':row.mine?'继续复核':'领取'));
      action.disabled=!row.can_open;action.onclick=async()=>{action.disabled=true;try{await onLeave();await onOpen(row);showWork();}catch(error){message(error.message,true);}finally{action.disabled=!row.can_open;}};
      const actions=element('div');actions.append(action);
      if(app==='exploration'&&row.history?.length>1&&row.can_open){
        const history=element('details');history.append(element('summary','历史尝试（'+row.history.length+'）'));
        for(const attempt of row.history){const open=element('button',stateNames[attempt.status]+' · '+date(attempt.created));open.onclick=async()=>{try{await onLeave();await onOpen({...row,attempt_id:attempt.id});showWork();}catch(error){message(error.message,true);}};history.append(open);}
        actions.append(history);
      }
      return app==='exploration'?[row.id.slice(0,8).toUpperCase(),row.title,...(mode==='all'?[row.owner]:[]),stateNames[row.status],number(row.case_progress?.completed_explorers),number(row.case_progress?.reviewer_count),row.report_count+' / '+row.flag_count,date(row.updated),date(row.submitted_at),actions]:
        [row.id.slice(0,8).toUpperCase(),row.title+' / '+row.case_id,row.owner,row.outcome==='none'?'未发现 bug':row.report_count+' 条报告',stateNames[row.status],row.reviewer||'—',number(row.case_progress?.reviewer_count),ratio(row.case_progress?.reviewed_answers,row.case_progress?.received_answers),date(row.submitted_at),date(row.updated),actions];
    });
    content.append(table(app==='exploration'?['任务','环境',...(mode==='all'?['探索者']:[]),'状态','已提交探索人数','本题复核人数','报告 / 截图','最近活动','提交时间','操作']:['答案','环境 / case','探索者','内容','状态','复核员','本题复核人数','复核答案（完成 / 收到）','提交时间','最近活动','操作'],values));
    if(!rows.length)content.append(element('p','当前没有符合条件的任务。尚未分配任务的账号可以登录，但无法进入环境或读取参考答案。','empty'));
    if(mode==='all'){
      content.append(element('h3','人员进度'));
      content.append(table(['用户','已分配 case','当前记录数','已完成','进行中','技术问题','完成比例','最近活动'],data.people.map(person=>{
        const name=element('button',person.name);name.onclick=()=>{filters[app==='exploration'?'owner':'reviewer']=person.name;render();};
        return [name,person.assigned_cases,person.total,person.completed,(person.states.draft||0)+(person.states.in_progress||0),person.technical_count,person.completion_percent+'%',date(person.last_activity||person.last_seen)];
      })));
      content.append(element('p','复核按 case 分配到复核组，答案领取后归具体复核员；未领取答案不会重复计入每个人的待办。','muted'));
    }
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
    content.append(element('p','共 '+all.length+' 题，当前显示 '+cases.length+' 题。人数按不同账号去重，不设每题探索人数要求。“当前答案已复核”仅表示现有提交均已送达并复核，仍可继续探索和提交。','muted'));
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
    if(!group.peer_available)content.append(element('p','另一平台的统计暂时不可用，相关数据以 — 显示；不会记为 0。','muted'));
    function section(title,pairs){
      content.append(element('h3',title,'group-section-title'));
      const cards=element('div',undefined,'progress-cards');
      for(const [label,value,hint] of pairs){const card=element('div',undefined,'card');card.append(element('span',label,'muted'),element('strong',value),element('small',hint,'muted'));cards.append(card);}content.append(cards);
    }
    section('探索完成情况',[
      ['题目总数',number(summary.total_cases),'当前可访问的不同题目'],
      ['已有人完成探索',ratio(summary.explored_cases,summary.total_cases),'至少一位探索者已提交'],
      ['当前答案全部已复核',ratio(summary.fully_reviewed_cases,summary.total_cases),'已有提交且全部送达并复核；允许继续提交'],
      ['探索参与人次',number(summary.completed_explorers),'同一人、同一题只计一次，不设人数配额'],
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
