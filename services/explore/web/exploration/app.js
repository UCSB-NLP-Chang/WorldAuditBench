import {renderExample} from '/static/example.js?v=icl-hover-v24';
import {setupProgress} from '/static/progress.js?v=two-person-progress-20260920';
import {api, $, element, message, imagePreview, initialize, randomId} from '/static/common.js';

let selectedTaskId, selectedAttemptId, progressView, nextBusy=false, assignmentPending=false, assignmentPolling=false, assignmentEpoch=0, allocationRequest=null;
let taxonomy, instructions, guideLanguage = localStorage.getItem('bf-guide-language') === 'en' ? 'en' : 'zh', deleting = false;
let user, task, attempt, runtime, frame, timer, saving = Promise.resolve(), change = 0, savedChange = 0;
let reports = [], outcome = 'reports', technicalNote = '', pending = new Map(), conflict = false, pollBusy = false;
const dbReady = new Promise((resolve, reject) => {
  const request = indexedDB.open('bf-exploration-evidence-v1', 1);
  request.onupgradeneeded = () => request.result.createObjectStore('pending', {keyPath: 'id'});
  request.onsuccess = () => resolve(request.result); request.onerror = () => reject(request.error);
});
async function pendingStore(operation, value) {
  const db = await dbReady;
  return new Promise((resolve, reject) => {
    const transaction = db.transaction('pending', operation === 'getAll' ? 'readonly' : 'readwrite');
    const request = transaction.objectStore('pending')[operation](value);
    transaction.oncomplete = () => resolve(request.result); transaction.onerror = () => reject(transaction.error);
  });
}
const cacheKey = () => 'bf-draft:' + user.name + ':' + attempt.id;
const draft = () => ({reports: reports.map(report => ({...report, category: task.ground_truth_categories?.[0]?.id || report.category || 'unsure'})), outcome, technical_note: technicalNote});
function cache() { try { localStorage.setItem(cacheKey(), JSON.stringify({version: attempt.draft_version, draft: draft(), dirty: change !== savedChange})); } catch { message('浏览器本地缓存不可用，请保持页面打开直到草稿保存。', true); } }
function changed() { change++; cache(); $('save-status').textContent = '正在保存…'; clearTimeout(timer); timer = setTimeout(() => saveDraft().catch(error => message(error.message, true)), 600); }
function saveDraft() {
  saving = saving.catch(() => {}).then(async () => {
    if (!attempt || attempt.status !== 'draft' || savedChange === change) return;
    if (conflict) throw new Error('草稿版本冲突，本地内容已保留。请在原页面完成保存后重新登录。');
    const generation = change;
    const content = JSON.parse(JSON.stringify(draft()));
    try {
      const result = await api(`/api/attempts/${attempt.id}/draft`, {version: attempt.draft_version, draft: content});
      attempt.draft_version = result.draft_version; savedChange = generation; cache();
      $('save-status').textContent = change === savedChange ? '草稿已保存' : '正在保存…';
    } catch (error) { if (error.status === 409) conflict = true; $('save-status').textContent = '保存失败 · 本地已保留'; throw error; }
  });
  return saving;
}

