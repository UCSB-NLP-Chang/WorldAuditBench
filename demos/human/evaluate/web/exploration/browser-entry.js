/* Human exploration entry: same environment simulation, without answer/debug UI. */
import * as THREE from 'three';
import {initEnv} from './core.js';
THREE.DefaultLoadingManager.setURLModifier(u => window.__vfsUrl(u) || u);
const $ = id => document.getElementById(id);
const locked = () => document.pointerLockElement === document.body;
let ctx, boundaryTimer;
const fx = {
  toast(m) { $('toast').textContent=m; $('toast').classList.add('on'); setTimeout(()=>$('toast').classList.remove('on'),2000); },
  fade() { $('fade').style.opacity=1;setTimeout(()=>$('fade').style.opacity=0,350); },
  prompt(t) { $('prompt').textContent=t; },
  hud() {},
  progress(m) { $('status').textContent=m || '正在准备环境…'; },
  boundary() { $('bwarn').classList.add('on');clearTimeout(boundaryTimer);boundaryTimer=setTimeout(()=>$('bwarn').classList.remove('on'),1500); }
};
try {
  ctx=await initEnv({configUrl:'./configs/task.json',agentMode:false,fx});
  // Remove upstream privileged inspection/action handles from the human surface.
  delete window.__ctx; delete window.__env;
  $('title').textContent='探索环境'; $('desc').textContent='WASD 移动 · 鼠标观察 · E 交互 · R 回到起点 · F 截图';
  $('status').textContent='环境已就绪'; $('enter').disabled=false;
  window.bfBrowserReady=true;
} catch(error) { $('status').textContent='环境加载失败，请重新进入。';console.error(error); }
$('enter').onclick=()=>{if(ctx)document.body.requestPointerLock();};
document.addEventListener('pointerlockchange',()=>{
  const on=locked();$('panel').classList.toggle('hidden',on);
  for(const id of ['cross','hud','keys'])$(id).classList.toggle('on',on);
  if(!on&&ctx)for(const key of Object.keys(ctx.keys))ctx.keys[key]=false;
});
document.body.addEventListener('mousemove',e=>{
  if(!locked()||!ctx)return;
  ctx.camera.rotation.y-=e.movementX/600;ctx.camera.rotation.x-=e.movementY/600;
  ctx.camera.rotation.x=Math.max(-Math.PI/2,Math.min(Math.PI/2,ctx.camera.rotation.x));
});
addEventListener('keydown',e=>{if(!ctx||!locked())return;ctx.keys[e.code]=true;if(e.code==='KeyR')ctx.respawn();if(e.code==='KeyE'&&!e.repeat)ctx.useAimed();});
addEventListener('keyup',e=>{if(ctx)ctx.keys[e.code]=false;});
