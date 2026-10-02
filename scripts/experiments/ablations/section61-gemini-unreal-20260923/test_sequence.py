import importlib.util,tempfile,json,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('sequence',Path(__file__).with_name('sequence.py'));s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
with tempfile.TemporaryDirectory() as tmp:
 b=Path(tmp);s.B=b;s.CURRENT=None;s.validate_admission=lambda:None
 for p in s.PHASES:(b/p).mkdir()
 (b/'replay.pid').write_text('2147483647')
 (b/s.PHASES[0]/'verified-resume-admission.consumed').write_text('test')
 (b/s.PHASES[0]/'finished.json').write_text(json.dumps({'time':time.time()+1,'stopped':False}))
 events=[]
 def run(phase,stage,args):
  events.append((phase,stage))
  if stage=='record':(b/phase/'recordings.finished.json').write_text(json.dumps({'verified':126}))
  if stage=='replay-preflight':(b/phase/'replay-preflight.json').write_text(json.dumps({'passed':True}))
  if stage=='finalize':(b/phase/'verified.finished.json').write_text('{}')
 s.run=run;s.subprocess.check_output=lambda *a,**k:''
 s.main()
 assert events==[(s.PHASES[0],'finalize')]+[(p,stage) for p in s.PHASES[1:] for stage in (['native-audit','finalize'] if p==s.PHASES[2] else ['record','replay-preflight','replay','finalize'])]
 assert (b/'all-experiments.finished.json').exists()
 try:s.main()
 except FileExistsError:pass
 else:raise AssertionError('duplicate sequence admission not blocked')
 (b/'STOP.json').write_text('{}');assert all(s.stopping(p) for p in s.PHASES)
 print('PASS phase ordering, prerequisites, single-use admission, shared STOP; zero model calls')