function workspaceAPI() {
  const query = new URLSearchParams();
  if (selectedAttemptId) query.set('attempt_id', selectedAttemptId); else if (selectedTaskId) query.set('task_id', selectedTaskId);
  return api('/api/workspace?' + query);
}
async function loadWorkspace() {
  const workspace = await workspaceAPI(); task = workspace.task; attempt = workspace.attempt;
  if (!task) throw new Error('当前账号暂无已分配探索任务。');
  if (!attempt) attempt = await api('/api/attempts', {task_id: task.id});
  selectedTaskId = task.id; selectedAttemptId = attempt.id;
  reports = attempt.draft.reports || []; outcome = attempt.draft.outcome; technicalNote = attempt.draft.technical_note || '';
  change = savedChange = 0; conflict = false;
  try {
    const cached = JSON.parse(localStorage.getItem(cacheKey()) || 'null');
    if (cached?.dirty && attempt.status === 'draft') {
      reports = cached.draft.reports; outcome = cached.draft.outcome; technicalNote = cached.draft.technical_note || ''; change++;
      conflict = cached.version !== attempt.draft_version;
      if (conflict) message('检测到另一页面修改了草稿。当前显示本地未同步内容，已暂停自动覆盖。', true);
      else await saveDraft();
    }
  } catch (error) { message(error.message, true); }
  if (attempt.status === 'draft' && !reports.length && !conflict) {
    reports.push(emptyReport());
    changed();
  }
  for (const item of pending.values()) if (item.url) URL.revokeObjectURL(item.url);
  pending = new Map();
  try { for (const item of await pendingStore('getAll')) if (item.owner === user.name && item.attempt_id === attempt.id) pending.set(item.id, {...item, state: '待重试', url: URL.createObjectURL(item.blob)}); }
  catch { message('本地截图恢复不可用，请保持页面打开完成上传。', true); }
  $('task-title').textContent = task.title; $('query').textContent = task.query;
  renderTaskCategory();
  $('task-id').textContent = '任务 ' + task.id.slice(0, 8).toUpperCase(); $('controls').textContent = 'W / A / S / D 移动 · E 交互 · 点击画面后鼠标观察 · F 截图 · Esc 释放鼠标';
  renderReports(); renderFlags(); renderStatus();
  await poll();
}

