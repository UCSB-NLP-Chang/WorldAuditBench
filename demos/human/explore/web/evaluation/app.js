import {renderExample} from '/static/example.js?v=icl-boxes-v23';
import {setupProgress} from '/static/progress.js';
import {api, $, element, message, imagePreview, initialize} from '/static/common.js';
let categoryNames = {other: '其他', unsure: '不确定 / 旧答案未分类'};
let progressView;
let taxonomy, reviewLanguage = 'zh';
let current = null, answers = [], user;
const labels = {correct: '正确，匹配 ground-truth', partial: '部分正确', incorrect: '不正确', insufficient: '证据不足', additional_bug: '疑似额外真实 bug', correct_none: '正确未发现', missed: '漏检'};
const key = () => 'bf-judgment:' + user.name + ':' + current.submission.id;
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
  try {
    if (current) cache();
    current = await api('/api/claim', id ? {id} : {});
    answers = current.judgment?.answers || (current.submission.outcome === 'none' ? [{report_id: 'none', verdict: '', reason: '', reference_item: ''}] : current.submission.reports.map(r => ({report_id: r.id, verdict: '', reason: '', reference_item: ''})));
    try { const cached = JSON.parse(localStorage.getItem(key()) || 'null'); if (cached?.revision === current.revision) answers = cached.answers; } catch {}
    render(); await refresh(); message(''); return true;
  } catch (error) { message(error.message, true); throw error; }
}
function render() {
  $('evaluation').hidden = false; $('query').textContent = current.submission.query;
  $('exploration-protocol').textContent=current.submission.exploration_protocol==='category_guided_v1'?'探索方式：已向测试者提供 ground-truth 类型提示（'+(current.submission.provided_categories||[]).map(c=>categoryNames[c]||c).join('、')+'），未提供具体 rubric。':'历史答案：未提供本次新增的类型提示。';
  renderExample($('task-example'),current.submission.task_version_id,reviewLanguage,true);
  $('rubric').textContent = current.reference.rubric;
  $('version').textContent = 'Case: ' + current.reference.case_id + '\nRevision: ' + current.reference.case_revision + '\nBuild SHA256: ' + current.reference.build_sha256 + '\nRubric SHA256: ' + current.reference.rubric_sha256;
  $('review-status').textContent = current.state === 'complete' ? '已完成 · 可修订' : '已领取';
  $('submission-id').textContent = '答案 ' + current.submission.id.slice(0, 8).toUpperCase() + ' · ' + new Date(current.submission.submitted_at * 1000).toLocaleString();
  $('history').textContent = current.revision ? '已保存版本 ' + current.revision + ' · 历史记录 ' + current.history.length + ' 条' : '请逐条选择判定并填写理由';
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
    (report?.evidence_ids || []).forEach((id, i) => { const figure = element('figure'); figure.append(imagePreview('/api/evidence/' + id, '证据 ' + (i + 1)), element('figcaption', '证据 ' + (i + 1) + ' · ' + id.slice(0, 8), 'muted')); images.append(figure); });
    card.append(images);
    const fields = element('div', undefined, 'judgment-fields');
    const label = element('label', report ? '1. Bug 是否成立' : '未发现 bug 的结论是否正确'); const select = element('select'); select.setAttribute('aria-label', '判定 ' + (index + 1)); select.append(new Option('请选择判定', ''));
    for (const value of report ? ['correct', 'partial', 'incorrect', 'insufficient', 'additional_bug'] : ['correct_none', 'missed', 'insufficient']) select.append(new Option(labels[value], value));
    select.value = answer.verdict;
    const referenceLabel = element('label', '匹配的参考条目'); const reference = element('select'); reference.append(new Option('未匹配 / 不适用', ''), new Option('条目 1', 'primary')); reference.value = answer.reference_item;
    reference.onchange = () => { answer.reference_item = reference.value; cache(); };
    select.onchange = () => { answer.verdict = select.value; answer.reference_item = ['correct', 'partial'].includes(answer.verdict) ? 'primary' : ''; reference.value = answer.reference_item; cache(); };
    const reasonLabel = element('label', '判定理由'); const reason = element('textarea'); reason.value = answer.reason; reason.maxLength = 10000; reason.placeholder = '说明哪些描述和截图支持／不支持该 bug、与 rubric 的对应关系，以及类别复核的依据。若证据不足，请指出缺少什么。'; reason.oninput = () => { answer.reason = reason.value; cache(); };
    label.append(select); referenceLabel.append(reference); reasonLabel.append(reason); fields.append(label, referenceLabel); if (report) fields.append(categoryReview(answer, index)); fields.append(reasonLabel); card.append(fields); $('answers').append(card);
  });
}
function categoryReview(answer, index) {
  const section = element('fieldset', undefined, 'category-picker'); section.append(element('legend', '2. 探索者的类别是否选对'));
  const select = element('select'); select.setAttribute('aria-label', '类别复核 ' + (index + 1));
  for (const [code, name] of Object.entries({'':'请选择类别复核',correct:'类别正确',incorrect:'类别选错',uncertain:'无法确定',not_applicable:'不适用（异常不成立等）'})) select.append(new Option(name, code));
  select.value = answer.category_verdict === 'not_reviewed' ? '' : answer.category_verdict || '';
  const correction = element('div');
  const renderCorrection = () => {
    correction.replaceChildren(); if (answer.category_verdict !== 'incorrect') return;
    const label = element('label', '建议类别'); const choice = element('select'); choice.setAttribute('aria-label', '建议类别 ' + (index + 1)); choice.append(new Option('请选择建议类别', ''));
    for (const group of taxonomy.categories) choice.append(new Option(group.name.zh, group.id)); choice.append(new Option('其他', 'other'));
    choice.value = answer.corrected_category || ''; choice.onchange = () => { answer.corrected_category = choice.value; cache(); }; label.append(choice); correction.append(label);
  };
  select.onchange = () => { answer.category_verdict = select.value; answer.corrected_category = ''; renderCorrection(); cache(); };
  section.append(select, element('p', '类别与 bug 成立性分别记录；建议类别不会改写探索者答案。', 'muted'), correction); renderCorrection(); return section;
}
function renderReviewGuide() {
  const lang = reviewLanguage;
  for (const code of ['zh','en']) $('review-' + code).setAttribute('aria-pressed', String(code === lang));
  const instructions = lang === 'zh' ? [
    '先看 Query 和 ground-truth rubric，再逐条核对探索者描述与截图。只依据实际证据判断，不把探索者所选类别当成已证实的事实。',
    '正确：描述和证据支持对应 rubric 的异常；部分正确：识别到对应异常，但重要描述只得到部分支持；不正确：关键主张与证据矛盾或把正常现象当作 bug；证据不足：无法据现有材料判断。',
    '疑似额外真实 bug：证据支持一个不属于当前 rubric 的独立异常。不要仅因没有匹配 rubric 就判错，也不要因无法判断就选额外 bug。',
    '单独复核分类：类别正确、类别选错、无法确定或不适用。选错时指定建议类别，在理由中解释；类别错误不应自动导致“bug 不正确”。旧子类型会标为历史分类，不因旧名称本身扣分。',
    '每条结论写清依据和证据编号。动态或碰撞问题可能无法由单张静态截图证明；指出缺少的步骤或画面。重复描述同一异常时在理由中指出重复。',
    '对“未发现 bug”的答案，结合 rubric 判断正确未发现、漏检或证据不足；不要求填写类别。保存后可以修订，历史版本会保留。'
  ] : [
    'Read the query and ground-truth rubric, then compare each description with its evidence. Treat the explorer’s chosen category as a claim, not an established fact.',
    'Correct: evidence supports the reported rubric anomaly. Partial: the anomaly is identified but important details are only partly supported. Incorrect: central claims contradict evidence or describe normal behavior as a bug. Insufficient: the available material does not permit a reliable conclusion.',
    'Additional bug: evidence supports a distinct anomaly outside the rubric. Lack of a rubric match alone does not make a report incorrect; uncertainty alone does not establish an additional bug.',
    'Review classification separately: correct, incorrect, uncertain or not applicable. Suggest a category when incorrect and explain your reasoning. A category error alone does not invalidate a real bug. Historical subtype labels are preserved and are not errors merely because they use the earlier taxonomy.',
    'Explain each decision using evidence numbers. A still image may not prove motion or collision; identify missing actions or views. Note duplicate reports of the same anomaly in the rationale.',
    'For a no-bug answer, use the rubric to judge correct-none, missed or insufficient. Category review is not required. Saved judgments can be revised and earlier versions are retained.'
  ];
  const list = element('ol'); instructions.forEach(text => list.append(element('li', text))); $('review-instructions').replaceChildren(list);
  $('review-taxonomy').replaceChildren(element('h3', lang === 'zh' ? '与探索端一致的五类定义' : 'The same five-category taxonomy shown to explorers'), element('p', taxonomy.intro[lang]));
  for (const group of taxonomy.categories) { const details = element('details'); details.append(element('summary', group.name[lang]), element('p', group.description[lang])); $('review-taxonomy').append(details); }
  $('review-taxonomy').append(element('p', taxonomy.principle[lang], 'category-hint'));
}
for (const lang of ['zh','en']) $('review-' + lang).onclick = () => { reviewLanguage = lang; renderReviewGuide(); if(current)renderExample($('task-example'),current.submission.task_version_id,reviewLanguage,true); };

