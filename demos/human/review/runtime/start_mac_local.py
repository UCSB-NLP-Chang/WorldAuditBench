#!/usr/bin/env python3
"""Restart the configured local Mac live review service after stopping prior copies."""
import json,os,pathlib,signal,subprocess,sys,time
root=pathlib.Path(__file__).resolve().parents[1]
config=root/'var/mac-real/runtime.json';env_file=root/'var/mac-real/service-env.json'
if not config.exists() or not env_file.exists():raise SystemExit('Local Mac runtime has not been prepared. Read docs/MAC-LIVE.md.')
env=os.environ.copy();env.update(json.loads(env_file.read_text()))
children=[]
def stop(*args):raise KeyboardInterrupt
signal.signal(signal.SIGTERM,stop)
try:
 children.append(subprocess.Popen([sys.executable,str(root/'runtime/mac_supervisor.py'),str(config)],start_new_session=True))
 time.sleep(.5)
 if children[0].poll() is not None:raise RuntimeError('Supervisor failed to start; existing instance may own its port')
 children.append(subprocess.Popen([sys.executable,str(root/'server.py')],env=env,start_new_session=True))
 print('Live review: '+env['REVIEW_PUBLIC_ORIGIN']+'/?case=U018',flush=True)
 while all(p.poll() is None for p in children):time.sleep(1)
except KeyboardInterrupt:pass
finally:
 for p in reversed(children):
  if p.poll() is None:
   p.terminate()
   try:p.wait(timeout=25)
   except subprocess.TimeoutExpired:p.kill();p.wait()