function renderStatus() {
  const editable = attempt.status === 'draft';
  $('attempt-status').textContent = editable ? (['ready','starting','queued','closing'].includes(runtime?.status) ? '会话进行中 · 草稿未提交' : '草稿待提交') : attempt.status === 'technical' ? '技术问题已记录' : attempt.status==='skipped'?'已放弃（未找到）':'已提交';
  $('outcome').value = outcome; $('outcome').disabled = !editable;
  $('not-found').checked=outcome==='none';$('not-found').disabled=!editable;
  $('technical-issue').checked=outcome==='technical';$('technical-issue').disabled=!editable;
  $('reports').hidden=outcome!=='reports';
  $('submit').textContent=outcome==='none'?'放弃本题并领取下一题':outcome==='technical'?'记录技术问题并领取下一题':'提交报告并领取下一题';
  $('technical-note').value = technicalNote; $('technical-note').hidden = outcome !== 'technical'; $('technical-note').disabled = !editable;
  $('add-report').hidden = !editable || outcome !== 'reports';
  $('submit').hidden = !editable; $('new-attempt').hidden = true;
  $('submitted').hidden = editable;
  if (!editable) $('submitted').textContent = attempt.status==='skipped'?'已记录放弃；这不表示环境没有 bug，也未提交 bug 报告。':attempt.status === 'technical' ? '技术问题已记录，未计作正常 bug finding 答案。' : '答案已保存。' + (attempt.submission?.delivered ? '已送达人工评测。' : '正在发送给人工评测；你可以安全关闭页面。');
  $('start').disabled = assignmentPending || !editable || runtime?.status === 'queued' || runtime?.status === 'starting' || runtime?.status === 'ready' || runtime?.status === 'closing';
  $('stop').disabled = !assignmentPending && !['queued', 'ready', 'starting'].includes(runtime?.status);
  $('stop').textContent = assignmentPending ? '取消等待' : '结束会话';
  renderConnection();
}
function renderReports() {
  $('reports').replaceChildren();
  if (!reports.length) $('reports').append(element('p', '看到疑似异常后，先 Flag，再添加描述。', 'empty'));
  reports.forEach((report, index) => {
    const article = element('article', undefined, 'report'); const head = element('div', undefined, 'report-head');
    head.append(element('h3', 'Bug ' + (index + 1)));
    if (attempt.status === 'draft') { const remove = element('button', '移除'); remove.onclick = () => { reports = reports.filter(r => r.id !== report.id); changed(); renderReports(); }; head.append(remove); }
    const textarea = element('textarea'); textarea.value = report.description; textarea.maxLength = 10000; textarea.placeholder = '简要描述对象、位置和异常现象；仅在必要时补充触发条件。'; textarea.setAttribute('aria-label', 'Bug ' + (index + 1) + ' description'); textarea.disabled = attempt.status !== 'draft';
    textarea.oninput = () => { report.description = textarea.value; changed(); };
    const choices = element('div', undefined, 'evidence-choices');
    if (!attempt.flags.length) choices.append(element('span', '请先保存一张 Flag 截图。', 'muted'));
    attempt.flags.forEach((flag, i) => {
      const label = element('label'); const checkbox = element('input'); checkbox.type = 'checkbox'; checkbox.checked = report.evidence_ids.includes(flag.id); checkbox.disabled = attempt.status !== 'draft';
      checkbox.onchange = () => { report.evidence_ids = checkbox.checked ? [...report.evidence_ids, flag.id] : report.evidence_ids.filter(id => id !== flag.id); changed(); };
      label.append(checkbox, document.createTextNode('Flag ' + (i + 1))); choices.append(label);
    });
    textarea.placeholder = instructions[guideLanguage].template;
    article.append(head, textarea, element('span', guideLanguage === 'en' ? 'Evidence screenshots' : '证据截图', 'muted'), choices); $('reports').append(article);
  });
}
function renderTaskCategory(){
  const environment=$('task-environment');environment.replaceChildren();
  const description=task?.environment_description?.[guideLanguage];
  environment.hidden=!description;
  if(description)environment.append(element('h3',guideLanguage==='en'?'Environment description':'环境描述'),element('p',description));
  const box=$('task-category');box.replaceChildren();if(!task)return;
  renderExample($('task-example'),task.id,guideLanguage);
  const groups=task.ground_truth_categories||[];
  box.append(element('h3',guideLanguage==='en'?'Bug types involved in this task':'本题涉及的 bug 类型'));
  for(const c of groups)box.append(element('strong',c.name[guideLanguage]),element('p',c.description[guideLanguage]));
  box.append(element('p',groups.length?(guideLanguage==='en'?'Use these types as exploration hints. Briefly describe the bug you find and attach relevant screenshots; no exploration log is required. The report type is filled in automatically.':'请参考这些类型定位问题，简要描述发现的 bug，并关联相关截图。无需记录探索过程。报告类型由系统自动填写。'):'历史任务：不在当前分配池中。','muted'));
}
function renderGuide() {
  renderTaskCategory();
  const lang = guideLanguage, data = instructions[lang];
  $('guide-title').textContent = data.title; $('guide-intro').textContent = data.intro;
  $('guide-language').textContent = lang === 'zh' ? 'English' : '中文';
  $('guide-language').setAttribute('aria-label', lang === 'zh' ? 'Switch instructions to English' : '切换为中文说明');
  $('guide-summary').textContent = lang === 'zh' ? '展开说明' : 'View instructions';
  $('bug-guide').lang = lang;
  const download = $('guide-download'); download.href = '/api/instructions/' + lang + '.md'; download.download = 'exploration-instructions.' + lang + '.md';
  download.textContent = lang === 'en' ? 'Download complete instructions (.md) for an LLM agent' : '下载完整说明（Markdown）';
  $('guide-sections').replaceChildren();
  for (const section of data.sections) {
    const details = element('details'); details.append(element('summary', section.title));
    const list = element('ul'); for (const item of section.items) list.append(element('li', item));
    details.append(list); $('guide-sections').append(details);
  }
  $('taxonomy-heading').textContent = lang === 'en' ? 'Bug taxonomy · 5 categories' : 'Bug 类型 · 5 大类';
  $('category-guide').replaceChildren(element('p', taxonomy.intro[lang]));
  for (const group of taxonomy.categories) {
    const details = element('details'); details.append(element('summary', group.name[lang]), element('p', group.description[lang]));
    $('category-guide').append(details);
  }
  $('category-guide').append(element('p', taxonomy.principle[lang], 'category-hint'));
  $('template-heading').textContent = data.report_title; $('report-template').textContent = data.template; $('agent-note').textContent = data.agent_note;
}
$('guide-language').onclick = () => { guideLanguage = guideLanguage === 'zh' ? 'en' : 'zh'; localStorage.setItem('bf-guide-language', guideLanguage); renderGuide(); renderReports(); };

