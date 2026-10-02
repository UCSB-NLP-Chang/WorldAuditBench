from pathlib import Path
import subprocess,json,time,uuid,os
r=Path('/home/ubuntu/unreal-auditor/indoor-workspace');out=Path(os.getenv('INDOOR_TEST_OUTPUT',str(r/'out/h10-start/restoration')));out.mkdir(parents=True,exist_ok=True)
binary=Path(os.getenv('INDOOR_TEST_BINARY',str(r/'dist/indoor-h10-start-20260913-v2/Linux/AtmosphericResidentialHou/Binaries/Linux/AtmosphericResidentialHou')))
tasks=json.loads((r/'dist/indoor-h10-start-20260913-v2/tasks.json').read_text())['tasks']
regions={t['id']:t['map'] for t in json.loads((r/'environments/residential-house/regions.json').read_text())['regions']}
for t in tasks:t['map']=regions[t['region']]
def request(**fields):
 id=uuid.uuid4().hex
 tmp=out/'command.tmp';tmp.write_text(json.dumps(dict(request_id=id,**fields)));tmp.replace(out/'command.json')
 start=time.time()
 while time.time()-start<65:
  try:
   data=json.loads((out/'response.json').read_text())
   if data['request_id']==id and data['status']!='switching':
    assert data['status']=='ready',data
    return data
  except (FileNotFoundError,json.JSONDecodeError):pass
  time.sleep(.1)
 raise RuntimeError('IPC acknowledgement timeout '+str(fields))
with (out/'game.log').open('w') as f:
 p=subprocess.Popen([str(binary),tasks[0]['map'],'-nullrhi','-unattended','-nosound','-AuditorRemoteInput','-AuditorReviewDiagnostics','-ExecCmds=t.MaxFPS 30','-AuditorReviewIPC='+str(out)],stdout=f,stderr=subprocess.STDOUT)
 try:
  initial=request(action='snapshot');golden={};results=[]
  for t in tasks:
   clean=request(action='switch',map=t['map'],task='baseline')
   state=sorted(clean['actors'],key=lambda a:a['tag'])
   if t['map'] not in golden:golden[t['map']]=state
   assert state==golden[t['map']],('dirty before',t['id'])
   bug=request(action='switch',map=t['map'],task=t['id'])
   restored=request(action='switch',map=t['map'],task='baseline')
   assert restored['pid']==bug['pid']==initial['pid']==p.pid
   assert bug['task']==t['id'] and restored['task']=='baseline'
   if t['id']=='H10':
    assert sum((a-b)**2 for a,b in zip(bug['position'][:2],t['probe'][:2]))<1,bug['position']
    plant=next(a for a in bug['actors'] if a['tag']=='auditor_actor:StaticMeshActor_927')
    assert not plant['hidden'] and plant['collision']
   assert sorted(restored['actors'],key=lambda a:a['tag'])==golden[t['map']],('dirty after',t['id'])
   assert sum((a-b)**2 for a,b in zip(restored['position'],clean['position']))<1
   result=dict(id=t['id'],ok=True,pid=p.pid,generation=restored['generation']);results.append(result);print(json.dumps(result),flush=True)
  (out/'report.json').write_text(json.dumps(results,indent=2))
 finally:
  p.terminate()
  try:p.wait(15)
  except subprocess.TimeoutExpired:p.kill();p.wait()

