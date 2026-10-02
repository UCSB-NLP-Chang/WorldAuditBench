const $ = id => document.getElementById(id);
let rows = [], selected = null, active = null, busy = false;
let sceneVersion = 0, polling = false;

function status(message, error = false) {
  $('status').textContent = message;
  $('status').classList.toggle('error', error);
}
function setBusy(value) {
  busy = value;
  $('open').disabled = busy || !selected;
  $('stop').disabled = busy || !active;
  $('fullscreen').disabled = busy || !active;
  $('open').textContent = busy ? 'Starting…' : active === selected?.task_id ? 'Reset environment' : 'Open environment';
}
function label(value) {
  return value.replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase());
}
function options(id, values) {
  const select = $(id), old = select.value;
  while (select.options.length > 1) select.remove(1);
  [...new Set(values)].sort().forEach(value =>
    select.add(new Option(id === 'environment' ? label(value) : value, value)));
  if ([...select.options].some(option => option.value === old)) select.value = old;
}
function selectTask(row) {
  selected = row;
  $('title').textContent = row.task_id;
  $('tags').replaceChildren();
  [label(row.environment), row.engine, row.category, row.subcategory].forEach(text => {
    const span = document.createElement('span');
    span.className = 'tag'; span.textContent = text; $('tags').append(span);
  });
  $('instruction').textContent = row.input.instruction;
  $('scene').textContent = row.input.scene_description;
  $('anomaly').textContent = row.rubric.anomaly;
  $('expected').textContent = row.rubric.expected;
  $('rubric').open = false;
  setBusy(busy);
  document.querySelectorAll('.task').forEach(button => {
    const current = button.dataset.task === row.task_id;
    button.classList.toggle('active', current);
    button.setAttribute('aria-pressed', String(current));
  });
  document.querySelector('.task.active')?.scrollIntoView({ block: 'nearest' });
  history.replaceState(null, '', '?task=' + encodeURIComponent(row.task_id));
  if (!busy && active && active !== row.task_id)
    status('Still viewing ' + active + '. Open ' + row.task_id + ' to switch.');
}
function filter() {
  const category = $('category').value;
  options('subcategory', rows.filter(row => !category || row.category === category).map(row => row.subcategory));
  const query = $('search').value.trim().toLowerCase(), environment = $('environment').value;
  const subcategory = $('subcategory').value;
  const shown = rows.filter(row => (!environment || row.environment === environment)
    && (!category || row.category === category) && (!subcategory || row.subcategory === subcategory)
    && (!query || (row.task_id + ' ' + row.environment).toLowerCase().includes(query)));
  $('count').textContent = shown.length + ' / ' + rows.length + ' tasks';
  $('tasks').replaceChildren();
  shown.forEach(row => {
    const button = document.createElement('button');
    button.className = 'task'; button.dataset.task = row.task_id;
    const name = document.createElement('span'); name.textContent = row.task_id;
    const type = document.createElement('small'); type.textContent = row.subcategory;
    button.append(name, type); button.onclick = () => selectTask(row); $('tasks').append(button);
  });
  if (shown.length) selectTask(shown.find(row => row.task_id === selected?.task_id) || shown[0]);
  else {
    selected = null; $('title').textContent = 'No matching tasks'; $('tags').replaceChildren();
    for (const id of ['instruction', 'scene', 'anomaly', 'expected']) $(id).textContent = '';
    $('rubric').open = false; setBusy(busy);
  }
}
async function post(path, body) {
  const response = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const data = await response.json();
  if (!response.ok) throw Error(data.error || 'Request failed');
  return data;
}
function clearScene() {
  sceneVersion++;
  $('boundary').hidden = true;
  active = null;
  $('browser').hidden = true; $('browser').src = 'about:blank';
  $('placeholder').hidden = false; $('active-task').textContent = 'No environment running';
}
$('open').onclick = async () => {
  if (busy || !selected) return;
  const task = selected.task_id;
  setBusy(true); clearScene();
  status('Opening ' + task + '… The first download or startup can take a few minutes.');
  try {
    const result = await post('/api/open', { task_id: task });
    const url = new URL(result.url, location.href);
    if (result.transport === 'pixel-streaming') {
      const signalling = new URL(url.pathname.replace(/player\.html$/, ''), location.href);
      signalling.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
      url.search = new URLSearchParams({ ss: signalling.href, AutoConnect: 'true',
        AutoPlayVideo: 'true', HoveringMouse: 'false', WebRTCMaxBitrate: '3000' });
    }
    active = task;
    $('browser').src = url.href; $('browser').hidden = false; $('placeholder').hidden = true;
    $('active-task').textContent = task + ' · ' + (result.engine === 'unreal' ? 'Live stream' : 'Interactive scene');
    if (result.build)
      $('active-task').textContent += ' · ' + result.build.label + ' · ' + result.build.sha256.slice(0, 8);
    status(result.engine === 'unreal'
      ? 'Click inside the live player to explore. Use WASD, mouse and E; Esc releases the mouse.'
      : 'Click inside the scene to explore. Use WASD and mouse; Esc releases the mouse.');
    if (selected?.task_id !== task) status('Viewing ' + task + '. Open the selected task to switch.');
  } catch (error) { clearScene(); status(error.message, true); }
  finally { setBusy(false); }
};
$('stop').onclick = async () => {
  if (busy) return;
  setBusy(true);
  try { await post('/api/stop', {}); clearScene(); status('Environment stopped. Select a task to explore.'); }
  catch (error) { status(error.message, true); }
  finally { setBusy(false); }
};
$('fullscreen').onclick = async () => {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await $('viewport').requestFullscreen();
  } catch { status('Fullscreen is not available in this browser.', true); }
};
for (const id of ['environment', 'category', 'subcategory']) $(id).onchange = filter;
$('search').oninput = filter;

// A crashed GPU process must not leave the page claiming its environment is live.
setInterval(async () => {
  if (!active || busy || polling) return;
  polling = true;
  const version = sceneVersion;
  try {
    const response = await fetch('/api/status');
    if (!response.ok) throw Error();
    const state = await response.json();
    if (version !== sceneVersion || busy) return;
    if (!state.running || state.task_id !== active) {
      clearScene(); setBusy(false);
      status('The environment stopped or was changed in another tab. Open it again to reconnect.', true);
    } else {
      $('boundary').hidden = state.boundary_state !== 2;
    }
  } catch {
    if (version === sceneVersion && !busy) {
      $('boundary').hidden = true;
      status('Cannot reach the viewer server. Check that it is still running.', true);
    }
  } finally { polling = false; }
}, 500);

(async () => {
  try {
    const response = await fetch('/api/tasks');
    if (!response.ok) throw Error('Could not load task data');
    rows = await response.json();
    options('environment', rows.map(row => row.environment));
    options('category', rows.map(row => row.category));
    selected = rows.find(row => row.task_id === new URLSearchParams(location.search).get('task'));
    filter();
  } catch (error) { $('count').textContent = 'Task data unavailable'; status(error.message, true); }
})();