function renderFlags() {
  $('flags').replaceChildren(); $('flag-count').textContent = attempt.flags.length + ' 张已保存' + (pending.size ? ' · ' + pending.size + ' 张待上传' : '');
  attempt.flags.forEach((flag, index) => { const card = element('div', undefined, 'flag'); card.append(imagePreview('/api/evidence/' + flag.id, 'Flag ' + (index + 1)), element('div', 'Flag ' + (index + 1) + ' · 已保存', 'caption')); if (attempt.status === 'draft') card.append(deleteButton(flag.id)); $('flags').append(card); });
  pending.forEach(item => {
    const card = element('div', undefined, 'flag'); card.append(imagePreview(item.url, '待上传的 Flag'), element('div', item.state, 'caption'));
    if (item.state !== '上传中…') { const retry = element('button', '重试上传'); retry.onclick = () => upload(item); card.append(retry); }
    if (attempt.status === 'draft' && item.state !== '上传中…') card.append(deleteButton(item.id));
    $('flags').append(card);
  });
}
function deleteButton(id) {
  const button = element('button', '删除截图', 'delete-flag'); button.disabled = deleting;
  button.onclick = () => removeFlag(id); return button;
}
function removeFlag(id) {
  if (deleting) return; deleting = true; renderFlags(); $('submit').disabled = true;
  saveDraft();
  saving = saving.then(async () => {
    const result = await api(`/api/attempts/${attempt.id}/delete-flag`, {id, version: attempt.draft_version});
    attempt.draft_version = result.draft_version; attempt.flags = result.flags;
    for (const report of reports) report.evidence_ids = report.evidence_ids.filter(eid => eid !== id);
    const item = pending.get(id);
    if (item) { await pendingStore('delete', id); pending.delete(id); URL.revokeObjectURL(item.url); }
    cache(); renderFlags(); renderReports(); message('截图已删除，报告中的引用已同步移除。');
  }).catch(error => { if (error.status === 409) conflict = true; message(error.message, true); }).finally(() => { deleting = false; renderFlags(); $('submit').disabled = false; });
}
// Keep evidence within the server's PNG byte and dimension limits. The original
// stays in IndexedDB until upload succeeds, including retries of older captures.
async function prepareScreenshot(blob) {
  const maxBytes = 5 * 1024 * 1024;
  const bitmap = await createImageBitmap(blob);
  try {
    if (blob.type === 'image/png' && blob.size <= maxBytes && bitmap.width <= 4096 && bitmap.height <= 2160) return blob;
    const scale = Math.min(1, 4096 / bitmap.width, 2160 / bitmap.height);
    let width = Math.max(1, Math.floor(bitmap.width * scale));
    let height = Math.max(1, Math.floor(bitmap.height * scale));
    const canvas = document.createElement('canvas');
    for (;;) {
      canvas.width = width; canvas.height = height;
      const context = canvas.getContext('2d');
      if (!context) throw new Error('无法处理截图，请重试。原始截图已保留。');
      context.imageSmoothingEnabled = true;
      context.imageSmoothingQuality = 'high';
      context.drawImage(bitmap, 0, 0, width, height);
      const output = await new Promise((resolve, reject) => canvas.toBlob(result => result ? resolve(result) : reject(new Error('截图处理失败，请重试。原始截图已保留。')), 'image/png'));
      if (output.size <= maxBytes) return output;
      if (width === 1 && height === 1) throw new Error('无法将截图缩小至上传限制内，原始截图已保留。');
      const shrink = Math.min(0.85, Math.max(0.5, Math.sqrt(maxBytes / output.size) * 0.95));
      width = Math.max(1, Math.floor(width * shrink));
      height = Math.max(1, Math.floor(height * shrink));
    }
  } finally { bitmap.close(); }
}
async function upload(item) {
  if (item.state === '上传中…') return;
  item.state = '上传中…'; renderFlags();
  try {
    const uploadBlob = await prepareScreenshot(item.blob);
    const content = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result.split(',')[1]); reader.onerror = reject; reader.readAsDataURL(uploadBlob); });
    await api(`/api/attempts/${item.attempt_id}/flags`, {id: item.id, runtime_id: item.runtime_id, captured_at: item.capturedAt, content_base64: content});
    await pendingStore('delete', item.id); pending.delete(item.id); URL.revokeObjectURL(item.url);
    const workspace = await workspaceAPI();
    if (workspace.attempt?.id === attempt.id) attempt.flags = workspace.attempt.flags;
    // Do not rebuild textareas while the user is typing. Preserve their selection.
    const active = document.activeElement, reportIndex = [...$('reports').querySelectorAll('textarea')].indexOf(active), selection = reportIndex >= 0 ? [active.selectionStart, active.selectionEnd] : null;
    renderFlags(); renderReports();
    if (selection) { const field = $('reports').querySelectorAll('textarea')[reportIndex]; field?.focus(); field?.setSelectionRange(...selection); }
    message('Flag 已保存。');
  } catch (error) { item.state = '上传失败 · 已保留本地截图'; renderFlags(); message(error.message, true); }
}
async function acceptCapture(event) {
  if (event.origin !== location.origin || !frame || event.source !== frame.contentWindow) return;
  if (event.data?.type === 'bf-capture-error') return message(event.data.message, true);
  if (event.data?.type !== 'bf-capture' || !(event.data.blob instanceof Blob) || runtime?.status !== 'ready' || attempt.status !== 'draft') return;
  if (attempt.flags.length + pending.size >= 30) return message('最多保存 30 张截图。', true);
  const item = {id: randomId(), owner: user.name, attempt_id: attempt.id, runtime_id: runtime.id, blob: event.data.blob, capturedAt: event.data.capturedAt};
  try { await pendingStore('put', item); }
  catch { message('本地截图缓存失败，请保持页面打开直到上传完成。', true); }
  const pendingItem = {...item, url: URL.createObjectURL(item.blob), state: '等待上传'}; pending.set(item.id, pendingItem); upload(pendingItem);
}
function requestCapture() { if (runtime?.status === 'ready' && frame) frame.contentWindow.postMessage({type: 'bf-capture-request'}, location.origin); }
window.addEventListener('message', acceptCapture);
document.addEventListener('keydown', event => { if (event.code === 'KeyF' && !event.repeat && !event.ctrlKey && !event.metaKey && !event.altKey && !event.target.closest('input,textarea,select,[contenteditable="true"]')) { event.preventDefault(); requestCapture(); } });
window.addEventListener('beforeunload', event => { if (savedChange !== change) { cache(); event.preventDefault(); event.returnValue = ''; } });

