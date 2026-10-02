export function connectSocketPlayer(parent, session, onState) {
  const canvas = document.createElement('canvas');
  canvas.width = 1920; canvas.height = 1080;
  canvas.tabIndex = 0;
  canvas.setAttribute('aria-label', 'Live Unreal scene. Click to control, WASD to move, E to interact.');
  Object.assign(canvas.style, {width:'100%',height:'100%',objectFit:'contain',display:'block',outline:'none'});
  parent.append(canvas);
  const context = canvas.getContext('2d', {alpha:false});
  const ws = new WebSocket(`${location.protocol==='https:'?'wss':'ws'}://${location.host}/api/stream/${session.id}?token=${encodeURIComponent(session.token)}`);
  ws.binaryType = 'arraybuffer';
  let closed=false, active=false, live=false, locked=false, decoding=Promise.resolve(), decoder=null;
  const pendingFrames=new Map();
  const render=(frame,sequence)=>{
    if(closed)return;
    const w=frame.displayWidth||frame.width,h=frame.displayHeight||frame.height;
    if(canvas.width!==w||canvas.height!==h){canvas.width=w;canvas.height=h;}
    context.drawImage(frame,0,0);canvas.dataset.frames=String(sequence);
    if(!live){live=true;onState('live');}
    if(ws.readyState===WebSocket.OPEN)ws.send(JSON.stringify({ack:sequence}));
  };
  ws.onopen=async()=>{
    let supported=false;
    if('VideoDecoder' in window){try{supported=(await VideoDecoder.isConfigSupported({codec:'avc1.42C028',optimizeForLatency:true})).supported;}catch{}}
    if(ws.readyState===WebSocket.OPEN)ws.send(JSON.stringify({video:supported?'h264':'jpeg'}));
  };
  const keys = new Map([['KeyW',87],['KeyA',65],['KeyS',83],['KeyD',68],['KeyE',69],['Space',32],['ShiftLeft',16],['ShiftRight',16]]);
  const pressed = new Set();
  const send = data => { if(!closed && ws.readyState===WebSocket.OPEN) ws.send(data); };
  const release = () => { for(const key of pressed) send(new Uint8Array([61,key])); pressed.clear(); };
  const leave = () => { release(); send(new Uint8Array([71])); };
  const fallback = () => { if(closed)return; active=true; onState('Move the mouse over the scene to look. Esc releases control.'); };
  const lockChange = () => { const next=document.pointerLockElement===canvas; if(locked && !next){active=false;leave();} locked=next; };
  const blur = () => { active=false;leave(); };
  document.addEventListener('pointerlockerror', fallback);
  document.addEventListener('pointerlockchange', lockChange);
  window.addEventListener('blur', blur);
  canvas.onblur = blur;
  canvas.onclick = async () => {
    if(!live)return;
    canvas.focus();active=true;send(new Uint8Array([70]));
    if(document.pointerLockElement!==canvas){try{await canvas.requestPointerLock();}catch{fallback();}}
  };
  canvas.onkeydown = event => {
    if(event.code==='Escape'){active=false;leave();if(locked)document.exitPointerLock();return;}
    const key=keys.get(event.code);if(!active||!key)return;
    event.preventDefault();pressed.add(key);send(new Uint8Array([60,key,event.repeat?1:0]));
  };
  canvas.onkeyup = event => {const key=keys.get(event.code);if(key){event.preventDefault();pressed.delete(key);send(new Uint8Array([61,key]));}};
  canvas.onmouseleave = () => {if(!locked)leave();};
  canvas.onmouseenter = () => {if(active)send(new Uint8Array([70]));};
  function coordinates(event){
    const r=canvas.getBoundingClientRect(), scale=Math.min(r.width/canvas.width,r.height/canvas.height);
    const w=canvas.width*scale,h=canvas.height*scale;
    return {x:locked?32768:Math.max(0,Math.min(65535,(event.clientX-r.left-(r.width-w)/2)/w*65535)),
      y:locked?32768:Math.max(0,Math.min(65535,(event.clientY-r.top-(r.height-h)/2)/h*65535)),w,h};
  }
  canvas.onmousemove = event => {
    if(!active)return;
    const c=coordinates(event), b=new ArrayBuffer(9),v=new DataView(b);
    v.setUint8(0,74);v.setUint16(1,c.x,true);v.setUint16(3,c.y,true);
    v.setInt16(5,Math.max(-32767,Math.min(32767,event.movementX/c.w*65534)),true);
    v.setInt16(7,Math.max(-32767,Math.min(32767,event.movementY/c.h*65534)),true);send(b);
  };
  for(const [eventName,type] of [['onmousedown',72],['onmouseup',73]]) canvas[eventName]=event=>{
    if(!active||event.button>2)return;event.preventDefault();
    const c=coordinates(event),b=new ArrayBuffer(6),v=new DataView(b);
    v.setUint8(0,type);v.setUint8(1,event.button);v.setUint16(2,c.x,true);v.setUint16(4,c.y,true);send(b);
  };
  canvas.oncontextmenu=event=>event.preventDefault();
  ws.onmessage = event => {
    if(typeof event.data==='string'){
      const config=JSON.parse(event.data);
      if(config.type==='codec'){
        canvas.dataset.codec=config.codec;
        if(config.codec!=='jpeg'){
          decoder=new VideoDecoder({output:frame=>{
            const sequence=pendingFrames.get(frame.timestamp);pendingFrames.delete(frame.timestamp);
            if(sequence!==undefined)render(frame,sequence);frame.close();
          },error:()=>{if(!closed){onState('disconnected');ws.close();}}});
          decoder.configure({codec:config.codec,codedWidth:config.width,codedHeight:config.height,optimizeForLatency:true});
        }
      }
      return;
    }
    if(!(event.data instanceof ArrayBuffer))return;
    const header=new DataView(event.data),sequence=header.getUint32(0),kind=header.getUint8(4),timestamp=Number(header.getBigUint64(5));
    if(kind!==0){
      pendingFrames.set(timestamp,sequence);
      try{decoder.decode(new EncodedVideoChunk({type:kind===1?'key':'delta',timestamp,data:event.data.slice(13)}));}
      catch{onState('disconnected');ws.close();}
      return;
    }
    decoding=decoding.then(async()=>{
      if(closed)return;
      const bitmap=await createImageBitmap(new Blob([event.data.slice(13)],{type:'image/jpeg'}));
      render(bitmap,sequence);bitmap.close();
    }).catch(()=>{if(!closed){onState('disconnected');ws.close();}});
  };
  ws.onclose=()=>{if(!closed)onState('disconnected');};
  ws.onerror=()=>{if(!closed)onState('disconnected');};
  return {close(){
    leave();closed=true;if(locked)document.exitPointerLock();ws.close();
    if(decoder && decoder.state!=='closed')decoder.close();pendingFrames.clear();
    document.removeEventListener('pointerlockerror',fallback);document.removeEventListener('pointerlockchange',lockChange);window.removeEventListener('blur',blur);
    parent.replaceChildren();
  }};
}
