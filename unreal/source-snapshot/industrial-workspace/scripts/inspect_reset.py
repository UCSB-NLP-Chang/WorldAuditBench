import review_industrial_build as q
import subprocess,json
p=subprocess.Popen([str(q.BINARY),q.TASKS[0]['map'],'-nullrhi','-nosound','-unattended','-AuditorReviewDiagnostics','-AuditorReviewIPC='+str(q.OUT),'-ExecCmds=t.MaxFPS 30'],stdout=(q.OUT/'reset-probe.log').open('w'),stderr=subprocess.STDOUT)
try:
 q.request(action='snapshot');a=q.request(action='switch',map=q.TASKS[0]['map'],task='baseline');b=q.request(action='switch',map=q.TASKS[0]['map'],task='I01');c=q.request(action='switch',map=q.TASKS[0]['map'],task='baseline')
 aa={x['tag']:x for x in q.stable_state(a)};cc={x['tag']:x for x in q.stable_state(c)};diff=[(k,aa.get(k),cc.get(k)) for k in set(aa)|set(cc) if aa.get(k)!=cc.get(k)]
 (q.OUT/'reset-diff.json').write_text(json.dumps(diff,indent=2));print(json.dumps(dict(count=len(diff),sample=diff[:4]),indent=2))
finally:p.terminate();p.wait(20)