async function poll() {
  if(assignmentPending){await pollAssignment();return;}
  if (!attempt || pollBusy) return; pollBusy = true;
  try {
    const previousStatus = runtime?.status;
    const epoch=assignmentEpoch,aid=attempt.id;
    const state=await api(`/api/attempts/${aid}/runtime`);
    if(epoch!==assignmentEpoch || aid!==attempt?.id)return;
    runtime=state;
    $('runtime-status').textContent = ({queued: '排队中 · 第 '+runtime.queue_position+' 位', idle: '环境未运行', starting: '正在启动环境…', ready: '环境已就绪', closing: '正在释放环境…'})[runtime.status] || runtime.status;
    const capacity=runtime.capacity;
    if(capacity) $('session-capacity').textContent='Unreal slots: '+capacity.running+' / '+capacity.capacity+' · 排队 '+capacity.queued+' 人'+(capacity.legacy_busy?' · audit 正在使用 GPU，仅 Unreal 会话需等待；Three.js 不受影响':'')+' · Three.js 不占 GPU 槽位 · 每账号一个会话 · 最长 '+Math.round(capacity.max_age/60)+' 分钟';
    if (runtime.message) message(runtime.message);
    else if (runtime.status === 'ready' && previousStatus !== 'ready') message(runtime.kind === 'browser' ? '环境已启动，正在加载场景。' : '环境已启动，正在连接视频。');
    if (runtime.status === 'ready' && runtime.stream_url && frame?.dataset.runtime !== runtime.id) {
      frame = element('iframe'); frame.title = '探索环境'; frame.dataset.runtime = runtime.id; frame.allow = 'autoplay; fullscreen; gamepad';
      const url = new URL(runtime.stream_url, location.origin);
      const signalling = location.origin.replace(/^http/, 'ws') + runtime.stream_url + 'ws';
      if(runtime.kind !== 'browser') for (const [key, value] of Object.entries({ss: signalling, AutoConnect: 'true', AutoPlayVideo: 'true', StartVideoMuted: 'true', HoveringMouse: 'false', HideUI: 'true', ForceTURN: 'true', WebRTCMaxBitrate: '3000'})) url.searchParams.set(key, value);
      frame.src = url.href; $('player').replaceChildren(frame);
    } else if (runtime.status !== 'ready' && frame) { frame.remove(); frame = null; $('player').append(element('div', '环境已暂停。草稿和截图仍然保留。', 'placeholder')); }
    if (attempt.status === 'submitted' && !attempt.submission?.delivered) { const workspace = await workspaceAPI(); if (workspace.attempt.id === attempt.id) attempt.submission = workspace.attempt.submission; }
    renderStatus();
  } catch (error) { message(error.message, true); }
  finally { pollBusy = false; }
}
$('flag').onclick = requestCapture;
$('start').onclick = async () => { $('start').disabled = true; try { runtime = await api(`/api/attempts/${attempt.id}/runtime`, {operation: 'start'}); message('正在准备环境，请稍候。'); await poll(); } catch (error) { message(error.message, true); renderStatus(); } };
$('stop').onclick = async () => { $('stop').disabled=true; try { await saveDraft(); if(assignmentPending){await releaseCurrent();message('已取消等待，草稿保留。');renderStatus();return;} await api(`/api/attempts/${attempt.id}/runtime`, {operation: 'stop'}); await poll(); } catch (error) { message(error.message, true); } };
function emptyReport() { return {id: randomId(), description: '', category: task.ground_truth_categories?.[0]?.id || 'unsure', evidence_ids: []}; }
$('add-report').onclick = () => { reports.push(emptyReport()); changed(); renderReports(); $('reports').lastElementChild?.querySelector('textarea')?.focus(); };
$('not-found').onchange=()=>{outcome=$('not-found').checked?'none':'reports';changed();renderStatus();};
$('technical-issue').onchange=()=>{outcome=$('technical-issue').checked?'technical':'reports';changed();renderStatus();};
$('technical-note').oninput = () => { technicalNote = $('technical-note').value; changed(); };
$('submit').onclick = async () => {
  $('submit').disabled = true;
  try {
    if (deleting) throw new Error('请等待截图删除完成。');
    if (pending.size) throw new Error('请先完成待上传截图，避免提交时遗漏证据。');
    await saveDraft();
    await api(`/api/attempts/${attempt.id}/submit`, {version: attempt.draft_version});
    localStorage.removeItem(cacheKey()); await loadWorkspace();
    await requestNext();
  } catch (error) { message(error.message, true); }
  finally { $('submit').disabled = false; }
};
$('new-attempt').onclick = async () => { try { const next = await api('/api/attempts', {task_id: task.id}); selectedAttemptId = next.id; await loadWorkspace(); } catch (error) { message(error.message, true); } };
for(const id of ['next-task','next-task-bottom']) $(id).onclick=async()=>{
  try { await requestNext(); } catch(error) { message(error.message,true); }
};
async function releaseCurrent(){
  assignmentEpoch++;assignmentPending=false;
  // Let an in-flight allocation settle before releasing it, so cancellation cannot leave a late lease.
  if(allocationRequest)await allocationRequest.catch(()=>null);
  await saveDraft();
  await api('/api/release',{});
  runtime=null;
  if(frame){frame.remove();frame=null;}
  $('player').replaceChildren(element('div','环境已释放，草稿和截图保留。','placeholder'));
}
async function nextAllocation(data){
 const request=api('/api/next',data);allocationRequest=request;
 try{return await request;}finally{if(allocationRequest===request)allocationRequest=null;}
}
async function requestNext(){
  if(assignmentPending)return pollAssignment();
  if(nextBusy)return false;nextBusy=true;
  for(const id of ['next-task','next-task-bottom']) $(id).disabled=true;
  try {
  if(pending.size)throw new Error('请先完成截图上传。');
  await saveDraft();
  const previousTaskId=task?.id;
  await releaseCurrent();
  const epoch=assignmentEpoch;
  const next=await nextAllocation({exclude_task_id:previousTaskId});
  if(epoch!==assignmentEpoch)return false;
  if(next.waiting){assignmentPending=true;$('runtime-status').textContent='等待分配可用环境…';message(next.message);if(attempt)renderStatus();return false;}
  if(next.unavailable){message(next.message);return false;}
  if(attempt?.id===next.id){message('已打开当前领取的题目，草稿已保留。');return true;}
  if(attempt){const state=await api(`/api/attempts/${attempt.id}/runtime`);if(['queued','ready','starting','closing'].includes(state.status))await api(`/api/attempts/${attempt.id}/runtime`,{operation:'stop'});}
  selectedTaskId=next.task.id;selectedAttemptId=next.id;await loadWorkspace();
  message('已领取题目。查看类型提示后，点击 Start session 开始环境；提交或放弃后会自动领取下一题。');return true;
  } finally { nextBusy=false;for(const id of ['next-task','next-task-bottom']) $(id).disabled=false; }
}
async function pollAssignment(){
 if(assignmentPolling)return false;assignmentPolling=true;
 const epoch=assignmentEpoch;
 try{
  const next=await nextAllocation({});
  if(epoch!==assignmentEpoch || !assignmentPending)return false;
  if(next.waiting){message(next.message);return false;}
  assignmentPending=false;
  if(next.unavailable){message(next.message);return false;}
  selectedTaskId=next.task.id;selectedAttemptId=next.id;await loadWorkspace();progressView?.showWork();message('已安排可用题目。点击 Start session 开始。');return true;
 }catch(error){message(error.message,true);return false;}
 finally{assignmentPolling=false;}
}
function resizeWorkspace() {
  const layout = $('explore-layout');
  layout.style.height = innerWidth > 960 ? Math.max(440, innerHeight - layout.getBoundingClientRect().top - window.scrollY - 20) + 'px' : '';
}
window.addEventListener('resize', resizeWorkspace);
new ResizeObserver(resizeWorkspace).observe(document.querySelector('.task-heading'));
new ResizeObserver(resizeWorkspace).observe($('message'));
function renderConnection() {
  if (!frame || runtime?.status !== 'ready') { $('flag').disabled = true; return; }
  const health = frame.contentWindow?.reviewHealth;
  const receiving = runtime.kind === 'browser' ? !!frame.contentWindow?.bfBrowserReady : health?.peer === 'connected' && health.frames > 0 && Date.now() - health.lastFrameAt < 5000;
  if (receiving && ['环境已启动，正在连接视频。','环境已启动，正在加载场景。','正在准备环境，请稍候。'].includes($('message').textContent)) message('环境已连接。点击画面开始控制，按 Esc 返回填写报告。');
  $('runtime-status').textContent = receiving ? '环境已连接 · 点击画面开始控制' : runtime.kind === 'browser' ? '正在加载场景…' : health?.frames > 0 ? '视频连接中断，正在重连…' : '正在连接视频…';
  $('flag').disabled = attempt.status !== 'draft' || !receiving;
}
setInterval(renderConnection, 1000);
initialize(async loggedIn => {
  user = loggedIn; [taxonomy, instructions] = await Promise.all([api('/api/taxonomy'), api('/api/instructions')]);
  renderGuide();
  progressView = setupProgress({app:'exploration', user, onNext:requestNext, onLeave:async()=>{
    if (pending.size) throw new Error('请等待截图上传完成后切换任务。');
    await saveDraft();
    if (frame?.contentDocument?.pointerLockElement) frame.contentDocument.exitPointerLock();
  },onOpen:async row=>{
    if (!attempt || attempt.id !== row.attempt_id) await releaseCurrent();
    selectedTaskId=row.task_id;selectedAttemptId=row.attempt_id;await loadWorkspace();
  }});
  setInterval(poll, 3000);
});
