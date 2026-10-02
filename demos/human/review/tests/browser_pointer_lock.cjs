const {chromium}=require('/Users/jiyi/node_modules/playwright');
const fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{let browser;try{
 browser=await chromium.launch({executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless:false,args:['--no-sandbox']});
 const context=await browser.newContext();const page=await context.newPage();const base='http://127.0.0.1:8091';
 const token=fs.readFileSync(__dirname+'/../var/mac-real/user-token','utf8').trim();
 const login=await context.request.post(base+'/api/login',{headers:{Origin:base},data:{token,reviewer:'本机评审'}});assert(login.ok());
 const current=(await (await context.request.get(base+'/api/sessions/current')).json()).session;assert.equal(current.status,'ready');
 // Use the actual served official player with AutoConnect disabled: no new subscription or game restart.
 const url=new URL(current.stream_url,base);url.searchParams.set('AutoConnect','false');url.searchParams.set('HoveringMouse','true');
 await page.goto(url.href);await page.waitForFunction(()=>window.pixelStreaming?.config.isFlagEnabled('HoveringMouse')===false);
 assert.equal(await page.evaluate(()=>window.pixelStreaming.config.isFlagEnabled('AutoConnect')),false);
 const video=page.locator('video');assert.equal(await video.count(),1);
 // The connect overlay deliberately stays up without a subscription. Hide only that overlay for pointer-lock testing.
 await page.evaluate(()=>{const v=document.querySelector('video');for(const e of document.querySelectorAll('body *')){if(e!==v&&!e.contains(v)&&e.getBoundingClientRect().width>300&&e.getBoundingClientRect().height>100&&getComputedStyle(e).position==='absolute')e.style.pointerEvents='none';}});
 await page.evaluate(()=>{const e=document.querySelector('video').parentElement;const request=e.requestPointerLock.bind(e);e.requestPointerLock=()=>{const p=request();p?.catch(x=>window.lockError=x.message);return p;};});await page.bringToFront();const box=await video.boundingBox();await page.mouse.click(box.x+box.width/2,box.y+box.height/2);
 await page.waitForFunction(()=>!!document.pointerLockElement,{},{timeout:5000});
 const locked=await page.evaluate(()=>({locked:!!document.pointerLockElement,hovering:window.pixelStreaming.config.isFlagEnabled('HoveringMouse')}));
 await page.keyboard.press('Escape');await page.waitForFunction(()=>!document.pointerLockElement);
 const report={status:'PASS',...locked,released:true,escape_verified:true,autoConnect:false,game_restarted:false,limits:'Checks actual official locked mouse controller and browser lock/release, without subscribing to user video. Real video/camera movement is not exercised in this no-subscription check.'};
 fs.writeFileSync(__dirname+'/../docs/pointer-lock-check.json',JSON.stringify(report,null,2));console.log(report);
 }finally{if(browser)await browser.close();}})().catch(e=>{console.error(e.message);process.exitCode=1});
