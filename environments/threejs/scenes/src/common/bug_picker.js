// Bug review overlay shared by every environment page.  Expects `window.__BUG_LIST = [{id, name, where, at}]` (injected
// by the build from environments/threejs/runtime/configs/*.answers.json) and, optionally, page hooks `window.__bugGoto(at)` (teleport next to
// the answer and look at it) and `window.__bugBeacon(at)` (toggle a marker at the answer).  Hidden in harness /
// benchmark modes.  Picking a case reloads the page with `?bug=<id>`.
(function () {
  'use strict';
  const q = new URLSearchParams(location.search);
  if (q.has('harness') || q.has('noui') || q.has('benchmark')) return;
  const list = window.__BUG_LIST || [];
  if (!list.length) return;
  const cur = q.get('bug') || q.get('config') || '';
  const entry = list.find((b) => b.id === cur) || null;
  const css = `#bug-picker{position:fixed;top:12px;right:12px;z-index:2147483645;width:340px;max-width:calc(100vw - 24px);font:13px/1.35 system-ui,sans-serif;color:#eee;background:rgba(18,20,24,.92);border:1px solid rgba(255,255,255,.18);border-radius:10px;padding:10px 12px;box-shadow:0 6px 24px rgba(0,0,0,.4)}
#bug-picker h4{margin:0 0 6px;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:#9ec5ff;display:flex;justify-content:space-between;align-items:center}
#bug-picker select{width:100%;font:13px system-ui,sans-serif;padding:5px 6px;border-radius:6px;border:1px solid #555;background:#111;color:#eee}
#bug-picker .where{margin:8px 0 6px;color:#ddd}#bug-picker .where b{color:#ffd166}
#bug-picker .row{display:flex;gap:6px;flex-wrap:wrap}#bug-picker button{font:12px system-ui,sans-serif;padding:5px 9px;border-radius:6px;border:1px solid #666;background:#2a2d33;color:#eee;cursor:pointer}
#bug-picker button:hover{background:#3a3f48}#bug-picker .mini{padding:2px 7px;border:none;background:transparent;color:#aaa}#bug-picker.min .body{display:none}#bug-picker.min{width:auto}
#bug-picker .hint{margin-top:6px;color:#888;font-size:11px}`;
  const style = document.createElement('style'); style.textContent = css; document.head.appendChild(style);
  const box = document.createElement('div'); box.id = 'bug-picker';
  const esc = (s) => String(s || '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const opts = ['<option value="">no bug (clean)</option>'].concat(list.filter((b) => !/00-clean$/.test(b.id)).map((b) => `<option value="${esc(b.id)}"${b.id === cur ? ' selected' : ''}>${esc(b.id)} — ${esc(b.name)}</option>`)).join('');
  box.innerHTML = `<h4><span>Bug review${window.__BUG_FAMILY ? ' · ' + esc(window.__BUG_FAMILY) : ''}</span><button class="mini" title="collapse">–</button></h4>
    <div class="body"><select>${opts}</select>
    <div class="where">${entry ? `<b>${esc(entry.name)}</b><br>${esc(entry.where)}` : 'Clean scene. Pick a case to reload with it injected.'}</div>
    <div class="row">${entry && entry.at ? '<button data-act="goto">Go to the bug</button><button data-act="beacon">Toggle marker</button>' : ''}<button data-act="reload">Reload</button></div>
    <div class="hint">Every case is a separate page load; walk with WASD, look with the mouse.</div></div>`;
  document.body.appendChild(box);
  box.querySelector('select').addEventListener('change', (e) => {
    const u = new URL(location.href); u.searchParams.delete('config'); if (e.target.value) u.searchParams.set('bug', e.target.value); else u.searchParams.delete('bug'); location.href = u.toString();
  });
  box.querySelector('.mini').addEventListener('click', () => box.classList.toggle('min'));
  box.addEventListener('click', (e) => {
    const act = e.target.dataset && e.target.dataset.act; if (!act) return;
    if (act === 'reload') location.reload();
    if (act === 'goto' && entry && window.__bugGoto) { try { window.__bugGoto(entry.at); } catch (err) { console.warn('goto failed', err); } }
    if (act === 'beacon' && entry && window.__bugBeacon) { try { window.__bugBeacon(entry.at); } catch (err) { console.warn('beacon failed', err); } }
  });
  // keyboard focus must stay with the game: controls blur themselves after use
  box.querySelectorAll('button,select').forEach((el) => el.addEventListener('mouseup', () => setTimeout(() => el.blur(), 0)));
  // stop game key handlers from seeing keystrokes typed into the select
  box.addEventListener('keydown', (e) => e.stopPropagation());
})();
