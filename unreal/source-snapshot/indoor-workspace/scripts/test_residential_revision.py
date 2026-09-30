#!/usr/bin/env python3
"""Verify the residential scenarios against matching clean controls, optionally render both."""
import argparse,json,subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('distribution',type=Path);p.add_argument('--ids',nargs='*');p.add_argument('--render',action='store_true');a=p.parse_args()
dist=a.distribution.resolve();catalog=json.loads((dist/'tasks.json').read_text());regions={x['id']:x['map'] for x in json.loads((dist/'maps.json').read_text())['regions']}
binary=dist/'Linux/AtmosphericResidentialHou.sh'
out=dist/('rendered-review' if a.render else 'behavior-tests');out.mkdir(exist_ok=True);results=[]
for t in catalog['tasks']:
 if a.ids and t['id'] not in a.ids:continue
 for control in [True,False]:
  label=t['id']+('-control' if control else '-bug');log=out/(label+'.log');png=out/(label+'.png');png.unlink(missing_ok=True)
  cmd=[str(binary),regions[t['region']],'-AuditorTask='+t['id'],'-AuditorTestExit','-unattended','-nosound','-ExecCmds=t.MaxFPS 30','-AuditorRemoteInput']
  if control:cmd+=['-AuditorControl']
  if a.render:cmd+=['-AuditorReview','-AuditorCapture='+str(png),'-RenderOffscreen','-vulkan','-sm5','-windowed','-ResX=1280','-ResY=720']
  else:cmd+=['-AuditorTaskTest','-nullrhi']
  with log.open('w') as f:
   try:rc=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,timeout=150).returncode
   except subprocess.TimeoutExpired:rc=-1
  text=log.read_text(errors='replace');passed=rc==0 and ('AUDITOR_TASK_TEST PASS id='+t['id']+' ') in text and (not a.render or png.exists())
  marker=next((line.split('AUDITOR_TASK_TEST ',1)[1] for line in text.splitlines() if 'AUDITOR_TASK_TEST ' in line),'No result')
  row={'id':t['id'],'subcategory':t['subcategory'],'control':control,'result':'PASS' if passed else 'FAIL','detail':marker};results.append(row);print(json.dumps(row),flush=True)
  (out/'results.json').write_text(json.dumps(results,indent=2)+'\n')
if any(x['result']=='FAIL' for x in results):raise SystemExit(1)
