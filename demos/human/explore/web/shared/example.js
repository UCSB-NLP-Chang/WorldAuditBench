import {api, element} from '/static/common.js';
const cache = new Map();
const generations = new WeakMap();
export async function renderExample(box, taskId, lang = 'zh', review = false) {
  if (!box || !taskId) return;
  hideExampleHover();
  const generation = (generations.get(box) || 0) + 1;
  generations.set(box, generation);
  const en = lang === 'en';
  box.replaceChildren(element('p', en ? 'Loading example…' : '正在加载参考例子…', 'muted'));
  try {
    if (!cache.has(taskId)) cache.set(taskId, api('/api/examples/' + taskId));
    const data = await cache.get(taskId);
    if (generations.get(box) !== generation) return;
    box.replaceChildren();
    if (!data.example) { box.append(element('p', en ? 'No matching example is available for this historical task.' : '这道历史题暂时没有匹配的参考例子。', 'muted')); return; }
    const e = data.example;
    const details = element('details'); details.open = true;
    details.append(element('summary', en ? 'Reference example · ' + e.code : '参考例子 · ' + e.code));
    details.append(element('h4', en ? e.name.en : e.title));
    details.append(element('p', en ? 'This example is from a different task. Its images are references to help you recognize the issue, not a required screenshot set or reporting format. Describe the bug you find; you do not need to explain every image or recount your exploration.' : '这是另一道题的参考例子。图片用于帮助理解异常，不是必需的截图数量或报告格式。提交时描述你发现的 bug 即可，无需逐张解释图片，也无需记录完整探索过程。', 'muted'));
    if (data.related) details.append(element('p', en ? 'Related example from the same broad category; the subtype differs.' : '同大类参考例，具体子类型不同。', 'example-note'));
    details.append(element('p', e.definition[lang]));
    const gallery = element('div', undefined, 'example-gallery');
    for (const f of e.frames) {
      const figure = element('figure');
      const caption = (en ? 'Figure ' : '图 ') + f.index + ' · ' + f.caption[lang];
      const preview = element('button', undefined, 'image-button'); preview.type = 'button';
      preview.append(annotatedImage(f, caption));
      preview.setAttribute('aria-label', (en ? 'Enlarge: ' : '放大：') + caption);
      preview.onclick = () => { hideExampleHover(); showExampleImages(e.frames, f.index - 1, lang); };
      if (!review) {
        preview.addEventListener('mouseenter', () => {
          if (matchMedia('(hover: hover) and (pointer: fine)').matches) showExampleHover(preview, f, caption);
        });
        preview.addEventListener('mouseleave', hideExampleHover);
        preview.addEventListener('blur', hideExampleHover);
      }
      figure.append(preview, element('figcaption', caption)); gallery.append(figure);
    }
    details.append(gallery, element('p', en ? (review ? 'Yellow boxes mark the area to compare, including normal controls. Click an image to enlarge.' : 'Yellow boxes mark areas to compare, including normal controls. Hover to enlarge; move away to close. Click for a pinned view.') : (review ? '黄色框标示需关注或对比的区域（含正常对照）。点击图片可放大。' : '黄色框标示需关注或对比的区域（含正常对照）。鼠标悬停放大，移开收起；也可点击查看。'), 'muted'));
    if (e.observation_context) details.append(element('p', e.observation_context[lang], 'example-note'));
    details.append(element('strong', en ? 'Example bug description' : 'Bug 描述示例'), element('p', e.evidence[lang]));
    if (review) details.append(element('p', en ? 'Current reviewer reference. This preview does not record which example the explorer saw; do not infer their exposure from this panel.' : '当前复核参考。本次前端预览尚未记录探索者作答时看到的示例，请勿据此推断其作答条件。', 'muted'));
    box.append(details);
  } catch {
    cache.delete(taskId);
    if (generations.get(box) === generation) box.replaceChildren(element('p', en ? 'Example unavailable. You can continue working.' : '参考例子暂时无法加载，可以继续做题。', 'muted'));
  }
}


