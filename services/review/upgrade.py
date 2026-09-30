import pathlib
r=pathlib.Path(__file__).resolve().parent
p=r/'server.py';s=p.read_text()
s=s.replace("return {'environment':", "return ({'rubrics_i18n':t['rubrics_i18n']} if 'rubrics_i18n' in t else {}) | {'environment':",1)
s=s.replace("r'U\\d{3}',t['id']", "r'(?:U\\d{3}|S(?:0[1-9]|1[0-9])|H(?:0[1-9]|1[0-3])|B0[1-3]|HB0[1-3])',t['id']")
s=s.replace("            if t['map'] not in (canonical,migration):raise ValueError('Invalid map')",'''            allowed=(canonical,migration) if t['id'].startswith('U') else ()
            subway={'B01':'Concourse','B02':'Platform','B03':'Trackside'}
            indoor={'HB01':'LivingRoom','HB02':'KitchenDining','HB03':'BedroomSuite'}
            if t['id'] in subway:allowed=('/Game/Auditor/Subway/'+subway[t['id']],)
            elif t['id'] in indoor:allowed=('/Game/Auditor/Regions/'+indoor[t['id']],)
            elif t['id'].startswith('S'):allowed=tuple('/Game/Auditor/Subway/'+region+'?Task='+t['id'] for region in ('Concourse','Platform','Trackside'))
            elif t['id'].startswith('H'):allowed=tuple('/Game/Auditor/Regions/'+region+'?Task='+t['id'] for region in ('LivingRoom','KitchenDining','BedroomSuite'))
            if t['map'] not in allowed:raise ValueError('Invalid map')
            if 'build_sha256' in t and not re.fullmatch(r'[0-9a-f]{64}',t['build_sha256']):raise ValueError('Invalid task build hash')
            if 'rubrics_i18n' in t and any(not isinstance(t['rubrics_i18n'].get(lang,{}).get(key),str) or not t['rubrics_i18n'][lang][key].strip() for lang in ('zh','en') for key in ('expected','steps','criteria')):raise ValueError('Incomplete bilingual rubrics')''')
