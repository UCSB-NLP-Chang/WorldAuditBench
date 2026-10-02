const {chromium}=require('/Users/ziyan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),assert=require('assert/strict'),path=require('path');
const base=process.env.MEDIEVAL_QA_URL||'http://127.0.0.1:19519';
const out=process.env.MEDIEVAL_QA_OUTPUT||'/Users/ziyan/3d-world-auditor/out/medieval-a10/props-v2/browser';fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const context=await browser.newContext({viewport:{width:1440,height:1050}});const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 try {
  if(process.env.MEDIEVAL_QA_COOKIE){const auth=JSON.parse(fs.readFileSync(process.env.MEDIEVAL_QA_COOKIE));await context.addCookies([{name:'linux_review_session',value:auth.cookie,url:base,secure:true}]);}
  else {const login=await context.request.post(base+'/api/login',{headers:{Origin:base},data:{token:'local-demo',reviewer:'Independent type order QA'}});assert.equal(login.status(),200);}
  await page.goto(base);await page.waitForFunction(()=>dashboardData&&!state.busy);
  const tasks=await page.evaluate(()=>state.tasks.map(t=>({id:t.id,family:t.family,code:t.taxonomy?.code,type:t.case_type})));
  const families=[...new Set(tasks.map(t=>t.family))];const codes=['G1','G2','G3','C1','C2','C3','V1','V2','V3','T1','T2','T3','S1','S2','S3'];
  const rank=t=>t.type==='baseline'?-1:t.code?codes.indexOf(t.code):15;
  await page.locator('#nav-review').click();
  for(const family of families){
   await page.locator('#environment-select').selectOption(family);
   const rows=tasks.filter(t=>t.family===family),expected=[...rows].sort((a,b)=>rank(a)-rank(b)||Number(a.id.match(/\d+$/)?.[0]||0)-Number(b.id.match(/\d+$/)?.[0]||0)||a.id.localeCompare(b.id));
   const options=await page.locator('#task-select option').evaluateAll(nodes=>nodes.map(n=>n.value));
   assert.deepEqual(options,expected.map(t=>t.id),family);
   if(options.length>2){await page.locator('#task-select').selectOption(options[1]);await page.locator('#next-task').click();await page.waitForFunction(()=>!state.busy);assert.equal(await page.locator('#task-select').inputValue(),options[2]);await page.locator('#prev-task').click();await page.waitForFunction(()=>!state.busy);assert.equal(await page.locator('#task-select').inputValue(),options[1]);}
  }
  await page.locator('#nav-progress').click();await page.locator('#progress-filter').selectOption('review');
  const visible=await page.locator('#progress-rows tr td:first-child').allTextContents();
  const dashboard=await page.evaluate(()=>dashboardData.tasks.filter(t=>!t.accepted).map(displayTaskId));assert.deepEqual(visible,dashboard);
  await page.locator('#nav-review').click();await page.locator('#environment-select').selectOption('medieval');
  const ours=tasks.filter(t=>t.family==='medieval'),descriptions={};
  if(ours.some(t=>t.id==='MV19')){const credits=await context.request.get(base+'/medieval-prop-attributions.md');assert.equal(credits.status(),200);assert((await credits.text()).includes('CC BY'));assert.equal(await page.locator('a[href="/medieval-prop-attributions.md"]').count(),1);}
  for(const t of ours){
   await page.locator('#task-select').selectOption(t.id);assert.equal(await page.locator('#rubric-box').isVisible(),t.type==='bug');
   for(const lang of ['zh','en']){await page.locator('#rubric-'+lang).click();const scene=await page.locator('#case-scene').innerText();assert(scene.length>40);
    const map=await page.evaluate(id=>sceneDescriptions.find(s=>s.task_ids.includes(id)).map,t.id);const k=map+lang;if(descriptions[k])assert.equal(scene,descriptions[k]);else descriptions[k]=scene;
    if(t.type==='bug')assert((await page.locator('#case-rubrics').innerText()).length>25);
   }
  }
  await page.locator('#task-select').selectOption(ours.some(t=>t.id==='MV19')?'MV19':'MV18');await page.screenshot({path:path.join(out,'review.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));assert.deepEqual(errors,[]);
  const report={result:'PASS',families:families.length,entries:tasks.length,medieval_entries:ours.length,dropdown_order:true,previous_next_order:true,progress_order:true,bilingual:true,mobile:true,feedback_submitted:false};
  fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