function annotatedImage(frame, caption) {
  const wrap = element('span', undefined, 'example-image-wrap');
  const img = element('img'); img.src = '/example-images/' + frame.image_path.split('/').pop(); img.alt = caption; img.loading = 'lazy';
  wrap.append(img);
  for (const box of frame.boxes || []) {
    const rect = element('span', undefined, 'example-box'); rect.setAttribute('aria-hidden', 'true');
    Object.assign(rect.style, {left: box.x * 100 + '%', top: box.y * 100 + '%', width: box.width * 100 + '%', height: box.height * 100 + '%'});
    wrap.append(rect);
  }
  return wrap;
}
function showExampleImages(frames, initialIndex, lang) {
  const en = lang === 'en'; let index = initialIndex;
  const dialog = element('dialog', undefined, 'example-lightbox');
  dialog.setAttribute('aria-label', en ? 'Reference example images' : '参考例子截图');
  const viewport = element('div', undefined, 'example-lightbox-image');
  const caption = element('p'); const actions = element('div', undefined, 'example-lightbox-actions');
  const previous = element('button', en ? 'Previous' : '上一张');
  const next = element('button', en ? 'Next' : '下一张');
  const toggle = element('button', en ? 'Hide boxes' : '隐藏方框'); toggle.setAttribute('aria-pressed', 'true');
  const close = element('button', en ? 'Close' : '关闭');
  function render() {
    const frame = frames[index]; caption.textContent = (en ? 'Figure ' : '图 ') + frame.index + ' · ' + frame.caption[lang];
    viewport.replaceChildren(annotatedImage(frame, caption.textContent)); previous.disabled = index === 0; next.disabled = index === frames.length - 1;
  }
  previous.onclick = () => { index--; render(); }; next.onclick = () => { index++; render(); };
  toggle.onclick = () => { const hidden = viewport.classList.toggle('hide-example-boxes'); toggle.textContent = hidden ? (en ? 'Show boxes' : '显示方框') : (en ? 'Hide boxes' : '隐藏方框'); toggle.setAttribute('aria-pressed', String(!hidden)); };
  close.onclick = () => dialog.close(); dialog.addEventListener('close', () => dialog.remove(), {once:true});
  actions.append(previous, next, toggle, close); dialog.append(viewport, caption, actions); document.body.append(dialog); render(); dialog.showModal();
}


let hoverPreview = null;
function hideExampleHover() { hoverPreview?.remove(); hoverPreview = null; }
function showExampleHover(button, frame, caption) {
  hideExampleHover();
  const source = button.querySelector('img');
  if (!source?.naturalWidth || document.querySelector('dialog[open]')) return;
  const anchor = button.getBoundingClientRect();
  const margin = 12, gap = 16;
  const availableLeft = anchor.left - gap - margin;
  const availableRight = innerWidth - anchor.right - gap - margin;
  const room = Math.max(availableLeft, availableRight);
  const aspect = source.naturalWidth / source.naturalHeight;
  const width = Math.min(760, innerWidth - 2 * margin, Math.max(280, room), Math.max(120, innerHeight - 110) * aspect);
  hoverPreview = element('div', undefined, 'example-hover-preview');
  hoverPreview.setAttribute('aria-hidden', 'true');
  hoverPreview.style.width = width + 'px';
  const picture = annotatedImage(frame, caption); picture.querySelector('img').loading = 'eager';
  hoverPreview.append(picture, element('p', caption)); document.body.append(hoverPreview);
  const left = availableLeft >= width ? anchor.left - gap - width : availableRight >= width ? anchor.right + gap : (innerWidth - width) / 2;
  const height = width / aspect + hoverPreview.querySelector('p').offsetHeight + 24;
  Object.assign(hoverPreview.style, {left: Math.max(margin, left) + 'px', top: Math.max(margin, Math.min(anchor.top, innerHeight - height - margin)) + 'px'});
}
window.addEventListener('scroll', hideExampleHover, true);
window.addEventListener('resize', hideExampleHover);
window.addEventListener('blur', hideExampleHover);
document.addEventListener('keydown', event => { if (event.key === 'Escape') hideExampleHover(); });