$('refresh').onclick = () => refresh().catch(error => message(error.message, true));
$('claim').onclick = () => claim().catch(error=>message(error.message,true));
$('save').onclick = async () => {
  $('save').disabled = true;
  try {
    if (current.submission.outcome === 'reports' && answers.some(a => !a.category_verdict || a.category_verdict === 'not_reviewed' || a.category_verdict === 'incorrect' && !a.corrected_category)) throw new Error('请完成每条报告的类别复核，选错时指定建议类别。');
    const id = current.submission.id; current = await api(`/api/submissions/${id}/judgment`, {revision: current.revision, answers}); localStorage.removeItem(key()); render(); await refresh(); message('人工判定已保存。'); }
  catch (error) { message(error.message, true); }
  finally { $('save').disabled = false; }
};
initialize(async loggedIn => {
  user = loggedIn; taxonomy = await api('/api/taxonomy');
  for (const group of taxonomy.categories) categoryNames[group.id] = group.name.zh;
  for (const [code, old] of Object.entries(taxonomy.legacy)) categoryNames[code] = old.name.zh + '（历史分类）';
  renderReviewGuide();
  progressView = setupProgress({app:'evaluation',user,onLeave:async()=>{if(current)cache();},onOpen:async row=>{await claim(row.id);}});
  await refresh();
  setInterval(async () => { if (!current || current.state === 'complete') return; try { await api(`/api/submissions/${current.submission.id}/heartbeat`, {}); } catch (error) { message(error.message + '；本地评测草稿已保留。', true); } }, 60000);
});