s=s.replace("t['sha256'],self.build_sha,self.mode", "t['sha256'],t.get('build_sha256',self.build_sha),self.mode")
p.write_text(s)
p=r/'manage.py';s=p.read_text().replace("    groups.setdefault(current, [])", "    task_groups=collections.defaultdict(list)\n    for task in data.get('tasks',[]):\n        group=(current[0],str(task.get('build_sha256',current[1])))\n        task_groups[group].append(task);groups.setdefault(group,[])\n    if not task_groups:groups.setdefault(current, [])")
s=s.replace("        if group == current:\n            rows.update({case_snapshot(task): {} for task in data.get('tasks', [])})", "        rows.update({case_snapshot(task): {} for task in task_groups.get(group,[])})")
p.write_text(s)
p=r/'runtime/mac_supervisor.py';s=p.read_text()
s=s.replace("  self.root=pathlib.Path", "  self.profiles=config.get('launch_profiles',{})\n  if self.profiles and set(self.profiles)!=self.allowed:raise ValueError('Launch profiles must exactly match manifest maps')\n  self.verified={}\n  self.root=pathlib.Path",1)
s=s.replace("     argv=[self.c['binary'],map_", "     profile=self.profiles.get(map_,self.c)\n     binary=profile['binary']\n     if self.profiles:\n      expected=profile['build_sha256'];stat=pathlib.Path(binary).stat();key=(binary,stat.st_size,stat.st_mtime_ns)\n      if key not in self.verified:\n       digest=hashlib.file_digest(open(binary,'rb'),'sha256').hexdigest() if hasattr(hashlib,'file_digest') else self.hash_binary(binary)\n       self.verified[key]=digest\n      if self.verified[key]!=expected:raise RuntimeError('Runtime binary does not match task build hash')\n     argv=[binary,map_")
s=s.replace("'-PixelStreamingKeyFilter=M,One,Two,Three,Four,Tilde'", "'-PixelStreamingKeyFilter='+profile.get('key_filter','M,One,Two,Three,Four,Tilde')")
s=s.replace("argv+=self.c.get('game_args',[])", "argv+=self.c.get('game_args',[])+profile.get('extra_args',[])")
s=s.replace("str(pathlib.Path(self.c['binary']).parent)","str(pathlib.Path(binary).parent)")
s=s.replace(" def record(self,s,event,**details):", " def hash_binary(self,binary):\n  digest=hashlib.sha256()\n  with open(binary,'rb') as f:\n   for block in iter(lambda:f.read(8*1024*1024),b''):digest.update(block)\n  return digest.hexdigest()\n def record(self,s,event,**details):")
p.write_text(s)
p=r/'static/app.js';s=p.read_text()
s=s.replace("$('task-select').disabled=blocked;", "$('task-select').disabled=blocked;$('environment-select').disabled=blocked;")
s=s.replace("['rubrics','case-rubrics'],",'')
needle=" for(const key of ['difficulty','quality','comment'])"
s=s.replace(needle,""" const box=$('case-rubrics');box.replaceChildren();
 if(task?.rubrics_i18n){for(const [lang,label] of [['zh','中文'],['en','English']]){const section=document.createElement('section');section.lang=lang;section.className='rubric-language';const heading=document.createElement('h3');heading.textContent=label;section.append(heading);for(const [key,zh,en] of [['expected','正常预期','Expected behavior'],['steps','复现步骤','Review steps'],['criteria','判定标准','Acceptance criteria']]){const p=document.createElement('p'),b=document.createElement('strong');b.textContent=(lang==='zh'?zh:en)+'：';p.append(b,document.createTextNode(task.rubrics_i18n[lang][key]));section.append(p);}box.append(section);}}else box.textContent=task?.rubrics||'—';
 $('case-taxonomy').textContent=task?.taxonomy_label||task?.subcategory||'';
"""+needle)
start=s.index('async function loadTasks()');end=s.index('\nasync function enter',start)
s=s[:start]+'''function taskFamily(task){return task.family||'urban';}
function populateTasks(preferred){const select=$('task-select'),family=$('environment-select').value;select.replaceChildren();const labels={subway:'Subway · 地铁',indoor:'Indoor · 室内',urban:'Urban · 街区'};for(const key of ['subway','indoor','urban']){const tasks=state.tasks.filter(t=>taskFamily(t)===key&&(!family||key===family));if(!tasks.length)continue;const group=document.createElement('optgroup');group.label=labels[key];for(const task of tasks){const option=document.createElement('option');option.value=task.id;option.textContent=task.id+' · '+(task.title||task.environment)+(task.case_type==='baseline'?' / 正常基准':'');group.append(option);}select.append(group);}if([...select.options].some(o=>o.value===preferred))select.value=preferred;}
async function loadTasks(){const data=await api('/api/tasks');state.mode=data.mode;state.tasks=data.tasks;populateTasks(new URLSearchParams(location.search).get('case'));$('case-count').textContent=data.tasks.length+' 项 · 中英双语 Rubrics';renderSession();}
$('environment-select').onchange=()=>{populateTasks($('task-select').value);renderCase();controls();};
'''+s[end:]
s=s.replace("if(session&&session.status!=='closed')$('task-select').value=session.task_id;", "if(session&&session.status!=='closed'){if(![...$('task-select').options].some(o=>o.value===session.task_id)){$('environment-select').value='';populateTasks(session.task_id);}$('task-select').value=session.task_id;}")
p.write_text(s)
p=r/'static/index.html';s=p.read_text().replace('<h1>评审工作台</h1>', '<h1>评审工作台</h1><span id="case-count" class="muted"></span>')
s=s.replace('<label class="sr-only" for="task-select">', '<select id="environment-select" aria-label="环境"><option value="">全部环境</option><option value="subway">Subway · 地铁</option><option value="indoor">Indoor · 室内</option><option value="urban">Urban · 街区</option></select><label class="sr-only" for="task-select">')
s=s.replace('<p id="case-rubrics">—</p>','<div id="case-taxonomy" class="taxonomy-label"></div><div id="case-rubrics">—</div>').replace('· 预期异常','· 中文 / English').replace('鼠标转动视角</span>','鼠标转动视角 · E 交互</span>')
p.write_text(s)
p=r/'static/style.css';p.write_text(p.read_text()+'''\n.rubric-language h3{font-size:12px;margin:12px 0 8px;color:#52634f}.rubric-language p{margin:8px 0;font-size:13px;line-height:1.65}.rubric-language+section{border-top:1px solid #ddd;padding-top:4px}.taxonomy-label{font-size:12px;margin-top:8px;color:#657461}#task-select{max-width:360px}#environment-select{max-width:165px}.assignment .actions{flex-wrap:wrap}.assignment-title #case-count{font-size:12px}.rubric-box{overflow-wrap:anywhere}\n''')
print('Unified coordinator, runtime profiles, bilingual UI and per-build export implemented')
