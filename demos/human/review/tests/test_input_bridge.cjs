const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const listeners={},winListeners={};
const doc={hidden:false,pointerLockElement:null,addEventListener(t,f){(listeners[t]??=[]).push(f)},dispatchEvent(e){for(const f of listeners[e.type]||[])f(e)}};
const win={addEventListener(t,f){(winListeners[t]??=[]).push(f)}};
class Key{constructor(type,props){this.type=type;Object.assign(this,props)}preventDefault(){this.defaultPrevented=true}}
vm.runInNewContext(fs.readFileSync(__dirname+'/../static/review-bridge.js','utf8'),{window:win,document:doc,KeyboardEvent:Key,setInterval(){},Date,Map,Set,Proxy,Reflect,Object,ArrayBuffer,Uint8Array});
const events=[];doc.addEventListener('keyup',e=>events.push(e));
for(const [code,keyCode] of [['KeyW',87],['KeyA',65],['KeyS',83],['KeyD',68]]){
 const down=new Key('keydown',{code,keyCode:229,isComposing:true});doc.dispatchEvent(down);assert.equal(down.keyCode,keyCode);assert(down.defaultPrevented);
 const up=new Key('keyup',{code,keyCode:229,metaKey:true,target:{closest:()=>true}});doc.dispatchEvent(up);assert.equal(up.keyCode,keyCode);
}
const text=new Key('keydown',{code:'KeyW',keyCode:229,target:{closest:()=>true}});doc.dispatchEvent(text);assert.equal(text.keyCode,229);
doc.dispatchEvent(new Key('keydown',{code:'KeyW',keyCode:229}));winListeners.blur.forEach(f=>f());assert.equal(events.at(-1).keyCode,87);const n=events.length;winListeners.blur.forEach(f=>f());assert.equal(events.length,n);
console.log('PASS: physical WASD, IME 229, modifier keyup, editable isolation and blur release');
