#!/usr/bin/env python3
"""Own the SSH-only Linux pilot; systemd also cleans its entire cgroup."""
import json,os,pathlib,signal,subprocess,sys,time
root=pathlib.Path(__file__).resolve().parents[1]
state=pathlib.Path(sys.argv[1]);c=json.loads((state/'runtime.json').read_text())
env={**os.environ,**json.loads((state/'service-env.json').read_text())}
children=[]
def stop(*args):raise KeyboardInterrupt
signal.signal(signal.SIGTERM,stop)
try:
 if not env.get('REVIEW_SHARED_SCHEDULER'):
  children.append(subprocess.Popen(c['turn_argv'],env={**os.environ,**c['turn_env']}))
  children.append(subprocess.Popen([sys.executable,str(root/'runtime/mac_supervisor.py'),str(state/'runtime.json')]))
 time.sleep(1)
 if any(p.poll() is not None for p in children):raise RuntimeError('Runtime dependency failed')
 children.append(subprocess.Popen([sys.executable,str(root/'server.py')],env=env))
 print('Linux pilot ready: '+env['REVIEW_PUBLIC_ORIGIN'],flush=True)
 while all(p.poll() is None for p in children):time.sleep(1)
 raise RuntimeError('A service process exited')
except KeyboardInterrupt:pass
finally:
 for p in reversed(children):
  if p.poll() is None:
   p.terminate()
   try:p.wait(timeout=30)
   except subprocess.TimeoutExpired:p.kill();p.wait()
