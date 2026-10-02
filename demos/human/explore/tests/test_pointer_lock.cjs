// Deterministic DOM-event model using the actual old/new bridge scripts and the
// actual deployed player's lock callbacks. Does not open a browser or game session.
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const root = __dirname;
const official = fs.readFileSync(path.join(root, 'player-pointer-methods.js'), 'utf8');
async function run(file) {
  const listeners = new Map();
  const document = {
    pointerLockElement: null,
    addEventListener(type, callback) { if (!listeners.has(type)) listeners.set(type, new Set()); listeners.get(type).add(callback); },
    removeEventListener(type, callback) { listeners.get(type)?.delete(callback); },
    dispatchEvent(event) { for (const callback of [...(listeners.get(event.type) || [])]) callback(event); },
    exitPointerLock() { this.pointerLockElement = null; this.dispatchEvent({type: 'pointerlockchange'}); }
  };
  class Element {
    constructor(tag) { this.tagName = tag; this.isConnected = true; }
    requestPointerLock() { document.pointerLockElement = this; document.dispatchEvent({type: 'pointerlockchange'}); return Promise.resolve(); }
    focus() {}
    closest(selector) { return selector === 'video' && this.tagName === 'VIDEO' ? this : null; }
  }
  const window = {addEventListener() {}, focus() {}};
  const context = vm.createContext({window, document, Element, setInterval() {}, KeyboardEvent: class {}, console, lib_pixelstreamingcommon_ue5_6_1: {Logger: {Info() {}}}});
  vm.runInContext(fs.readFileSync(file, 'utf8'), context);
  const callbacks = vm.runInContext('({' + official.trim().replace(/}\s+(?=on[A-Z])/g, '},\n') + '})', context);
  const video = new Element('VIDEO');
  const controller = {videoElementParent: new Element('DIV'), onMouseMoveListener() {}, activeKeys: {getActiveKeys: () => []}, streamMessageController: {toStreamerHandlers: new Map()}};
  document.addEventListener('pointerlockchange', callbacks.onLockStateChange.bind(controller));
  document.dispatchEvent({type: 'pointerdown', target: video});
  await Promise.resolve();
  callbacks.onRequestLock.call(controller);
  await Promise.resolve();
  document.exitPointerLock();
  if (listeners.get('mousemove')?.has(controller.onMouseMoveListener)) throw new Error('Mouse listener remains after release');
  callbacks.onRequestLock.call(controller);
  await Promise.resolve();
  return {lockedElement: document.pointerLockElement?.tagName, expectedElement: controller.videoElementParent.tagName, officialMouseMoveRegistered: listeners.get('mousemove')?.has(controller.onMouseMoveListener) || false};
}
(async () => {
  const report = {
    method: 'deterministic DOM-event model, not a live browser measurement',
    current: await run(path.join(root, '../web/exploration/input-bridge.js'))
  };
  console.log(JSON.stringify(report, null, 2));
  if (!report.current.officialMouseMoveRegistered || report.current.lockedElement !== report.current.expectedElement) process.exitCode = 1;
})();
