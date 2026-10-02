"""Own shared supervisor and TURN in one systemd cgroup."""
import json,os,pathlib,signal,subprocess,sys,time,socket

def main():
 c=json.loads(pathlib.Path(sys.argv[1]).read_text());children=[]
 def stop(*args):raise KeyboardInterrupt
 signal.signal(signal.SIGTERM,stop)
 try:
  if c.get('own_turn') and c.get('turn_argv'):children.append(subprocess.Popen(c['turn_argv'],env={**os.environ,**c.get('turn_env',{})}))
  children.append(subprocess.Popen([sys.executable,'-m','bf.shared_supervisor',sys.argv[1]]))
  if c.get('scheduler_config'):
   deadline=time.monotonic()+15
   while True:
    if any(p.poll() is not None for p in children):raise RuntimeError('Shared supervisor startup failed')
    try:
     with socket.create_connection(('127.0.0.1',c['supervisor_port']),timeout=.5):break
    except OSError:
     if time.monotonic()>=deadline:raise RuntimeError('Shared supervisor unavailable')
     time.sleep(.2)
   children.append(subprocess.Popen([sys.executable,'-m','bf.scheduler_service',c['scheduler_config']]))
  while all(p.poll() is None for p in children):time.sleep(.5)
  raise RuntimeError('Shared runtime dependency exited')
 except KeyboardInterrupt:pass
 finally:
  for p in reversed(children):
   if p.poll() is None:
    p.terminate()
    try:p.wait(timeout=20)
    except subprocess.TimeoutExpired:p.kill();p.wait()
if __name__=='__main__':main()
