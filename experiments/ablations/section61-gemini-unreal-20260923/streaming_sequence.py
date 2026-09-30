"""Adopt the active recorder; stream verified videos to unchanged Gemini analysis and real judges."""
from pathlib import Path
import json,os,time,signal,hashlib,fcntl,subprocess
import sequence as s
B=Path(__file__).resolve().parent
PHASES=['04-vla-half','05-vla-onehalf']
owned=[];adopted=None;handoff=False

def cmdline(pid):
 try:return (Path('/proc')/str(pid)/'cmdline').read_bytes().replace(b'\0',b' ')
 except FileNotFoundError:return b''

def process_alive(pid):
 try:
  state=(Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()[0]
  return state!='Z'
 except FileNotFoundError:return False

def launch(phase,stage,argv):
 assert not s.stopping(phase)
 log=(B/phase/(stage+'.log')).open('x')
 try:p=subprocess.Popen(argv,cwd=B,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 finally:log.close()
 owned.append(p);return p

def abort():
 for p in owned:
  if p.poll() is None:s.terminate(p)
 if adopted and process_alive(adopted):
  assert str(B/'record_controller.py').encode() in cmdline(adopted)
  os.killpg(adopted,signal.SIGTERM)
  deadline=time.time()+60
  while process_alive(adopted) and time.time()<deadline:time.sleep(1)
  if process_alive(adopted):os.killpg(adopted,signal.SIGKILL)

def main():
 global adopted,handoff
 s.validate_admission()
 a=s.read(B/'streaming-admission.json')
 assert a['approved'] and a['phases']==PHASES
 for n,h in a['files'].items():assert hashlib.sha256((B/n).read_bytes()).hexdigest()==h,n
 assert not s.stopping(PHASES[0]) and not s.stopping(PHASES[1])
 assert s.read(B/'03-vlm-60steps/verified.finished.json')['graded']==124
 old=a['prior_sequence_pid'];rec=a['active_recorder_pid']
 assert str(B/'resume_remaining.py').encode() in cmdline(old)
 assert str(B/'record_controller.py').encode() in cmdline(rec) and PHASES[0].encode() in cmdline(rec)
 for phase in PHASES:
  p=B/phase
  assert not (p/'replay-admission.consumed').exists() and not (p/'progress.json').exists()
  assert not any((p/'cases').glob('*'))
 assert not (B/PHASES[1]/'recording-admission.consumed').exists()
 assert len(list((B/PHASES[0]/'recordings').glob('*/verification.json')))>0
 # Freeze only the old coordinator, never the recorder or its four GPU workers.
 os.kill(old,signal.SIGSTOP)
 try:
  state=s.read(B/'sequence-status.json')
  assert state['pid']==old and state['phase']==PHASES[0] and state['stage']=='record' and state['child_pid']==rec
  assert str(B/'record_controller.py').encode() in cmdline(rec)
  assert not s.stopping(PHASES[0])
  with (B/'streaming-admission.consumed').open('x') as f:f.write(str(os.getpid()))
  archive=B/'streaming-handoff';archive.mkdir(exist_ok=False)
  s.write(archive/'previous-sequence-status.json',state)
  s.write(archive/'transfer.json',{'time':time.time(),'old_sequence_pid':old,'recorder_pid':rec,'new_sequence_pid':os.getpid(),'recording_process_preserved':True})
  # The old coordinator has no transferable exit protocol; killing only this PID
  # avoids its SIGTERM handler, which would interrupt the independent recorder.
  os.kill(old,signal.SIGKILL);handoff=True;adopted=rec
 except BaseException:
  if process_alive(old):os.kill(old,signal.SIGCONT)
  raise
 lock=(B/'sequence.lock').open('a');deadline=time.time()+10
 while True:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
  except BlockingIOError:
   assert time.time()<deadline,'Prior sequence lock did not release';time.sleep(.2)
 for phase in PHASES:
  s.validate_admission()
  if phase==PHASES[0]:record=None;record_pid=rec
  else:
   record=launch(phase,'record',[s.PY,str(B/'record_controller.py'),phase]);record_pid=record.pid
  replay=launch(phase,'streaming-replay',[s.PY,str(B/'streaming_replay.py'),'run',phase])
  while True:
   if s.stopping(phase):raise RuntimeError('STOP active')
   recording_live=process_alive(record_pid) if record is None else record.poll() is None
   if not recording_live:
    if record is not None:assert record.returncode==0,('Recorder exit',record.returncode)
    assert s.read(B/phase/'recordings.finished.json')['verified']==126
   if replay.poll() is not None:
    assert replay.returncode==0,('Streaming replay exit',replay.returncode)
    assert not s.read(B/phase/'finished.json')['stopped']
   s.status(phase,'record+analysis+judge' if recording_live else 'analysis+judge',recorder_pid=record_pid,replay_pid=replay.pid)
   if not recording_live and replay.poll() is not None:break
   time.sleep(5)
  adopted=None
  s.run(phase,'finalize',[s.PY,str(B/'finalize_phase.py'),phase])
 s.write(B/'all-experiments.finished.json',{'time':time.time(),'phases':{p:s.read(B/p/'verified.finished.json') for p in s.PHASES}})
 s.status('all','completed')

if __name__=='__main__':
 try:main()
 except BaseException as e:
  if handoff:
   if not (B/'STOP.json').exists():s.write(B/'STOP.json',{'time':time.time(),'reason':'Streaming orchestration: '+repr(e)})
   abort();s.status('sequence','stopped',error=repr(e))
  raise
