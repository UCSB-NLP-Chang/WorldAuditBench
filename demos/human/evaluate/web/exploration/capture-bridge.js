/* Runs before Pixel Streaming registers keyboard handlers. Captures the displayed frame. */
(() => {
  'use strict';
  function capture() {
    const scene = window.bfBrowserReady && document.querySelector('canvas');
    if(scene){
      const capturedAt=Date.now()/1000;
      try{scene.toBlob(blob=>parent.postMessage(blob?{type:'bf-capture',blob,capturedAt}:{type:'bf-capture-error',message:'截图失败，请重试。'},location.origin),'image/png');}
      catch{parent.postMessage({type:'bf-capture-error',message:'截图失败，请重新进入环境。'},location.origin);}
      return;
    }
    const video = document.querySelector('video');
    if (!video || video.readyState < 2 || !video.videoWidth || video.paused || video.ended) {
      parent.postMessage({type: 'bf-capture-error', message: '视频尚未就绪，请等待画面播放后再 Flag。'}, location.origin); return;
    }
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth; canvas.height = video.videoHeight;
    const capturedAt = Date.now() / 1000;
    try {
      canvas.getContext('2d').drawImage(video, 0, 0);
      canvas.toBlob(blob => {
        if (blob) parent.postMessage({type: 'bf-capture', blob, capturedAt}, location.origin);
        else parent.postMessage({type: 'bf-capture-error', message: '截图失败，请重试。'}, location.origin);
      }, 'image/png');
    } catch { parent.postMessage({type: 'bf-capture-error', message: '无法截取当前画面，请重新连接。'}, location.origin); }
  }
  window.addEventListener('message', event => {
    if (event.origin === location.origin && event.source === parent && event.data?.type === 'bf-capture-request') capture();
  });
  for (const type of ['keydown', 'keyup']) document.addEventListener(type, event => {
    if (event.code !== 'KeyF' || event.target.closest?.('input,textarea,select,[contenteditable="true"]') || event.ctrlKey || event.metaKey || event.altKey) return;
    event.preventDefault(); event.stopImmediatePropagation();
    if (type === 'keydown' && !event.repeat) capture();
  }, true);
})();
