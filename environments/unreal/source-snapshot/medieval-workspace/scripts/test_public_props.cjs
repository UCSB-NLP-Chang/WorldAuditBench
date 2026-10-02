const {chromium}=require('/Users/ziyan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),assert=require('assert/strict'),{execFileSync}=require('child_process');
const base='https://review.150-230-45-149.sslip.io',out='/Users/ziyan/3d-world-auditor/out/medieval-a10/props-v2/public-final',wait=ms=>new Promise(r=>setTimeout(r,ms));
fs.mkdirSync(out,{recursive:true});
const report={feedback_submitted:false,checks:[]};
function runtime(id){return JSON.parse(execFileSync('ssh',['lambda-unreal','python3 /home/ubuntu/unreal-auditor/medieval-workspace/scripts/read_public_runtime.py '+id],{encoding:'utf8'}));}
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',args:['--autoplay-policy=no-user-gesture-required']});let context,page;
 try{
  context=await browser.newContext({viewport:{width:1440,height:1050}});
  const auth=JSON.parse(fs.readFileSync('/Users/ziyan/3d-world-auditor/out/medieval-a10/qa-cookie.json'));
  await context.addCookies([{name:'linux_review_session',value:auth.cookie,url:base,secure:true}]);
  page=await context.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base);await page.waitForFunction(()=>dashboardData&&!state.busy,{},{timeout:60000});
  assert.equal(await page.evaluate(()=>dashboardData.capacity),3);
  assert.equal(await page.evaluate(()=>state.tasks.filter(t=>t.family==='medieval').length),22);
  assert.equal(await page.evaluate(()=>new Set(state.tasks.map(t=>t.family)).size)>=6,true);
  await page.locator('#nav-review').click();await page.locator('#environment-select').selectOption('medieval');
  assert.equal(await page.locator('#task-select option').count(),22);
  const expected=await page.evaluate(()=>state.tasks.filter(t=>t.family==='medieval').map(displayTaskId));
  assert.deepEqual(await page.locator('#task-select option').allTextContents(),expected);
  const credits=await context.request.get(base+'/medieval-prop-attributions.md');assert.equal(credits.status(),200);assert((await credits.text()).includes('CC BY'));
  for(let i=1;i<=20;i++){
   await page.locator('#task-select').selectOption('MV'+String(i).padStart(2,'0'));
   for(const lang of ['en','zh']){await page.locator('#rubric-'+lang).click();const text=await page.locator('#case-rubrics').innerText();assert(text.length>25);assert.equal(await page.locator('#case-rubrics details').count(),0);}
  }
  async function ready(id){await page.waitForFunction(id=>state.session?.task_id===id&&state.session.status==='ready'&&!state.busy,id,{timeout:150000});}
  async function video(){
   await page.locator('#player iframe').waitFor({timeout:120000});const frame=await(await page.locator('#player iframe').elementHandle()).contentFrame();
   for(let i=0;i<90;i++){
    const data=await frame.evaluate(()=>({health:window.reviewHealth,w:document.querySelector('video')?.videoWidth}));
    if(data.w&&data.health?.frames>3&&Date.now()-data.health.lastFrameAt<5000)return frame;
    for(const label of [/^click to start$/i,/^click to play$/i,/^connect$/i]){const button=frame.getByText(label,{exact:true}).first();if(await button.isVisible().catch(()=>false))await button.click({timeout:800}).catch(()=>{});}
    await wait(1000);
   }throw Error('Video did not become live');
  }
  await page.locator('#task-select').selectOption('MVB01');await page.locator('#start').click();await ready('MVB01');
  let frame=await video();const firstId=await page.evaluate(()=>state.session.id),initial=runtime(firstId);await frame.evaluate(()=>window.__medievalCanary=true);
  await frame.locator('video').screenshot({path:path.join(out,'public-before-move.png')});
  await frame.locator('video').click({position:{x:400,y:300}});await page.keyboard.down('s');await wait(900);await page.keyboard.up('s');await wait(700);
  await frame.locator('video').screenshot({path:path.join(out,'public-after-move.png')});
  await page.mouse.move(780,450);await page.mouse.move(930,470,{steps:12});await wait(500);await page.keyboard.press('Escape');
  await page.screenshot({path:path.join(out,'public-assembly.png')});
  for(const id of ['MV18','MVB02','MV19','MVB01','MV20','MVB01']){
   await page.evaluate(id=>{const ids=[...document.querySelector('#task-select').options].map(o=>o.value);return action(()=>navigateTask(ids.indexOf(id)-ids.indexOf(document.querySelector('#task-select').value)));},id);await ready(id);frame=await video();
   const currentId=await page.evaluate(()=>state.session.id);const current=runtime(currentId);
   assert.equal(current.pid,initial.pid);assert(await frame.evaluate(()=>window.__medievalCanary));
   await wait(2500);
   await frame.locator('video').screenshot({path:path.join(out,'video-'+id+'.png')});
   await page.screenshot({path:path.join(out,'public-'+id+'.png')});
   report.checks.push({id,same_pid:current.pid,map:current.map,video:true});
  }
  await page.locator('#close').click();await page.waitForFunction(()=>state.session?.status==='closed'&&!state.busy);
  await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:path.join(out,'public-mobile.png'),fullPage:true});assert.deepEqual(errors,[]);
  report.result='PASS';report.catalog_entries=22;report.bilingual_bug_views=40;
 }catch(error){report.result='FAIL';report.error=error.stack;process.exitCode=1;if(page)await page.screenshot({path:path.join(out,'public-failure.png')}).catch(()=>{});}
 finally{
  if(context){try{const session=(await(await context.request.get(base+'/api/sessions/current')).json()).session;if(session&&!['closed','failed'].includes(session.status))await context.request.post(base+'/api/sessions/'+session.id+'/close',{headers:{Origin:base},data:{}});}catch{}}
  await browser.close();fs.writeFileSync(path.join(out,'public-report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }
})();
