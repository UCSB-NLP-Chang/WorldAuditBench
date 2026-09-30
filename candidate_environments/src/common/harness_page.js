// Shared harness contract for standalone environment pages (`?harness=1&config=<name>`): implements the same
// `window.__env` API that env/core.js exposes (ready / meta / enable / act / tick / state / targets / flags / probe),
// so harness/bridge.py + harness/runner.py drive the page unchanged.  The page runs in real time: an action holds
// the movement keys for `dist / speed` seconds, samples film frames from the canvas at `film.dt` seconds and returns
// the same payload shape as core.js.  Ported from the reef page (src/water/app/harness.js) and generalised through
// an adapter object; loaded as a classic script (`window.__installHarness(adapter)`).
//
// adapter = {
//   renderer, camera,                         three.js objects (renderer.domElement is the frame source)
//   getPos() -> [x, y, z]                     the player's position (camera or body)
//   getYaw() / getPitch() -> radians          yaw: 0 = -z, positive = turning left (three.js convention)
//   setView(yaw, pitch)                       absolute view in radians
//   keyDown(code) / keyUp(code)               drive the page's own controls (default: KeyboardEvents on window)
//   speed                                     walking speed in world units per second (for dist -> hold time)
//   spawn: { pos, yawDeg }                    where enable() puts the player (config.spawn overrides)
//   teleport(x, y, z)                         used by enable()
//   resetCount() -> int                       increments whenever the page respawned the player
//   config, bugAnswer, film, meta             config json (name/spawn/targets), judge answer, film settings, extra meta
//   dtFrames                                  optional: frames to wait before grabbing a still (default 2)
// }
(function () {
  'use strict';
  window.__installHarness = function installHarness(a) {
    const flags = [];
    let agentOn = false;
    // Virtual clock (`?vclock=1`, the VLA explorer): the page's time sources (performance.now, Date.now, rAF timestamps)
    // are replaced by a clock that only advances inside tick() / act(), in frame-sized sub-steps with one real animation
    // frame each, so a tick is exactly dtMs of simulated time on any device (a paused world, like env/core.js).  Without
    // the flag the page runs on the wall clock as before.
    const VCLOCK = new URLSearchParams(location.search).has('vclock');
    const realNow = performance.now.bind(performance);
    const realRAF = window.requestAnimationFrame.bind(window);
    let vt = realNow(); const dateBase = Date.now() - vt;
    if (VCLOCK) {
      performance.now = () => vt;
      Date.now = () => Math.round(dateBase + vt);
      window.requestAnimationFrame = (cb) => realRAF(() => cb(vt));
    }
    const now = () => (VCLOCK ? vt : realNow());
    const t0 = now();
    const simT = () => (now() - t0) / 1000;
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    // a wait inside an action: wall-clock sleep, or (virtual clock) advance vt in <= 1/60 s steps with one real frame each
    const vsleep = async (ms) => {
      if (!VCLOCK) return sleep(ms);
      let rem = ms;
      while (rem > 1e-6) { const step = Math.min(rem, 1000 / 60); vt += step; rem -= step; await new Promise((r) => realRAF(r)); }
    };
    const nextFrames = (n = 2) => new Promise((res) => { const step = (k) => (k <= 0 ? res() : requestAnimationFrame(() => step(k - 1))); step(n); });
    const keyDown = a.keyDown || ((code) => window.dispatchEvent(new KeyboardEvent('keydown', { code, key: code, bubbles: true })));
    const keyUp = a.keyUp || ((code) => window.dispatchEvent(new KeyboardEvent('keyup', { code, key: code, bubbles: true })));
    const canvas = () => a.renderer.domElement;
    const film = a.film || null;
    const deg = (r) => +((((r * 180 / Math.PI) % 360) + 360) % 360).toFixed(1);
    // boundary notice: humans get the page's DOM overlay; the agent only ever sees the canvas, so the same notice is
    // composited into every captured frame for 1.5 s after the walker was held at the edge of the explorable area
    let noticeUntil = 0, noticeTimer = 0;
    function notice() {
      noticeUntil = now() + 1500;
      const el = document.getElementById('benchmark-boundary-warning');
      if (el) { el.classList.add('is-visible'); clearTimeout(noticeTimer); noticeTimer = setTimeout(() => el.classList.remove('is-visible'), 1500); }
    }
    const noticeOn = () => now() < noticeUntil;
    window.__stampNotice = function (c2d, w, h) {
      const bh = Math.round(h * 0.17);
      c2d.fillStyle = 'rgba(58,4,10,0.88)'; c2d.fillRect(0, 0, w, bh);
      c2d.fillStyle = '#ff5d62'; c2d.font = `bold ${Math.round(h * 0.07)}px sans-serif`; c2d.textAlign = 'center'; c2d.textBaseline = 'middle';
      c2d.fillText('EDGE OF THE EXPLORABLE AREA', w / 2, bh * 0.36);
      c2d.fillStyle = '#ffecec'; c2d.font = `${Math.round(h * 0.045)}px sans-serif`;
      c2d.fillText('Turn around and keep exploring inside', w / 2, bh * 0.74);
    };
    let full = null;
    function fullFrame() {   // still frame, with the notice banner when it is showing
      const c = canvas();
      if (!noticeOn()) return c.toDataURL('image/jpeg', 0.85);
      if (!full) full = document.createElement('canvas');
      full.width = c.width; full.height = c.height;
      const g = full.getContext('2d'); g.drawImage(c, 0, 0); window.__stampNotice(g, full.width, full.height);
      return full.toDataURL('image/jpeg', 0.85);
    }
    // still frames: read the canvas from inside a rAF callback (after the page's render, before the frame is presented)
    function grabFrame() { return new Promise((res) => { const step = (k) => requestAnimationFrame(() => (k <= 1 ? res(fullFrame()) : step(k - 1))); step(a.dtFrames || 2); }); }
    let small = null;
    function smallFrame() {
      if (!small) { small = document.createElement('canvas'); small.width = film.w; small.height = film.h; }
      const g = small.getContext('2d'); g.drawImage(canvas(), 0, 0, film.w, film.h);
      if (noticeOn()) window.__stampNotice(g, film.w, film.h);
      return small.toDataURL('image/jpeg', 0.7);
    }
    function state() {
      const p = a.getPos();
      return { pos: p.map((v) => +v.toFixed(2)), yaw: deg(a.getYaw()), pitch: +(a.getPitch() * 180 / Math.PI).toFixed(1), gems: 0, flags: flags.length };
    }
    const spawn = (a.config && a.config.spawn) || a.spawn || { pos: a.getPos(), yawDeg: 0 };
    // explorable area: config.bounds {minX,maxX,minZ,maxZ} minus config.exclude [{minX,maxX,minZ,maxZ}, ...] (water, cliffs...)
    const bounds = (a.config && a.config.bounds) || null;
    const exclude = (a.config && a.config.exclude) || [];
    const inRect = (r, x, z) => x >= r.minX && x <= r.maxX && z >= r.minZ && z <= r.maxZ;
    // a page may add its own walkability test (adapter.allowed(x, z) -> bool; e.g. the cottage: ground above the pond's water level)
    const allowed = (x, z) => (!bounds || inRect(bounds, x, z)) && !exclude.some((r) => inRect(r, x, z)) && (!a.allowed || a.allowed(x, z));
    let lastOk = null, wasOut = false;
    const holdInside = () => {   // called while walking: step back to the last allowed spot when the walker leaves the area
      const p = a.getPos();
      if (allowed(p[0], p[2])) { lastOk = p; wasOut = false; return false; }
      if (wasOut) return false;   // started outside (a step past the edge): let it walk back in, never trap it
      if (lastOk) { if (a.clamp) a.clamp(lastOk[0], lastOk[2]); else a.teleport(lastOk[0], p[1], lastOk[2]); }
      notice();
      return true;
    };
    function toSpawn() {
      a.teleport(spawn.pos[0], spawn.pos[1], spawn.pos[2]);
      a.setView((spawn.yawDeg || 0) * Math.PI / 180, 0);
    }
    // judge support (eval/score_flags.resolve_answers): answers carry absolute positions
    window.__resolveAnswers = (list) => list.map((x) => ({ ...x, position: (Array.isArray(x.at) ? x.at : [0, 0, 0]).map((v) => +(+v).toFixed(2)) }));
    const bug = a.bugAnswer || null;
    window.__env = {
      get ready() { return true; },
      meta: Object.assign({ config: a.config && a.config.name, renderer: 'webgl (standalone page)', agentMode: true, seed: null, bug: bug ? bug.id : null }, a.meta || {}),
      async enable() { if (a.onEnable) a.onEnable(); toSpawn(); agentOn = true; await nextFrames(3); return true; },   // let the page's physics settle on the spawn
      state,
      targets() { return { ...((a.config && a.config.targets) || {}) }; },
      flags() { return flags.slice(); },
      probe() { return { simT: +simT().toFixed(3), onFloor: true, pos: state().pos, resets: a.resetCount ? a.resetCount() : 0, bugEvents: [] }; },
      async tick(act = {}, dtMs = 50) {
        if (!agentOn) throw new Error('call enable() first');
        await nextFrames(1);
        const before = a.getPos(); const resets0 = a.resetCount ? a.resetCount() : 0;
        a.setView(a.getYaw() - (act.mouseDx || 0) / 600, Math.max(-Math.PI / 2, Math.min(Math.PI / 2, a.getPitch() - (act.mouseDy || 0) / 600)));
        for (const k of (act.keys || [])) keyDown(k);
        await vsleep(dtMs);
        for (const k of (act.keys || [])) keyUp(k);
        holdInside();
        const frame = await grabFrame();
        const p = a.getPos();
        return { frame, moved: +Math.hypot(p[0] - before[0], p[1] - before[1], p[2] - before[2]).toFixed(3), respawned: (a.resetCount ? a.resetCount() : 0) > resets0, nEvents: 0, ...state() };
      },
      async act(act) {
        if (!agentOn) throw new Error('call enable() first');
        await nextFrames(1);   // positions set by a teleport in the previous call are applied by the page's next tick
        const before = a.getPos(); const resets0 = a.resetCount ? a.resetCount() : 0; const start = simT();
        // fixed-tick decisions (agent/ harness): maxSec cuts the action short, holdSec pads the tick to that length
        const maxSec = act.maxSec > 0 ? +act.maxSec : null;
        const holdSec = act.holdSec > 0 ? +act.holdSec : null;
        const capped = (sec) => (maxSec != null ? Math.min(sec, maxSec) : sec);
        const frames = [], frameT = [], filmFrames = [];
        // film frames are sampled inside requestAnimationFrame (right after the page's own render callback), so the
        // drawing buffer is still valid even without preserveDrawingBuffer
        let filming = false, filmDt = 0, filmNext = 0;
        const sampler = () => {
          if (filming) {
            const now = performance.now();
            if (now >= filmNext && filmFrames.length < film.maxFrames) { filmFrames.push({ t: +(simT() - start).toFixed(2), url: smallFrame() }); filmNext = now + Math.max(50, filmDt * 1000); }
            if (filmFrames.length >= film.maxFrames) filming = false;
          }
          if (filming) requestAnimationFrame(sampler);
        };
        const startFilm = (dtSec) => { if (!film) return; filming = true; filmDt = dtSec; filmNext = 0; requestAnimationFrame(sampler); };
        const stopFilm = () => { filming = false; };
        const snap = async () => { frames.push(await grabFrame()); frameT.push(+(simT() - start).toFixed(3)); };
        if (act.action === 'forward' || act.action === 'back') {
          const dist = Math.min(Math.max(act.dist ?? 1.5, 0.3), 4);
          const code = act.action === 'forward' ? 'KeyW' : 'KeyS';
          startFilm(film ? film.dt : 0);
          // hold the key until the requested distance is covered (or the walk is clearly blocked)
          const p0 = a.getPos(); const maxMs = capped(dist / a.speed * 1.6 + 0.4) * 1000; const tStart = now();
          wasOut = !allowed(p0[0], p0[2]); keyDown(code); if (!wasOut) lastOk = p0; let blockedByBounds = false;
          const trace = window.__walkTrace = []; window.__walkEnd = 'time';   // diagnostics: [t, x, y, z, allowed], why the walk ended
          while (now() - tStart < maxMs) {
            await vsleep(16);
            if (holdInside()) { blockedByBounds = true; window.__walkEnd = 'bounds'; break; }
            const p1 = a.getPos();
            if (trace.length < 400) trace.push([+((now() - tStart) / 1000).toFixed(2), +p1[0].toFixed(2), +p1[1].toFixed(2), +p1[2].toFixed(2), allowed(p1[0], p1[2])]);
            if (Math.hypot(p1[0] - p0[0], p1[2] - p0[2]) >= dist) { window.__walkEnd = 'dist'; break; }
          }
          keyUp(code);
          if (blockedByBounds) { await nextFrames(2); holdInside(); }
          // dropping through the ground (hole cases): keep filming until the page respawns the walker (max 2.8 s)
          if (a.getPos()[1] < before[1] - 0.6) {
            const tFall = now();
            while (now() - tFall < 2800 && (a.resetCount ? a.resetCount() : 0) === resets0) await vsleep(60);
            await nextFrames(2);
          }
          stopFilm(); await vsleep(150);
        } else if (act.action === 'turn') {
          a.setView(a.getYaw() - (act.deg ?? 45) * Math.PI / 180, a.getPitch());
          await vsleep(capped(Math.abs(act.deg ?? 45) / 120) * 1000);
        } else if (act.action === 'look') {
          a.setView(a.getYaw(), Math.max(-1.3, Math.min(1.3, a.getPitch() - (act.deg ?? 20) * Math.PI / 180)));
          await vsleep(capped(Math.abs(act.deg ?? 20) / 120) * 1000);
        } else if (act.action === 'interact') {
          startFilm(film ? Math.max(film.dt, 2.8 / (film.maxFrames - 1)) : 0);
          const total = capped(2.8);
          await snap(); await vsleep(Math.min(0.7, total) * 1000); await snap(); await vsleep(Math.max(0, total - 0.7) * 1000); stopFilm();
        } else if (act.action === 'wait') {
          const sec = capped(Math.min(act.ms ?? 1000, 5000) / 1000);
          startFilm(film ? Math.max(film.dt, sec / (film.maxFrames - 1)) : 0);
          await vsleep(sec * 1000); stopFilm();
        } else if (act.action === 'flag') {
          const p = a.getPos();
          flags.push({ pos: p.map((v) => +v.toFixed(2)), note: act.note || '', simT: +simT().toFixed(2) });
        }
        if (holdSec != null) { const rem = holdSec - (simT() - start); if (rem > 0) await vsleep(rem * 1000); }
        await snap();
        const p = a.getPos();
        return {
          frames, frameT, interacted: false, film: filmFrames,
          moved: +Math.hypot(p[0] - before[0], p[1] - before[1], p[2] - before[2]).toFixed(2),
          teleported: false, respawned: (a.resetCount ? a.resetCount() : 0) > resets0,
          simElapsed: +(simT() - start).toFixed(3),
          ...state(),
        };
      },
    };
    return window.__env;
  };
  // film settings from the query string (runner passes obs=film&filmDt=&filmMax=; the agent/ harness also
  // passes filmW/filmH to archive the strip at capture resolution and downsizes for the context itself)
  window.__harnessFilmFromQuery = function (query) {
    return query.get('obs') === 'film' ? { dt: +(query.get('filmDt') || 0.5), maxFrames: +(query.get('filmMax') || 8),
                                           w: +(query.get('filmW') || 480), h: +(query.get('filmH') || 300) } : null;
  };
})();
