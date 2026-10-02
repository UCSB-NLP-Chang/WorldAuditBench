// First-person diver controller (benchmark contract from the previous build, kept API-compatible):
//   player = { isActive, start, exit, reset, setPosition([x,y,z]), getState(), update(time) }
import * as THREE from 'three';

export function createDiveController({ camera, domElement, controls, app, seabedHeight, sampleOceanSurface, harnessMode = false, bounds = 27 }) {
  let active = false, yaw = 0, pitch = -0.08, lastTime = null;
  const keys = new Set();
  // v3: solid rocks. colliders = [{x,y,z,r,obj}] spheres or {box:{min,max}} (invisible walls); holes = seabed
  // patches without a floor (the diver drops through and respawns).  Filled by main.js / bugs.js.
  const colliders = [];
  const holes = [];
  const DIVER_R = 0.32;
  function resolveColliders(p) {
    for (const c of colliders) {
      if (c.box) {
        const b = c.box;
        if (p.x > b.min.x - DIVER_R && p.x < b.max.x + DIVER_R && p.y > b.min.y - DIVER_R && p.y < b.max.y + DIVER_R && p.z > b.min.z - DIVER_R && p.z < b.max.z + DIVER_R) {
          const dx = Math.min(p.x - (b.min.x - DIVER_R), (b.max.x + DIVER_R) - p.x);
          const dz = Math.min(p.z - (b.min.z - DIVER_R), (b.max.z + DIVER_R) - p.z);
          const dy = Math.min(p.y - (b.min.y - DIVER_R), (b.max.y + DIVER_R) - p.y);
          if (dx <= dz && dx <= dy) p.x += (p.x - (b.min.x + b.max.x) / 2 > 0 ? dx : -dx);
          else if (dz <= dy) p.z += (p.z - (b.min.z + b.max.z) / 2 > 0 ? dz : -dz);
          else p.y += (p.y - (b.min.y + b.max.y) / 2 > 0 ? dy : -dy);
        }
        continue;
      }
      // ellipsoid collider (rx, ry, rz): work in the normalised space where it is a unit sphere
      const rx = (c.rx ?? c.r) + DIVER_R, ry = (c.ry ?? c.r) + DIVER_R, rz = (c.rz ?? c.r) + DIVER_R;
      const nx = (p.x - c.x) / rx, ny = (p.y - c.y) / ry, nz = (p.z - c.z) / rz;
      const n2 = nx * nx + ny * ny + nz * nz;
      if (n2 < 1 && n2 > 1e-6) {
        const n = Math.sqrt(n2); const k = (1 - n) / n;   // push out along the normalised radial direction
        p.x += nx * k * rx; p.y += ny * k * ry; p.z += nz * k * rz;
      }
    }
  }
  function inHole(x, z) { return holes.some((h) => Math.hypot(x - h.x, z - h.z) < h.r); }
  const spawn = new THREE.Vector3(0, -1.6, 11.5);
  const movement = new THREE.Vector3();
  const forward = new THREE.Vector3();
  const right = new THREE.Vector3();
  const ui = document.querySelector('[data-clean-dive-ui]');
  const status = document.querySelector('[data-clean-dive-status]');
  const startButton = document.querySelector('[data-clean-dive-start]');
  const resumeButton = document.querySelector('[data-clean-dive-resume]');
  const resetButton = document.querySelector('[data-clean-dive-reset]');
  const exitButton = document.querySelector('[data-clean-dive-exit]');
  if (harnessMode && ui) ui.hidden = true;

  function applyLook() {
    camera.rotation.order = 'YXZ';
    camera.rotation.y = yaw;
    camera.rotation.x = pitch;
    camera.rotation.z = 0;
  }
  function setStatus(text) { if (status) status.textContent = text; }
  let resetCount = 0;
  function reset() {
    resetCount++;
    camera.position.copy(spawn);
    yaw = 0; pitch = -0.08; lastTime = null;
    applyLook();
    setStatus('Back at the start');
  }
  function lock() {
    if (!active || document.pointerLockElement === domElement) return;
    try { domElement.requestPointerLock?.(); } catch { setStatus('Click the view to take control'); }
  }
  function start() {
    if (harnessMode) return;
    active = true;
    controls.enabled = false;
    app.classList.add('is-clean-dive-active');
    reset();
    lock();
  }
  function exit() {
    active = false;
    keys.clear();
    document.exitPointerLock?.();
    controls.enabled = true;
    app.classList.remove('is-clean-dive-active', 'is-clean-dive-locked');
    camera.position.set(7.8, 3.65, 10.8);
    controls.target.set(0, 0.54, 0);
    controls.update();
    setStatus('Observer mode');
  }
  function onKeyDown(event) {
    if (!active) return;
    if (['Space', 'Tab'].includes(event.code)) event.preventDefault();
    keys.add(event.code);
    if (!event.repeat && event.code === 'KeyR') reset();
  }
  function onKeyUp(event) { keys.delete(event.code); }
  function onMouseMove(event) {
    if (!active || document.pointerLockElement !== domElement) return;
    yaw -= event.movementX * 0.00215;
    pitch -= event.movementY * 0.00215;
    pitch = THREE.MathUtils.clamp(pitch, -1.42, 1.42);
    applyLook();
  }
  function onPointerLock() {
    const locked = document.pointerLockElement === domElement;
    app.classList.toggle('is-clean-dive-locked', active && locked);
    if (locked) setStatus('Exploring the reef');
    else if (active) setStatus('Paused · click the view to continue');
    if (!locked) keys.clear();
  }

  startButton?.addEventListener('click', start);
  resumeButton?.addEventListener('click', lock);
  resetButton?.addEventListener('click', reset);
  exitButton?.addEventListener('click', exit);
  domElement.addEventListener('click', () => { if (active && document.pointerLockElement !== domElement) lock(); });
  window.addEventListener('keydown', onKeyDown);
  window.addEventListener('keyup', onKeyUp);
  window.addEventListener('mousemove', onMouseMove);
  document.addEventListener('pointerlockchange', onPointerLock);

  const api = {
    colliders, holes,
    get resetCount() { return resetCount; },
    isActive: () => active,
    start, exit, reset,
    setPosition(position) {
      if (Array.isArray(position) && position.length === 3) camera.position.fromArray(position);
      return api.getState();
    },
    setView(nextYaw, nextPitch) {
      yaw = nextYaw;
      if (nextPitch !== undefined) pitch = THREE.MathUtils.clamp(nextPitch, -1.42, 1.42);
      applyLook();
    },
    // headless harness helper: activate without pointer lock, keys still drive the diver
    activate(useLock = true) {
      active = true;
      controls.enabled = false;
      app.classList.add('is-clean-dive-active');
      if (useLock) lock();
      else setStatus('First-person dive · click the view to look around with the mouse');
      lastTime = null;
      applyLook();
    },
    getState() {
      return {
        active,
        pointerLocked: document.pointerLockElement === domElement,
        position: camera.position.toArray(),
        rotation: { yaw, pitch },
      };
    },
    update(time) {
      const delta = lastTime === null ? 0 : THREE.MathUtils.clamp(time - lastTime, 0, 0.1);
      lastTime = time;
      if (!active) return;
      if (document.pointerLockElement !== domElement && !api.headless) return;
      forward.set(-Math.sin(yaw), 0, -Math.cos(yaw));
      right.set(Math.cos(yaw), 0, -Math.sin(yaw));
      movement.set(0, 0, 0);
      if (keys.has('KeyW')) movement.add(forward);
      if (keys.has('KeyS')) movement.sub(forward);
      if (keys.has('KeyD')) movement.add(right);
      if (keys.has('KeyA')) movement.sub(right);
      // no ascend/descend keys: the diver cruises at a fixed depth, the same action space as the agent (move, turn, look)
      if (movement.lengthSq() > 0) {
        movement.normalize();
        const speed = keys.has('ShiftLeft') || keys.has('ShiftRight') ? 6 : 3.15;
        camera.position.addScaledVector(movement, speed * delta);
        camera.position.x = THREE.MathUtils.clamp(camera.position.x, -bounds, bounds);
        camera.position.z = THREE.MathUtils.clamp(camera.position.z, -bounds, bounds);
      }
      resolveColliders(camera.position);
      const floorY = seabedHeight(camera.position.x, camera.position.z);
      const surface = sampleOceanSurface(camera.position.x, camera.position.z, time).height - 0.38;
      if (inHole(camera.position.x, camera.position.z)) {
        // no floor here (hole bug): sink, and respawn once well below the sand
        camera.position.y -= 4.0 * delta;
        if (camera.position.y < floorY - 1.5) { reset(); setStatus('Fell out of the world, back at the start'); }
      } else {
        const bottom = floorY + 0.55;
        camera.position.y = THREE.MathUtils.clamp(camera.position.y, bottom, Math.max(bottom + 0.1, surface));
      }
      applyLook();
    },
  };
  api.headless = false;
  return api;
}
