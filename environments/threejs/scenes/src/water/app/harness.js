// Harness contract for the reef page (`?harness=1&config=<wtXX>`): the same `window.__env` API that
// environments/threejs/runtime/core.js exposes for the built-in scenes, so agent/vla/bridge.py + agent/vla/runner.py can run the S1
// audit (and the VLA `tick`) on this standalone environment unchanged.  The reef runs in real time (no
// sim-clock pause between actions): an action holds the diver's keys for its duration, samples film
// frames at `film.dt` seconds and returns the same payload shape as core.js.
import * as THREE from 'three';

export function installHarness({ renderer, camera, diver, config, bugAnswer, film, speed = 3.15 }) {
  const flags = [];
  let agentOn = false;
  // Virtual clock (`?vclock=1`, the VLA explorer): see src/common/harness_page.js - the page's time sources only advance
  // inside tick() / act(), in frame-sized sub-steps with one real animation frame each (a paused world on any device).
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
  const vsleep = async (ms) => {
    if (!VCLOCK) return sleep(ms);
    let rem = ms;
    while (rem > 1e-6) { const step = Math.min(rem, 1000 / 60); vt += step; rem -= step; await new Promise((r) => realRAF(r)); }
  };
  const nextFrames = (n = 2) => new Promise((res) => { const step = (k) => (k <= 0 ? res() : requestAnimationFrame(() => step(k - 1))); step(n); });
  const key = (code, down) => window.dispatchEvent(new KeyboardEvent(down ? 'keydown' : 'keyup', { code, bubbles: true }));
  async function grabFrame() { await nextFrames(2); return renderer.domElement.toDataURL('image/jpeg', 0.85); }
  let small = null;
  function smallFrame() {
    if (!small) { small = document.createElement('canvas'); small.width = film.w; small.height = film.h; }
    small.getContext('2d').drawImage(renderer.domElement, 0, 0, film.w, film.h);
    return small.toDataURL('image/jpeg', 0.7);
  }
  const rot = () => diver.getState().rotation;
  function state() {
    const p = camera.position, r = rot();
    return {
      pos: [+p.x.toFixed(2), +p.y.toFixed(2), +p.z.toFixed(2)],
      yaw: +((THREE.MathUtils.euclideanModulo(r.yaw, Math.PI * 2)) * 180 / Math.PI).toFixed(1),
      pitch: +(r.pitch * 180 / Math.PI).toFixed(1),
      gems: 0, flags: flags.length,
    };
  }
  const spawn = config.spawn || { pos: [0, -4.4, 11.5], yawDeg: 0 };
  function toSpawn() {
    camera.position.set(spawn.pos[0], spawn.pos[1], spawn.pos[2]);
    diver.setView((spawn.yawDeg || 0) * Math.PI / 180, 0);
  }

  // judge support (judge/score_flags.resolve_answers): the reef's answers carry absolute positions
  window.__resolveAnswers = (list) => list.map((a) => ({ ...a, position: (Array.isArray(a.at) ? a.at : [0, 0, 0]).map((v) => +(+v).toFixed(2)) }));

  window.__env = {
    get ready() { return true; },
    meta: { config: config.name, renderer: 'webgl (reef page)', agentMode: true, three: THREE.REVISION, seed: null, bug: bugAnswer ? bugAnswer.id : null },
    enable() { diver.headless = true; diver.activate(false); toSpawn(); agentOn = true; },
    state,
    targets() { return { ...(config.targets || {}) }; },
    flags() { return flags.slice(); },
    probe() { return { simT: +simT().toFixed(3), onFloor: true, pos: state().pos, resets: diver.resetCount, bugEvents: [] }; },
    async tick(a = {}, dtMs = 50) {
      if (!agentOn) throw new Error('call enable() first');
      const before = camera.position.clone(); const resets0 = diver.resetCount;
      const r = rot();
      diver.setView(r.yaw - (a.mouseDx || 0) / 600, Math.max(-Math.PI / 2, Math.min(Math.PI / 2, r.pitch - (a.mouseDy || 0) / 600)));
      for (const k of (a.keys || [])) key(k, true);
      await vsleep(dtMs);
      for (const k of (a.keys || [])) key(k, false);
      await nextFrames(1);
      return { frame: renderer.domElement.toDataURL('image/jpeg', 0.85), moved: +camera.position.distanceTo(before).toFixed(3), respawned: diver.resetCount > resets0, nEvents: 0, ...state() };
    },
    async act(a) {
      if (!agentOn) throw new Error('call enable() first');
      const before = camera.position.clone(); const resets0 = diver.resetCount; const start = simT();
      const maxSec = a.maxSec > 0 ? +a.maxSec : null;   // fixed-tick decisions: cut the action short
      const holdSec = a.holdSec > 0 ? +a.holdSec : null; // ... and pad the tick to this length
      const capped = (s) => (maxSec != null ? Math.min(s, maxSec) : s);
      const frames = [], frameT = [], filmFrames = [];
      let filming = false, filmNext = 0, filmDtMs = 0;
      // film frames are sampled from animation frames (no time advance of their own), so the virtual clock stays exact
      const sampler = () => {
        if (!filming) return;
        if (now() >= filmNext && filmFrames.length < film.maxFrames) { filmFrames.push({ t: +(simT() - start).toFixed(2), url: smallFrame() }); filmNext = now() + filmDtMs; }
        if (filmFrames.length >= film.maxFrames) { filming = false; return; }
        realRAF(sampler);
      };
      const startFilm = (dtSec) => { if (!film) return; filming = true; filmDtMs = Math.max(50, dtSec * 1000); filmNext = 0; realRAF(sampler); };
      const stopFilm = () => { filming = false; };
      const snap = async () => { frames.push(await grabFrame()); frameT.push(+(simT() - start).toFixed(3)); };
      const r = rot();
      if (a.action === 'forward' || a.action === 'back') {
        const dist = Math.min(Math.max(a.dist ?? 1.5, 0.3), 4);
        const code = a.action === 'forward' ? 'KeyW' : 'KeyS';
        startFilm(film ? film.dt : 0);
        key(code, true); await vsleep(capped(dist / speed) * 1000); key(code, false);
        stopFilm(); await vsleep(120);
      } else if (a.action === 'turn') {
        diver.setView(r.yaw - (a.deg ?? 45) * Math.PI / 180, r.pitch);
        await vsleep(capped(Math.abs(a.deg ?? 45) / 120) * 1000);
      } else if (a.action === 'look') {
        diver.setView(r.yaw, Math.max(-1.3, Math.min(1.3, r.pitch - (a.deg ?? 20) * Math.PI / 180)));
        await vsleep(capped(Math.abs(a.deg ?? 20) / 120) * 1000);
      } else if (a.action === 'interact') {
        startFilm(film ? Math.max(film.dt, 2.8 / (film.maxFrames - 1)) : 0);
        const total = capped(2.8);
        await snap(); await vsleep(Math.min(0.7, total) * 1000); await snap(); await vsleep(Math.max(0, total - 0.7) * 1000); stopFilm();
      } else if (a.action === 'wait') {
        const sec = capped(Math.min(a.ms ?? 1000, 5000) / 1000);
        startFilm(film ? Math.max(film.dt, sec / (film.maxFrames - 1)) : 0);
        await vsleep(sec * 1000); stopFilm();
      } else if (a.action === 'flag') {
        const p = camera.position;
        flags.push({ pos: [+p.x.toFixed(2), +p.y.toFixed(2), +p.z.toFixed(2)], note: a.note || '', simT: +simT().toFixed(2) });
      }
      if (holdSec != null) { const rem = holdSec - (simT() - start); if (rem > 0) await vsleep(rem * 1000); }
      await snap();
      return {
        frames, frameT, interacted: false, film: filmFrames,
        moved: +camera.position.distanceTo(before).toFixed(2),
        teleported: false, respawned: diver.resetCount > resets0,
        simElapsed: +(simT() - start).toFixed(3),
        ...state(),
      };
    },
  };
  return window.__env;
}
