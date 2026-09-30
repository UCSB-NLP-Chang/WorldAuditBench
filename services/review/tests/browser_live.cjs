/* Real Pixel Streaming QA; run ONLY after the parent authorizes a live slot.
 REVIEW_LIVE_ORIGIN=http://127.0.0.1:PORT REVIEW_LIVE_TOKEN_FILE=/private/token
 node tests/browser_live.cjs
 Optional: REVIEW_LIVE_OUTPUT, REVIEW_LIVE_REVIEWER, REVIEW_LIVE_SUBMIT=1.
 No backend launch, no user browser/profile, no runtime/assets modifications.
 */
const {chromium}=require('/Users/jiyi/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const origin=process.env.REVIEW_LIVE_ORIGIN;
assert(origin && ['127.0.0.1','localhost','[::1]'].includes(new URL(origin).hostname),'Explicit loopback REVIEW_LIVE_ORIGIN required');
const token=process.env.REVIEW_LIVE_TOKEN_FILE?fs.readFileSync(process.env.REVIEW_LIVE_TOKEN_FILE,'utf8').trim():process.env.REVIEW_LIVE_TOKEN;
assert(token,'Provide token via private file or environment; never CLI arguments');
const out=path.resolve(process.env.REVIEW_LIVE_OUTPUT||path.join(__dirname,'../docs/browser-live'));
fs.mkdirSync(out,{recursive:true});
const report={task:'U018',mode_expected:'external',status:'RUNNING',real_video_verified:false,input_verified:false,feedback_submitted:false,limitations:['Input evidence requires decoded media and scene change beyond a stationary baseline; packet counts alone are not proof.','No claim of task acceptance, bug correctness, multiuser capacity or long-run streaming stability.'],checks:[],screenshots:[],page_errors:[],console_errors:[],network_errors:[]};
let browser,page,sessionId;
const delay=ms=>new Promise(r=>setTimeout(r,ms));
async function api(route,body){return page.evaluate(async({route,body})=>{const r=await fetch(route,{method:body===undefined?'GET':'POST',credentials:'same-origin',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw new Error(data.error||'API request failed');return data;},{route,body});}
async function media(frame){return frame.evaluate(async()=>{const v=document.querySelector('video');const stats=[],transport=[];for(const pc of window.__liveQa.pcs){for(const r of (await pc.getStats()).values())if(r.type==='candidate-pair'&&r.state==='succeeded'&&r.nominated){const all=await pc.getStats(),local=all.get(r.localCandidateId),remote=all.get(r.remoteCandidateId);transport.push({localType:local?.candidateType,protocol:local?.protocol,relayProtocol:local?.relayProtocol,remoteType:remote?.candidateType,bytesReceived:r.bytesReceived});}else if(r.type==='inbound-rtp'&&(r.kind==='video'||r.mediaType==='video'))stats.push({id:r.id,framesDecoded:r.framesDecoded||0,framesReceived:r.framesReceived||0,bytesReceived:r.bytesReceived||0,framesPerSecond:r.framesPerSecond,codecId:r.codecId});}return {video:v?{width:v.videoWidth,height:v.videoHeight,readyState:v.readyState,currentTime:v.currentTime,paused:v.paused}:null,stats,transport,sends:window.__liveQa.sends,trustedKeys:window.__liveQa.keys,trustedMouse:window.__liveQa.mouse,pc_configuration_argument_shapes:window.__liveQa.pc_args,peerStates:window.__liveQa.pcs.map(p=>p.connectionState)};});}
async function pixels(frame){return frame.evaluate(()=>{const v=document.querySelector('video');const c=document.createElement('canvas');c.width=160;c.height=90;const ctx=c.getContext('2d',{willReadFrequently:true});ctx.drawImage(v,0,0,160,90);return Array.from(ctx.getImageData(0,0,160,90).data);});}
function diff(a,b){let sum=0,count=0;for(let i=0;i<a.length;i+=4){let d=(Math.abs(a[i]-b[i])+Math.abs(a[i+1]-b[i+1])+Math.abs(a[i+2]-b[i+2]))/3;sum+=d;if(d>20)count++;}return {mean_absolute_rgb:sum/(a.length/4),fraction_pixels_over_20:count/(a.length/4)};}
(async()=>{try{
 browser=await chromium.launch({executablePath:process.env.REVIEW_LIVE_CHROME||'/private/tmp/urban-preview-browser-unpacked/chrome-headless-shell-mac-arm64/chrome-headless-shell',headless:process.env.REVIEW_LIVE_POINTER!=='1',args:['--autoplay-policy=no-user-gesture-required','--no-sandbox']});
 const context=await browser.newContext({viewport:{width:1366,height:900}});
 await context.addInitScript(()=>{window.__liveQa={pcs:[],sends:0,keys:0,mouse:0,pc_args:[]};const Native=window.RTCPeerConnection;if(Native)window.RTCPeerConnection=new Proxy(Native,{construct(target,args){window.__liveQa.pc_args.push(args.map(a=>({type:typeof a,isNull:a===null,keys:a&&typeof a==='object'?Object.keys(a):[]})));const pc=Reflect.construct(target,args);window.__liveQa.pcs.push(pc);return pc;}});if(window.RTCDataChannel){const send=RTCDataChannel.prototype.send;RTCDataChannel.prototype.send=function(...args){window.__liveQa.sends++;return send.apply(this,args);};}});
 page=await context.newPage();page.on('pageerror',e=>report.page_errors.push(e.message));const redact=s=>s.replace(/(https?|wss?):\/\/[^\s\"']+/g,u=>{try{const x=new URL(u);return x.origin+x.pathname;}catch{return '[url]';}});page.on('console',m=>{if(['error','warning'].includes(m.type()))report.console_errors.push(redact(m.text()).slice(0,1000));});page.on('requestfailed',r=>report.network_errors.push({path:new URL(r.url()).pathname,error:r.failure()?.errorText}));page.on('response',r=>{if(r.status()>=400)report.network_errors.push({path:new URL(r.url()).pathname,status:r.status()});});
 const login=await context.request.post(origin+'/api/login',{headers:{Origin:origin},data:{token,reviewer:process.env.REVIEW_LIVE_REVIEWER||'Local Live QA'}});assert(login.ok(),'Dedicated QA login failed');await page.goto(origin+'/?case=U018');await page.bringToFront();await page.locator('#workspace').waitFor({state:'visible'});
 const tasks=await api('/api/tasks');assert.equal(tasks.mode,'external','Refuse mock for real-stream test');const existing=(await api('/api/sessions/current')).session;assert(!existing||['closed','failed'].includes(existing.status),'Use a dedicated QA login with no active live session');
 await page.locator('#task-select').selectOption('U018');await page.locator('#start').click();
 let current;for(let i=0;i<90;i++){current=(await api('/api/sessions/current')).session;if(current){sessionId=current.id;assert.equal(current.task_id,'U018');if(current.status==='failed')throw new Error(current.error||'Runner failed');if(current.status==='ready'&&current.stream_url)break;}await delay(1000);}
 assert(current?.status==='ready'&&current.stream_url,'No ready real stream URL');report.session={id:sessionId,task_id:current.task_id,revision:current.revision,status:current.status};
 await page.locator('#player iframe').waitFor({state:'visible',timeout:20000});const frame=await (await page.locator('#player iframe').elementHandle()).contentFrame();assert(frame,'Missing stream frame');report.frame_path=new URL(frame.url()).pathname;
 // Official PS frontend may require an explicit connect/play overlay click.
 for(let i=0;i<60;i++){const video=frame.locator('video');if(await video.count()){const s=await media(frame);if(s.video?.width>0&&s.stats.some(r=>r.framesDecoded>0))break;}
 for(const name of [/^click to start$/i,/^click to play$/i,/^connect$/i,/^start session$/i]){const button=frame.getByText(name,{exact:true}).first();if(await button.isVisible().catch(()=>false)){await button.click({timeout:1000}).catch(()=>{});break;}}
 await delay(1000);}
 report.frame_text=(await frame.locator('body').innerText()).slice(0,1800);const first=await media(frame);await delay(2500);const second=await media(frame);report.media_start=first;report.media_after=second;
 assert(second.video?.width>0&&second.video.readyState>=2,'Video element has no media frames');assert(second.stats.some(r=>r.framesDecoded>(first.stats.find(x=>x.id===r.id)?.framesDecoded||0)),'Inbound WebRTC framesDecoded must increase');report.real_video_verified=true;if(process.env.REVIEW_LIVE_REQUIRE_TURN==='1')assert(second.transport.some(t=>t.localType==='relay'&&t.relayProtocol==='tcp'),'Expected TURN over TCP through SSH');
 if(process.env.REVIEW_LIVE_SOAK_SECONDS){report.soak=[];const until=Date.now()+Number(process.env.REVIEW_LIVE_SOAK_SECONDS)*1000;while(Date.now()<until){await delay(5000);const s=(await api('/api/sessions/current')).session;assert.equal(s?.status,'ready','Runtime lost during soak: '+s?.error);const sample=await media(frame);assert(sample.peerStates.includes('connected'),'Media disconnected during soak');report.soak.push({time:new Date().toISOString(),media:sample});}assert(report.soak.at(-1).media.stats[0].framesDecoded>report.soak[0].media.stats[0].framesDecoded,'Video stopped during soak');}
 if(process.env.REVIEW_LIVE_IME==='1'){
  await page.bringToFront();await frame.locator('video').click();await delay(1000);const a=await pixels(frame);
  await frame.evaluate(()=>document.dispatchEvent(new KeyboardEvent('keydown',{code:'KeyW',key:'Process',keyCode:229,isComposing:true,bubbles:true,cancelable:true})));
  await delay(1600);
  const down=await frame.evaluate(()=>window.reviewHealth.lastKey);
  await frame.evaluate(()=>document.dispatchEvent(new KeyboardEvent('keyup',{code:'KeyW',key:'Process',keyCode:229,isComposing:true,bubbles:true,cancelable:true})));
  await delay(400);const b=await pixels(frame);const up=await frame.evaluate(()=>window.reviewHealth.lastKey);
  report.ime={synthetic_composition_event:true,down,up,change:diff(a,b)};assert.equal(down?.keyCode,87);assert.equal(down?.type,'down');assert.equal(up?.type,'up');assert(report.ime.change.mean_absolute_rgb>4,'IME-normalized W did not visibly move game');
  const current=(await api('/api/sessions/current')).session;assert.equal(current.health.game_running,true);assert.equal(current.health.streamer_registered,true);report.backend_health=current.health;
 }
 await frame.evaluate(()=>{document.addEventListener('keydown',e=>{if(e.isTrusted)window.__liveQa.keys++;},true);document.addEventListener('mousemove',e=>{if(e.isTrusted)window.__liveQa.mouse++;},true);});
 const video=frame.locator('video').first();await page.bringToFront();await frame.evaluate(()=>{window.__lockEvents=[];document.addEventListener('pointerlockchange',()=>window.__lockEvents.push({locked:!!document.pointerLockElement,t:Date.now()}));const e=document.querySelector('video').parentElement;const request=e.requestPointerLock.bind(e);e.requestPointerLock=()=>{const p=request();p?.catch(x=>window.__lockError=x.message);return p;};});await video.click();if(process.env.REVIEW_LIVE_POINTER==='1'){await frame.waitForFunction(()=>!!document.pointerLockElement);report.pointer_locked=true;await page.mouse.down();await page.mouse.up();await delay(500);assert(await frame.evaluate(()=>!!document.pointerLockElement),'Game click stole browser pointer lock');report.click_kept_browser_lock=true;}report.focus_before={parent:await page.evaluate(()=>({tag:document.activeElement?.tagName,hasFocus:document.hasFocus()})),frame:await frame.evaluate(()=>({tag:document.activeElement?.tagName,hasFocus:document.hasFocus()}))};report.focus_after={parent:await page.evaluate(()=>({tag:document.activeElement?.tagName,hasFocus:document.hasFocus()})),frame:await frame.evaluate(()=>({tag:document.activeElement?.tagName,hasFocus:document.hasFocus()}))};await delay(3500);const still1=await pixels(frame);await delay(1000);const still2=await pixels(frame);const baseline=diff(still1,still2);const beforeInput=await media(frame);
 await video.screenshot({path:path.join(out,'game-before.png')});report.screenshots.push('game-before.png');
 await page.keyboard.down('d');await delay(900);await page.keyboard.up('d');await delay(800);const afterKey=await pixels(frame);const keyChange=diff(still2,afterKey);const keyStats=await media(frame);
 await video.screenshot({path:path.join(out,'game-after-key.png')});report.screenshots.push('game-after-key.png');
 const bounds=await video.boundingBox();assert(bounds);await page.mouse.move(bounds.x+bounds.width*.5,bounds.y+bounds.height*.5);if(process.env.REVIEW_LIVE_POINTER!=='1')await page.mouse.down();await page.mouse.move(bounds.x+bounds.width*.65,bounds.y+bounds.height*.52,{steps:16});if(process.env.REVIEW_LIVE_POINTER!=='1')await page.mouse.up();await delay(800);const afterMouse=await pixels(frame);const mouseChange=diff(afterKey,afterMouse);const mouseStats=await media(frame);
 await video.screenshot({path:path.join(out,'game-after-mouse.png')});report.screenshots.push('game-after-mouse.png');
 report.input={baseline,keyChange,mouseChange,beforeInput,keyStats,mouseStats};
 assert(keyStats.trustedKeys>beforeInput.trustedKeys&&keyStats.sends>beforeInput.sends,'Trusted keyboard input did not reach PS datachannel');assert(mouseStats.trustedMouse>keyStats.trustedMouse&&mouseStats.sends>keyStats.sends,'Trusted mouse input did not reach PS datachannel');
 assert(keyChange.mean_absolute_rgb>Math.max(4,baseline.mean_absolute_rgb*3)&&keyChange.fraction_pixels_over_20>.04,'Keyboard movement not visually distinct from baseline animation');assert(mouseChange.mean_absolute_rgb>Math.max(4,baseline.mean_absolute_rgb*3)&&mouseChange.fraction_pixels_over_20>.04,'Mouse look not visually distinct from baseline animation');report.input_verified=true;
 await frame.evaluate(()=>document.exitPointerLock?.());await page.locator('#difficulty').selectOption('3');await page.locator('#quality').selectOption('uncertain');await page.locator('[name=comment]').fill('本机真实媒体链路技术验证：解码帧增长与键鼠画面响应；此记录不代表 Case 质量验收。');await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(out,'live-review-desktop.png'),fullPage:false});report.screenshots.push('live-review-desktop.png');
 report.parallel_controls=await page.evaluate(()=>Object.fromEntries(['#player','#difficulty','#quality','[name=comment]','button[value=finish]'].map(s=>{const r=document.querySelector(s).getBoundingClientRect();return [s,r.top>=0&&r.bottom<=innerHeight&&r.left>=0&&r.right<=innerWidth];})));assert(Object.values(report.parallel_controls).every(Boolean),'Game and review controls are not co-visible');
 if(process.env.REVIEW_LIVE_SUBMIT==='1'){await page.locator('button[value=finish]').click();await page.waitForFunction(()=>document.querySelector('#notice').textContent.includes('已保存'),{},{timeout:40000});report.feedback_submitted=true;}else report.checks.push('Rating fields filled but not submitted; use explicit REVIEW_LIVE_SUBMIT=1 for QA feedback');
 if(process.env.REVIEW_LIVE_RECOVERY==='1'){
  const previous=sessionId;
  await page.locator('#reset').click();
  for(let i=0;i<90;i++){await delay(1000);const c=(await api('/api/sessions/current')).session;if(c.status==='ready'&&i>3)break;assert(!['closed','failed'].includes(c.status),'Reset unexpectedly closed');}
  assert.equal((await api('/api/sessions/current')).session.status,'ready');
  await page.locator('#close').click();await page.waitForFunction(()=>document.querySelector('#session-status').textContent==='已结束',{},{timeout:30000});
  await page.locator('#restart').click();
  for(let i=0;i<90;i++){await delay(1000);const c=(await api('/api/sessions/current')).session;sessionId=c.id;if(c.status==='ready'&&c.id!==previous)break;}
  assert.notEqual(sessionId,previous);assert.equal((await api('/api/sessions/current')).session.status,'ready');
  await page.waitForFunction(()=>document.querySelector('#health-video').textContent==='视频：实时传输',{},{timeout:30000});
  assert.equal(await page.locator('#difficulty').inputValue(),'3');report.recovery={reset_ready:true,closed_restart_ready:true,video_resumed:true,draft_preserved:true};
 }
 if(process.env.REVIEW_LIVE_DISCONNECT==='1'){
  await page.evaluate(()=>{window.onbeforeunload=null;});
  page.on('dialog',d=>d.accept());await page.close();
  const started=Date.now();let latest;
  for(let i=0;i<25;i++){await delay(1000);latest=(await (await context.request.get(origin+'/api/sessions/current')).json()).session;if(latest.status==='closed')break;}
  assert.equal(latest.status,'closed','Backend game survived browser disconnect');assert.equal(latest.error,'Browser disconnected');assert.equal(latest.health.game_running,false);
  report.disconnect={closed:true,elapsed_ms:Date.now()-started,error:latest.error,health:latest.health};report.session_closed=true;sessionId=null;page=null;
 }
 report.status='PASS';
 }catch(e){report.status='FAIL';report.failure=e.message;if(page){report.pointer_errors=await Promise.all(page.frames().map(f=>f.evaluate(()=>({error:window.__lockError,events:window.__lockEvents,controller:window.pixelStreaming?._webRtcController?.mouseController?.constructor.name,focused:document.hasFocus(),locked:!!document.pointerLockElement})).catch(()=>null)));}if(page)await page.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});process.exitCode=1;
 }finally{if(page&&sessionId){try{await api(`/api/sessions/${sessionId}/close`,{});for(let i=0;i<30;i++){const s=(await api('/api/sessions/current')).session;if(!s||['closed','failed'].includes(s.status)){report.session_closed=true;break;}await delay(1000);}}catch(e){report.cleanup_error=e.message;}}if(browser)await browser.close();report.browser_closed=true;fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));}
})();
