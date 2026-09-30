import {renderExample} from '/static/example.js?v=icl-boxes-v23';
import {setupProgress} from '/static/progress.js?v=binary-review-v2-20260917';
import {api, $, element, message, imagePreview, initialize} from '/static/common.js';
let categoryNames = {other: '其他', unsure: '不确定 / 旧答案未分类'};
let progressView;
let taxonomy, reviewLanguage = 'zh';
let current = null, answers = [], user, reviewBusy = false;
const labels = {correct: '正确', partial: '部分正确', incorrect: '不正确', insufficient: '证据不足', additional_bug: '疑似额外真实 bug', correct_none: '正确未发现', missed: '漏检'};
const key = () => 'bf-judgment-v2:' + user.name + ':' + current.submission.id;
function cache() { localStorage.setItem(key(), JSON.stringify({revision: current.revision, answers})); }
async function refresh() {
  const queue = await api('/api/queue'); $('queue').replaceChildren();
  if (!queue.items.length) $('queue').append(element('p', '暂无答案。探索者完成提交后，答案和截图会自动送达这里。', 'empty'));
  queue.items.forEach(item => {
    const button = element('button', item.id.slice(0, 8).toUpperCase() + ' · ' + (item.state === 'complete' ? '已完成' : item.mine ? '我正在评测' : item.available ? '待领取' : '评测中'));
    button.disabled = !item.available && !item.mine; button.onclick = () => claim(item.id).catch(error=>message(error.message,true)); $('queue').append(button);
  });
}
async function claim(id) {
  if(reviewBusy)return false;
  busyReview(true);
  try {
    if (current) cache();
    const detail = await api('/api/claim', id ? {id} : {});
    await openReview(detail); return true;
  } catch (error) { message(error.message, true); throw error; }
  finally { busyReview(false); }
}
async function openReview(detail) {
    current = detail;
    const originals = current.judgment?.answers || [];
    const ids = current.submission.outcome === 'none' ? ['none'] : current.submission.reports.map(r => r.id);
    answers = ids.map(report_id => {
      const old = originals.find(a => a.report_id === report_id);
      if (current.judgment?.judgment_version === 2 && old) return {...old};
      const verdict = {correct:'correct', correct_none:'correct', partial:'correct', incorrect:'incorrect', missed:'incorrect', additional_bug:'incorrect'}[old?.verdict] || '';
      const reason_code = old?.verdict === 'missed' ? 'missed_bug' : old?.verdict === 'additional_bug' ? 'off_target' : verdict === 'correct' && old?.category_verdict === 'incorrect' ? 'category_mismatch' : '';
      return {report_id, verdict, reason_code};
    });
    try { const cached = JSON.parse(localStorage.getItem(key()) || 'null'); if (cached?.revision === current.revision && Array.isArray(cached.answers) && cached.answers.length === ids.length && ids.every(id => cached.answers.filter(a => a.report_id === id).length === 1)) answers = cached.answers; } catch {}
    render(); await refresh(); progressView?.showWork(); message('');
}
function busyReview(value) {
  reviewBusy=value;
  for(const id of ['claim','save','save-next','correct-next','next-review','auto-next-review']) { const button=$(id);if(button)button.disabled=value; }
}
async function nextReview() {
  if(reviewBusy)return;
  busyReview(true);
  try {
    if(current)cache();
    const next=await api('/api/next',{exclude_submission_id:current?.submission.id});
    if(next.unavailable){message(next.message);return;}
    await openReview(next);
  } catch(error){message(error.message,true);}
  finally{busyReview(false);}
}
function render() {
  $('evaluation').hidden = false; $('query').textContent = current.submission.query;
  $('exploration-protocol').textContent=current.submission.exploration_protocol==='category_guided_v1'?'探索方式：已向测试者提供 ground-truth 类型提示（'+(current.submission.provided_categories||[]).map(c=>categoryNames[c]||c).join('、')+'），未提供具体 rubric。':'历史答案：未提供本次新增的类型提示。';
  renderExample($('task-example'),current.submission.task_version_id,reviewLanguage,true);
  $('rubric').textContent = current.reference.rubric;
  $('version').textContent = 'Case: ' + current.reference.case_id + '\nRevision: ' + current.reference.case_revision + '\nBuild SHA256: ' + current.reference.build_sha256 + '\nRubric SHA256: ' + current.reference.rubric_sha256;
  $('review-status').textContent = current.state === 'complete' ? '已完成 · 可修订' : '已领取';
  $('submission-id').textContent = '答案 ' + current.submission.id.slice(0, 8).toUpperCase() + ' · ' + new Date(current.submission.submitted_at * 1000).toLocaleString();
  $('history').textContent = current.revision ? '已保存版本 ' + current.revision + ' · 历史记录 ' + current.history.length + ' 条' : '请选择正确或不正确；不正确时选择一个原因';
  $('answers').replaceChildren();
  answers.forEach((answer, index) => {
    const report = current.submission.reports.find(r => r.id === answer.report_id);
    const card = element('article', undefined, 'card report'); card.append(element('h3', report ? 'Bug ' + (index + 1) : '未发现 bug'));
    if (report) {
      const code = report.category || 'unsure';
      card.append(element('p', '探索者选择的类别：' + (categoryNames[code] || code), 'category-hint'));
      const group = taxonomy.categories.find(g => g.id === (taxonomy.legacy[code]?.group || code));
      if (group) { const definition = element('details'); definition.append(element('summary', '类别定义 / Category definition'), element('p', group.description.zh), element('p', group.description.en)); card.append(definition); }
    }
    card.append(element('div', report?.description || '探索者提交：没有发现 bug。', 'answer-text'));
    const images = element('div', undefined, 'answer-images');
    (report?.evidence_ids || []).forEach((id, i) => { const figure = element('figure'); figure.append(imagePreview('/api/evidence/' + id, '位置参考 ' + (i + 1)), element('figcaption', '位置参考 ' + (i + 1) + ' · ' + id.slice(0, 8), 'muted')); images.append(figure); });
    card.append(images);
    const fields = element('div', undefined, 'judgment-fields');
    const label = element('label', report ? 'Bug 判定' : '“未发现 bug”的结论是否正确');
    const select = element('select'); select.setAttribute('aria-label', '判定 ' + (index + 1));
    select.append(new Option('请选择判定', ''), new Option('正确', 'correct'), new Option('不正确', 'incorrect'));
    select.value = answer.verdict;
    const reasonLabel = element('label'); const reason = element('select'); reason.setAttribute('aria-label', '原因 ' + (index + 1));
    const reasonTitle = element('span'); const reasonHelp = element('p', '', 'muted reason-help'); reasonLabel.append(reasonTitle, reason, reasonHelp);
    function updateReasonHelp() { reasonHelp.textContent = current.judgment_options[answer.verdict]?.[answer.reason_code] || ''; reasonHelp.hidden = !reasonHelp.textContent; }
    function updateReasons() {
      const incorrect = answer.verdict === 'incorrect';
      reasonTitle.textContent = incorrect ? '原因（必选一项）' : '原因（可选，默认无需选择）';
      reason.replaceChildren(new Option(incorrect ? '请选择一个错误原因' : '无需选择', ''));
      for (const [code, name] of Object.entries(current.judgment_options[answer.verdict] || {})) reason.append(new Option(name, code));
      reason.value = answer.reason_code || ''; reason.required = incorrect; reason.disabled = !answer.verdict; updateReasonHelp();
    }
    select.onchange = () => { answer.verdict = select.value; answer.reason_code = ''; updateReasons(); cache(); };
    reason.onchange = () => { answer.reason_code = reason.value; updateReasonHelp(); cache(); };
    updateReasons(); label.append(select); fields.append(label, reasonLabel); card.append(fields);
    const old = current.judgment?.judgment_version !== 2 && current.judgment?.answers.find(a => a.report_id === answer.report_id);
    if (old) {
      const legacy = element('details'); legacy.append(element('summary', '查看旧版判定与理由'));
      legacy.append(element('p', '原判定：' + (labels[old.verdict] || old.verdict)), element('p', old.reason || '未填写理由'));
      if (old.category_verdict) legacy.append(element('p', '原类别复核：' + ({correct:'类别正确',incorrect:'类别选错',uncertain:'无法确定',not_applicable:'不适用',not_reviewed:'未复核'}[old.category_verdict] || old.category_verdict) + (old.corrected_category ? ' · 建议类别：' + (categoryNames[old.corrected_category] || old.corrected_category) : '')));
      legacy.append(element('p', '旧记录原样保留；保存后会新增二元判定版本。', 'muted')); card.append(legacy);
    }
    $('answers').append(card);
  });
}
function renderReviewGuide() {
  const lang = reviewLanguage;
  for (const code of ['zh','en']) $('review-' + code).setAttribute('aria-pressed', String(code === lang));
  const instructions = lang === 'zh' ? [
    '结合 Query 和 ground-truth rubric 核对探索者描述，只选择“正确”或“不正确”。',
    '描述命中目标异常即可判正确。表述简短或次要细节不完整，但核心异常正确的，也判正确。触发条件或影响描述只有改变核心异常结论时才判错。',
    '截图仅作为发现位置的参考，无需独立证明 bug；不要因为缺少动态画面或截图未完整呈现异常而判错。',
    '正确默认无需选原因；如类别选错，可在同一个原因列表中备注，类别选错本身不导致 bug 判错。',
    '不正确时选择一个最主要的错误原因，无需另写文字。报告其他问题而未命中目标 bug 时，选择“未命中目标 bug”。',
    '“未发现 bug”的结论也使用二元判定；目标异常存在而未发现时，选“不正确”和“漏检”。保存后可修订，历史版本保留。'
  ] : [
    'Compare the description with the query and ground-truth rubric. Choose Correct or Incorrect.',
    'Mark Correct when the description identifies the target anomaly, including brief descriptions or missing minor details whose core observation is correct. Errors about triggers or impact are incorrect only when they change the core anomaly conclusion.',
    'Screenshots are location references. They do not need to prove the bug independently; missing motion or incomplete visual coverage is not a reason to reject the report.',
    'Correct requires no reason by default. A wrong category can be noted in the same optional reason list and does not by itself make the bug incorrect.',
    'For Incorrect, select the main error reason. No written explanation is required. Use the off-target reason when the report describes another issue instead of the target bug.',
    'A no-bug answer also receives a binary verdict. Choose Incorrect and Missed bug when the target anomaly was missed. Saved judgments can be revised; history is retained.'
  ];
  const list = element('ol'); instructions.forEach(text => list.append(element('li', text))); $('review-instructions').replaceChildren(list);
  $('review-taxonomy').replaceChildren(element('h3', lang === 'zh' ? '与探索端一致的五类定义' : 'The same five-category taxonomy shown to explorers'), element('p', taxonomy.intro[lang]));
  for (const group of taxonomy.categories) { const details = element('details'); details.append(element('summary', group.name[lang]), element('p', group.description[lang])); $('review-taxonomy').append(details); }
  $('review-taxonomy').append(element('p', taxonomy.principle[lang], 'category-hint'));
}
for (const lang of ['zh','en']) $('review-' + lang).onclick = () => { reviewLanguage = lang; renderReviewGuide(); if(current)renderExample($('task-example'),current.submission.task_version_id,reviewLanguage,true); };

