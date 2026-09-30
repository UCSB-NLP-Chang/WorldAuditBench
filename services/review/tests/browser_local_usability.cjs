const {chromium}=require('/Users/jiyi/node_modules/playwright');const fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{const b=await chromium.launch({executablePath:'/private/tmp/urban-preview-browser-unpacked/chrome-headless-shell-mac-arm64/chrome-headless-shell',headless:true,args:['--no-sandbox']});try{
const p=await b.newPage();p.on('dialog',d=>d.accept());let s=null,logged=false;const tasks=JSON.parse(fs.readFileSync(__dirname+'/../tasks.json')).tasks;
await p.route('**/api/**',async route=>{const path=new URL(route.request().url()).pathname;let status=200,data;
if(path==='/api/me'){status=logged?200:401;data=logged?{reviewer:'QA Form',mode:'mock',local:true}:{error:'Login required'};}
else if(path==='/api/local-login'){logged=true;data={reviewer:'QA Form',local:true};}
else if(path==='/api/tasks')data={tasks,mode:'mock'};
else if(path==='/api/sessions/current')data={session:s};
else if(path.endsWith('/heartbeat'))data={session:s};
else throw Error('Unexpected request '+path);
await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});});
await p.goto('http://127.0.0.1:8091/?case=U018');await p.locator('#workspace').waitFor({state:'visible'});assert(await p.locator('#login-panel').isHidden());assert(await p.locator('#logout').isHidden());
await p.locator('#difficulty').selectOption('2');await p.locator('#quality').selectOption('pass');await p.locator('[name=comment]').fill('Unsubmitted local draft');assert(await p.locator('button[value=finish]').isDisabled());
s={id:'fixture-session',task_id:'U018',revision:2,status:'starting',mode:'mock'};await p.waitForFunction(()=>document.querySelector('#session-status').textContent==='正在启动');assert(await p.locator('#difficulty').isEnabled());assert.equal(await p.locator('[name=comment]').inputValue(),'Unsubmitted local draft');
for(const [status,label] of [['resetting','正在重置'],['closing','正在结束'],['closed','已结束']]){s.status=status;await p.waitForFunction(label=>document.querySelector('#session-status').textContent===label,label);assert(await p.locator('#quality').isEnabled());}
assert(await p.locator('button[value=finish]').isEnabled());await p.reload();await p.locator('#workspace').waitFor({state:'visible'});assert.equal(await p.locator('[name=comment]').inputValue(),'Unsubmitted local draft');
await p.locator('#task-select').selectOption('U011');assert.equal(await p.locator('[name=comment]').inputValue(),'');assert(await p.locator('button[value=finish]').isDisabled());await p.locator('#task-select').selectOption('U018');assert.equal(await p.locator('[name=comment]').inputValue(),'Unsubmitted local draft');
console.log('PASS: automatic local login; drafts editable before/during/after game; refresh and case isolation; no cross-case submission');
}finally{await b.close();}})().catch(e=>{console.error(e.message);process.exitCode=1});
