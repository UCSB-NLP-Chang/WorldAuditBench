const fs = require('fs'), vm = require('vm'), assert = require('assert/strict'), path = require('path');
const stage = process.argv[2];
const app = fs.readFileSync(path.join(stage,'static/app.js'),'utf8');
const taxonomy = app.match(/^const taxonomyDefinition=.*$/m)[0];
const canonical = app.match(/^function canonicalTaxonomy\(task\).*$/m)[0];
const ordering = app.match(/^function orderedTasks\(tasks\)[\s\S]*?^\}/m)[0];
const manifest = JSON.parse(fs.readFileSync(path.join(stage,'tasks.json'))).tasks;
const run = input => JSON.parse(JSON.stringify(vm.runInNewContext(taxonomy+'\n'+canonical+'\n'+ordering+'\norderedTasks(input)',{input})));
const original = JSON.stringify(manifest), sorted = run(manifest);
assert.equal(JSON.stringify(manifest), original);
assert.deepEqual(sorted.map(t=>t.id).sort(),manifest.map(t=>t.id).sort());
const codes = ['G1','G2','G3','C1','C2','C3','V1','V2','V3','T1','T2','T3','S1','S2','S3'];
const definition=vm.runInNewContext(taxonomy+'\ntaxonomyDefinition');
const lookup=Object.fromEntries(definition.categories.flatMap(c=>c.subcategories.flatMap(s=>[[s.id,s.code],[s.code,s.code]])));
const rank=t=>t.case_type==='baseline'?-1:codes.indexOf(lookup[definition.task_overrides?.[t.id]||t.subcategory||t.taxonomy?.code]);
const seen = new Set();let current;
for(const task of sorted){if(task.family!==current){assert(!seen.has(task.family));seen.add(task.family);current=task.family;}}
for(const family of seen){
 const rows=sorted.filter(t=>t.family===family);
 const ranks=rows.map(t=>{const r=rank(t);return r<0&&t.case_type!=='baseline'?15:r;});
 assert.deepEqual(ranks,[...ranks].sort((a,b)=>a-b),family);
}
const sample = [
 {id:'MV20',family:'medieval',subcategory:'S3'},
 {id:'MV02',family:'medieval',subcategory:'G2'},
 {id:'MV11',family:'medieval',subcategory:'G1'},
 {id:'MV01',family:'medieval',subcategory:'G1'},
 {id:'MVB02',family:'medieval',case_type:'baseline'},
 {id:'MVB01',family:'medieval',case_type:'baseline'},
];
assert.deepEqual(run(sample).map(t=>t.id),['MVB01','MVB02','MV01','MV11','MV02','MV20']);
console.log(JSON.stringify({result:'PASS',families:seen.size,entries:sorted.length,stable_ids:true,input_unchanged:true}));
