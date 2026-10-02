import { Config, PixelStreaming, Logger, LogLevel, Flags } from '@epicgames-ps/lib-pixelstreamingfrontend-ue5.6';
import { connectSocketPlayer } from './socket_player.js';
Logger.InitLogging(LogLevel.Warning, false);
export function connectPlayer(parent, session, onState) {
  if (session.transport === 'websocket') return connectSocketPlayer(parent, session, onState);
  const config = new Config({useUrlParams:false, initialSettings:{
    ss: `${location.protocol === 'https:' ? 'wss':'ws'}://${location.host}/api/signal/${session.id}?token=${encodeURIComponent(session.token)}`,
    AutoConnect:true, AutoPlayVideo:true, StartVideoMuted:true,
    HoveringMouse:false, WaitForStreamer:true, KeyboardInput:true, MouseInput:true,
    TouchInput:true
  }});
  const player = new PixelStreaming(config, {videoElementParent:parent});
  parent.tabIndex = 0;
  const fallback = () => {
    config.setFlagEnabled(Flags.HoveringMouseMode, true);
    onState('Mouse look: move over the scene to look; move outside it to release control.');
  };
  document.addEventListener('pointerlockerror', fallback);
  player.addEventListener('playStream', () => onState('live'));
  player.addEventListener('webRtcDisconnected', () => onState('disconnected'));
  player.addEventListener('playStreamError', () => onState('Click the scene to enable playback.'));
  parent.onclick = () => { parent.focus(); player.play(); };
  return { close(){ document.removeEventListener('pointerlockerror', fallback); player.disconnect(); parent.replaceChildren(); parent.onclick=null; } };
}
