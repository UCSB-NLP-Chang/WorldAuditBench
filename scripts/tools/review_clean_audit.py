#!/usr/bin/env python3
"""Audit the review site's clean view (`?bug=<case>&noui=1&seed=5`): what a reviewer sees besides the WebGL canvas.

For every environment page in a site directory: load one case through the review URL shape, wait for the world, then
  * list every visible DOM element that paints something over the canvas (text, background, border, image, control),
  * take a screenshot (what the reviewer sees; the agent's frames are the canvas alone),
  * press the keys the clean view must swallow (src/common/noui.py KEYS) and confirm the world state does not change.
usage: review_clean_audit.py --site <dir with the six html files> --out <dir> [--cases sp04-doublespawn,hs10-backcull,...]
"""
import argparse, json, pathlib, sys, time
sys.path.insert(0, '/home/ubuntu/game-auditing'); sys.path.insert(0, '/home/ubuntu/game-auditing/tools')
sys.path.insert(0, '/home/ubuntu/game-auditing/candidate_environments/src/common')
from agent.vla.bridge import Bridge          # noqa: E402
from review_view import FAMILY, READY, STATE  # noqa: E402
from noui import KEYS                      # noqa: E402

DEFAULT_CASES = {'00_sponza_constrained.html': 'sp04-doublespawn', '09_sims_house_builder_constrained.html': 'hs10-backcull',
                 '10_beautiful_water_clean_constrained.html': 'wt05-airwall', '01_mistwood_cottage_constrained.html': 'ct02-clip',
                 '03_sketchbook_airfield_constrained.html': 'af06-hole', '13_beyond_fable_wilderness_constrained.html': 'wl01-float'}
GPU = {'sketch': 'gl-egl'}   # the airfield page is blank under ANGLE Vulkan on this box
OVERLAYS = r"""() => {
  const vw = innerWidth, vh = innerHeight, out = [];
  const canvases = [...document.querySelectorAll('canvas')];
  for (const el of document.querySelectorAll('body *')) {
    if (el.tagName === 'CANVAS' || el.tagName === 'SCRIPT' || el.tagName === 'STYLE' || canvases.some(c => el.contains(c))) continue;
    let a = el, ghost = false;
    while (a && a !== document.documentElement) {
      const s = getComputedStyle(a);
      if (s.display === 'none' || s.visibility === 'hidden' || parseFloat(s.opacity) === 0) { ghost = true; break; }
      a = a.parentElement;
    }
    if (ghost) continue;
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0 || r.right <= 0 || r.bottom <= 0 || r.left >= vw || r.top >= vh) continue;
    const cs = getComputedStyle(el);
    const text = [...el.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join(' ').trim();
    const paints = text || (cs.backgroundColor !== 'rgba(0, 0, 0, 0)' && cs.backgroundColor !== 'transparent') || cs.backgroundImage !== 'none'
      || (cs.borderStyle !== 'none' && parseFloat(cs.borderWidth) > 0) || cs.boxShadow !== 'none' || ['IMG', 'SVG', 'BUTTON', 'INPUT', 'KBD', 'SELECT'].includes(el.tagName);
    if (!paints) continue;
    const cls = typeof el.className === 'string' && el.className.trim() ? '.' + el.className.trim().split(/\s+/).join('.') : '';
    out.push({el: el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + cls, text: text.slice(0, 70), box: [r.left, r.top, r.width, r.height].map(Math.round)});
  }
  return out;
}"""
PACKED_BEACONS = "() => window.__ctx.scene.children.filter(o => o.type === 'Group' && o.children.some(c => c.type === 'Box3Helper' || (c.geometry && c.geometry.type === 'CylinderGeometry'))).map(o => o.visible)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', required=True); ap.add_argument('--out', required=True); ap.add_argument('--cases', default=None)
    ap.add_argument('--extra-wait', type=float, default=4.0)
    a = ap.parse_args()
    site = pathlib.Path(a.site); out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    cases = dict(DEFAULT_CASES)
    if a.cases:   # e.g. sp02-clip,wl12-unload: one case per page, chosen by its prefix
        page_of = {'sp': '00_sponza_constrained.html', 'hs': '09_sims_house_builder_constrained.html', 'wt': '10_beautiful_water_clean_constrained.html',
                   'ct': '01_mistwood_cottage_constrained.html', 'af': '03_sketchbook_airfield_constrained.html', 'wl': '13_beyond_fable_wilderness_constrained.html'}
        for c in a.cases.split(','): cases[page_of[c[:2]]] = c
    report = {}
    groups = {}
    for html, cid in cases.items(): groups.setdefault(GPU.get(FAMILY[html], 'vulkan'), []).append((html, cid))
    for gpu, pages in groups.items():   # one browser at a time (sync Playwright allows a single instance per thread)
      with Bridge(gpu=gpu, size=(960, 600), serve_dir=site) as br:
        br.page.set_default_timeout(180_000)
        for html, cid in pages:
            fam = FAMILY[html]
            url = f'http://127.0.0.1:{br.port}/{html}?bug={cid}&noui=1&seed=5'
            br.console.clear(); br.page_errors.clear(); t0 = time.time()
            br.page.goto(url)
            try:
                br.page.wait_for_function(READY[fam], timeout=240_000)
            except Exception as e:
                report[html] = {'case': cid, 'error': f'not ready: {e}'}; print(html, 'NOT READY'); continue
            time.sleep(a.extra_wait)
            info = {'case': cid, 'load_s': round(time.time() - t0, 1), 'noui_class': br.page.evaluate("() => document.documentElement.classList.contains('noui')"),
                    'noui_block': br.page.evaluate("() => !!(window.__noui && window.__noui.keysBlocked)"),
                    'pointer_locked': br.page.evaluate('() => !!document.pointerLockElement')}
            br.page.screenshot(path=str(out / f'{fam}-{cid}-view.png'))
            info['overlays'] = br.page.evaluate(OVERLAYS)
            # keys outside the agent's action space must not change anything
            state_js = STATE[fam]
            before = br.page.evaluate(state_js)
            beacons_before = br.page.evaluate(PACKED_BEACONS) if fam == 'packed' else None
            keys = KEYS[fam] + (['KeyV'] if fam != 'packed' else [])
            for k in keys:
                if k == 'KeyR' and fam == 'sketch': br.page.keyboard.press('Shift+KeyR')
                else: br.page.keyboard.press(k)
                time.sleep(0.4)
            time.sleep(1.0)
            after = br.page.evaluate(state_js)
            info['keys_pressed'] = keys
            info['state_before'] = before; info['state_after'] = after
            if fam == 'packed': info['beacons_before'] = beacons_before; info['beacons_after'] = br.page.evaluate(PACKED_BEACONS)
            info['overlays_after_keys'] = br.page.evaluate(OVERLAYS)
            br.page.screenshot(path=str(out / f'{fam}-{cid}-after-keys.png'))
            info['errors'] = br.page_errors[:5]; info['console_err'] = [t for ty, t in br.console if ty == 'error'][:6]
            report[html] = info
            print(f"{html}: {len(info['overlays'])} overlay element(s) visible; noui class={info['noui_class']} block={info['noui_block']}")
            for o in info['overlays']: print('   ', o['el'], repr(o['text']), o['box'])
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
