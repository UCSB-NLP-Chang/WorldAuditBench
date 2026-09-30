from pathlib import Path
import json,subprocess,sys,os
w=Path('/home/ubuntu/unreal-auditor/configuration-workspace');tasks={'subway':('S18','/Game/Auditor/Subway/Platform'),'indoor':('H13','/Game/Auditor/Regions/KitchenDining'),'ancient':('A18','/Game/Auditor/AncientCity/Courtyard'),'medieval':('MV17','/Game/Auditor/MedievalVillage/Windmill'),'industrial':('I19','/Game/Auditor/Industrial/AssemblyHall')}
for f in sys.argv[1:]:
 build=json.loads((w/'out'/('build-'+f+'.json')).read_text());tid,map=tasks[f];out=w/'out'/('tests-'+f);out.mkdir(exist_ok=True);results=[]
 for control in [False,True]:
  name='clean' if control else 'bug';log=out/(name+'.log');args=[build['binary'],map+'?Task='+tid,'-nullrhi','-nosound','-unattended','-AuditorRemoteInput','-AuditorTaskTest','-AuditorTestExit','-ExecCmds=t.MaxFPS 30']+(['-AuditorControl'] if control else [])
  with log.open('w') as stream:
   try:code=subprocess.run(args,stdout=stream,stderr=subprocess.STDOUT,timeout=60).returncode
   except subprocess.TimeoutExpired:code=-1
  text=log.read_text(errors='replace');markers=[l for l in text.splitlines() if 'AUDITOR_TASK_TEST' in l or 'RESIDENTIAL_TASK_TEST' in l];ok=code==0 and any(' PASS ' in l for l in markers);result={'case':tid,'control':control,'ok':ok,'code':code,'markers':markers};results.append(result);print(json.dumps(result),flush=True)
 (out/'report.json').write_text(json.dumps(results,indent=2));assert all(x['ok'] for x in results)
