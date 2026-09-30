export async function api(path, data) {
  const response = await fetch(path, {method: data === undefined ? 'GET' : 'POST', headers: data === undefined ? {} : {'Content-Type': 'application/json'}, body: data === undefined ? undefined : JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) { const error = new Error(result.error || '请求失败'); error.status = response.status; throw error; }
  return result;
}
export const $ = id => document.getElementById(id);
export function element(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}
export function message(text, error = false) { $('message').textContent = text; $('message').classList.toggle('error', error); }
export function imagePreview(src, label) {
  const button = element('button', undefined, 'image-button');
  button.type = 'button';
  const img = element('img'); img.src = src; img.alt = label; button.append(img);
  button.onclick = () => { $('preview-image').src = src; $('preview').showModal(); };
  return button;
}
export async function initialize(onReady) {
  $('preview-close').onclick = () => $('preview').close();
  $('login-form').onsubmit = async event => {
    event.preventDefault(); const button = $('login-submit'); button.disabled = true;
    try { await api('/api/login', {name: $('login-name').value.trim(), password: $('login-password').value}); $('login-password').value = ''; await enter(); }
    catch (error) { message(error.message, true); }
    finally { button.disabled = false; }
  };
  $('logout').onclick = async () => { try { await api('/api/logout', {}); location.reload(); } catch (error) { message(error.message, true); } };
  async function enter() {
    const user = await api('/api/me'); $('identity').textContent = user.name;
    document.body.classList.remove('at-login'); $('login').hidden = true; $('workspace').hidden = false; $('account').hidden = false; message('');
    await onReady(user);
  }
  try { await enter(); } catch (error) {
    if (error.status !== 401) message(error.message, true);
    if (!$('login').hidden) {
      const select=$('login-name');$('login-submit').disabled=true;
      try {
        const {users}=await api('/api/login-users');
        select.replaceChildren(new Option(users.length ? '请选择你的账号 · Select your name' : '暂无可用账号', ''));
        for(const name of users) select.append(new Option(name,name));
        select.disabled=!users.length;$('login-submit').disabled=!users.length;
      } catch(error) { select.replaceChildren(new Option('用户列表加载失败，请刷新重试',''));message(error.message,true); }
    }
  }
}
export function randomId() { return crypto.randomUUID().replaceAll('-', ''); }
