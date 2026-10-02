// List streamers without subscribing or occupying the viewer's single player slot.
const { createRequire } = require('node:module');
const path = require('node:path');
const [root, port] = process.argv.slice(2);
const WebSocket = createRequire(path.join(root, 'package.json'))('ws');
const socket = new WebSocket(`ws://127.0.0.1:${Number(port)}`);
let finished = false;
const timer = setTimeout(() => finish(false), 4000);
function finish(ready) {
  if (finished) return;
  finished = true;
  clearTimeout(timer);
  socket.terminate();
  process.exitCode = ready ? 0 : 1;
}
socket.on('open', () => socket.send(JSON.stringify({ type: 'listStreamers' })));
socket.on('message', bytes => {
  try {
    const message = JSON.parse(bytes.toString());
    if (message.type === 'streamerList') finish(message.ids?.includes('DefaultStreamer'));
  } catch { finish(false); }
});
socket.on('error', () => finish(false));
socket.on('close', () => finish(false));
