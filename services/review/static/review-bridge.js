/* Runs only in the game iframe, before the official player. No review text is observed. */
'use strict';
(()=>{
 const health=window.reviewHealth={checkedAt:0,peer:'new',inputOpen:false,frames:0,lastFrameAt:0,lastKey:null,keysSent:0,focused:false,pointerLocked:false};
 const peers=new Set(),channels=new Set();
 const Native=window.RTCPeerConnection;
 if(Native)window.RTCPeerConnection=new Proxy(Native,{construct(target,args){const pc=Reflect.construct(target,args);peers.add(pc);return pc;}});
 if(window.RTCDataChannel){const send=RTCDataChannel.prototype.send;RTCDataChannel.prototype.send=function(data){const result=send.call(this,data);channels.add(this);if(data instanceof ArrayBuffer){const b=new Uint8Array(data);if(b[0]===60||b[0]===61){health.keysSent++;health.lastKey={type:b[0]===60?'down':'up',keyCode:b[1],at:Date.now()};}}return result;};}
 // Physical game controls are independent of the active keyboard layout/IME.
 const physical={KeyW:87,KeyA:65,KeyS:83,KeyD:68};
 const held=new Map();
 const enteringButtons=new Set();
 document.addEventListener('mousedown',event=>{if(document.pointerLockElement||event.target?.closest?.('video')){enteringButtons.add(event.button);event.preventDefault();event.stopImmediatePropagation();}},true);
 document.addEventListener('mouseup',event=>{if(enteringButtons.delete(event.button)){event.preventDefault();event.stopImmediatePropagation();}},true);
 document.addEventListener('dblclick',event=>{if(document.pointerLockElement||event.target?.closest?.('video')){event.preventDefault();event.stopImmediatePropagation();}},true);
 for(const type of ['keydown','keyup'])document.addEventListener(type,event=>{
  if(type==='keydown'&&(event.code==='Escape'||event.key==='Escape')&&document.pointerLockElement){event.preventDefault();event.stopImmediatePropagation();document.exitPointerLock();release();return;}
  const releasing=type==='keyup'&&held.has(event.code);
  if(!releasing&&event.target?.closest?.('input,textarea,select,[contenteditable="true"]'))return;
  const key=physical[event.code];if(!key)return;
  if(!releasing&&(event.metaKey||event.ctrlKey||event.altKey))return;
  Object.defineProperty(event,'keyCode',{value:key});
  event.preventDefault();
  if(type==='keydown')held.set(event.code,key);else held.delete(event.code);
 },true);
 function release(){for(const [code,keyCode] of held)document.dispatchEvent(new KeyboardEvent('keyup',{code,keyCode,bubbles:true}));held.clear();}
 function releaseCapture(){release();if(document.pointerLockElement)document.exitPointerLock();}
 window.addEventListener('pagehide',releaseCapture);window.addEventListener('blur',release);document.addEventListener('pointerlockchange',()=>{if(!document.pointerLockElement)release();});document.addEventListener('visibilitychange',()=>{if(document.hidden)releaseCapture();});
 document.addEventListener('pointerdown',event=>{const v=event.target.closest?.('video');if(v){v.tabIndex=0;window.focus();v.focus({preventScroll:true});}},true);
 let checking=false;
 setInterval(async()=>{if(checking)return;checking=true;try{
  if(window.pixelStreaming?.config.isFlagEnabled('HoveringMouse'))window.pixelStreaming.config.setFlagEnabled('HoveringMouse',false);
  health.pointerLocked=Boolean(document.pointerLockElement);
  const pc=[...peers].reverse().find(p=>p.connectionState!=='closed');health.peer=pc?.connectionState||'closed';
  health.inputOpen=[...channels].some(c=>c.readyState==='open');health.focused=document.hasFocus()&&document.activeElement?.tagName==='VIDEO';
  if(pc){let frames=0;for(const s of (await pc.getStats()).values())if(s.type==='inbound-rtp'&&(s.kind==='video'||s.mediaType==='video'))frames+=s.framesDecoded||0;if(frames>health.frames)health.lastFrameAt=Date.now();health.frames=frames;}
  health.checkedAt=Date.now();
 }catch{health.peer='unknown';}finally{checking=false;}},1000);
})();