$('refresh').onclick = () => refresh().catch(error => message(error.message, true));
$('claim').onclick = nextReview;
$('next-review').onclick = nextReview;
async function saveReview(advance=false) {
  if(reviewBusy)return;
  busyReview(true);
  let saved=false;
  try {
    if (answers.some(a => !['correct', 'incorrect'].includes(a.verdict))) throw new Error('请为每条报告选择正确或不正确。');
    if (answers.some(a => a.verdict === 'incorrect' && !a.reason_code)) throw new Error('请为每条不正确的报告选择一个错误原因。');
    const id = current.submission.id; current = await api(`/api/submissions/${id}/judgment`, {judgment_version: 2, revision: current.revision, answers}); localStorage.removeItem(key()); render(); await refresh(); message('人工判定已保存。'); saved=true; }
  catch (error) { message(error.message, true); }
  finally { busyReview(false); }
  if(saved&&advance)await nextReview();
}
$('save').onclick=()=>saveReview(false);
$('save-next').onclick=()=>saveReview(true);
async function correctAndNext() {
  if (!current || reviewBusy || !answers.length) return;
  for (const answer of answers) { answer.verdict = 'correct'; answer.reason_code = ''; }
  cache();
  render();
  await saveReview(true);
}
$('correct-next').onclick = correctAndNext;
document.addEventListener('keydown', event => {
  if (event.key.toLowerCase() !== 'y' || event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
  if (event.defaultPrevented || event.repeat || event.isComposing || !current || reviewBusy) return;
  const target = event.target;
  if (target?.isContentEditable || target?.closest?.('input, textarea, select, [role="textbox"], [role="combobox"]')) return;
  const button = $('correct-next');
  if (button.disabled || !button.getClientRects().length || document.querySelector('dialog[open]')) return;
  event.preventDefault();
  button.click();
});
document.addEventListener('keydown', event => {
  if (event.key !== 'Enter' || !(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey) return;
  if (event.defaultPrevented || event.repeat || event.isComposing || !current || reviewBusy) return;
  const button = $('save-next');
  if (button.disabled || !button.getClientRects().length || document.querySelector('dialog[open]')) return;
  event.preventDefault();
  button.click();
});
initialize(async loggedIn => {
  user = loggedIn; taxonomy = await api('/api/taxonomy');
  for (const group of taxonomy.categories) categoryNames[group.id] = group.name.zh;
  for (const [code, old] of Object.entries(taxonomy.legacy)) categoryNames[code] = old.name.zh + '（历史分类）';
  renderReviewGuide();
  progressView = setupProgress({app:'evaluation',user,onLeave:async()=>{if(current)cache();},onOpen:async row=>{await claim(row.id);}});
  const nextButton=element('button','自动下一份 · Next');nextButton.id='auto-next-review';nextButton.onclick=nextReview;document.querySelector('.platform-nav').append(nextButton);
  await refresh();
  setInterval(async () => { if (!current || current.state === 'complete') return; try { await api(`/api/submissions/${current.submission.id}/heartbeat`, {}); } catch (error) { message(error.message + '；本地评测草稿已保留。', true); } }, 60000);
});
