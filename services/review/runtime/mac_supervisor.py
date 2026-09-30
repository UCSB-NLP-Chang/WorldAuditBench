#!/usr/bin/env python3
"""Multi-slot runtime owner (macOS and Linux). In-memory Popen handles prevent unchecked PID reuse."""
import hashlib,hmac,json,os,pathlib,re,secrets,signal,subprocess,sys,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

class Supervisor:
 def __init__(self,config):
  self.c=config;self.capacity=int(config.get('capacity',1));self.lock=threading.RLock();self.sessions={};self.stopping=False
  if not 1<=self.capacity<=3:raise ValueError('Runtime capacity must be 1..3')
  ports=[config[k]+slot for k in ('streamer_port','player_port','sfu_port') for slot in range(self.capacity)]
  if len(set(ports))!=len(ports) or any(not 1024<=p<=65535 for p in ports):raise ValueError('Runtime ports overlap or are invalid')
  self.allowed={t['map'] for t in json.loads(pathlib.Path(config['manifest']).read_text())['tasks'] if t.get('runtime_kind')!='browser'}
  self.profiles=config.get('launch_profiles',{})
  if self.profiles and set(self.profiles)!=self.allowed:raise ValueError('Launch profiles must exactly match manifest maps')
  if self.profiles:
   for task in json.loads(pathlib.Path(config['manifest']).read_text())['tasks']:
    if task.get('runtime_kind')=='browser':continue
    if task.get('build_sha256')!=self.profiles[task['map']].get('build_sha256'):raise ValueError('Task and runtime build hash mismatch')
  self.verified={}
  self.root=pathlib.Path(config['state_dir']);self.root.mkdir(parents=True,exist_ok=True)
 def validate(self,d):
  op,sid,map_,slot=(d.get(k) for k in ['operation','session_id','map','slot'])
  if op not in ('start','stop','status','switch') or not isinstance(sid,str) or not re.fullmatch('[0-9a-f]{32}',sid) or map_ not in self.allowed or type(slot)!=int or not 0<=slot<self.capacity:raise ValueError('Invalid runtime request')
  return op,sid,map_,slot
 def run(self,d):
  op,sid,map_,slot=self.validate(d)
  with self.lock:
   old=self.sessions.get(sid)
   if old and (old['slot']!=slot or (old['map']!=map_ and op not in ('switch','stop'))):raise ValueError('Session map mismatch')
   if op=='start':
    if self.stopping:raise RuntimeError('Supervisor shutting down')
    if old:return {'ready':False}
    if any(s['slot']==slot for s in self.sessions.values()):raise RuntimeError('GPU slot already allocated')
    directory=self.root/sid;directory.mkdir(exist_ok=True)
    s={'map':map_,'slot':slot,'directory':directory,'processes':[],'files':[],'ready':False,'switch_id':''}
    self.sessions[sid]=s
    try:
     config={'log_folder':str(directory/'signal-logs'),'log_level_console':'info','log_level_file':'info','streamer_port':self.c['streamer_port']+slot,'player_port':self.c['player_port']+slot,'sfu_port':self.c['sfu_port']+slot,'serve':True,'http_root':self.c['http_root'],'homepage':'player.html','https':False,'https_redirect':False,'rest_api':False,'log_config':False,'stdin':False,'console_messages':'basic','max_players':1,'peer_options':self.c.get('peer_options',{'iceServers':[]})}
     path=directory/'signal-config.json';path.write_text(json.dumps(config))
     argv=self.c['signal_argv']+['--config_file',str(path)]
     self.spawn(s,argv,'signalling.log',self.c['signal_cwd'])
     # Signal reconnection is handled by UE while the loopback listener starts.
     profile=self.profiles.get(map_,self.c)
     binary=profile['binary']
     if self.profiles:
      expected=profile['build_sha256'];stat=pathlib.Path(binary).stat();key=(binary,stat.st_size,stat.st_mtime_ns)
      if key not in self.verified:
       digest=hashlib.file_digest(open(binary,'rb'),'sha256').hexdigest() if hasattr(hashlib,'file_digest') else self.hash_binary(binary)
       self.verified[key]=digest
      if self.verified[key]!=expected:raise RuntimeError('Runtime binary does not match task build hash')
     argv=[binary,map_,'-AuditorSkipSceneMenu','-AuditorRemoteInput','-RenderOffscreen','-DefaultViewportMouseCaptureMode=NoCapture','-ini:Input:[/Script/Engine.InputSettings]:bCaptureMouseOnLaunch=False','-ini:Input:[/Script/Engine.InputSettings]:DefaultViewportMouseLockMode=DoNotLock','-ForceRes','-ResX=1280','-ResY=720','-Unattended','-AudioMixer','-PixelStreamingConnectionURL=ws://127.0.0.1:'+str(self.c['streamer_port']+slot),'-PixelStreamingID=DefaultStreamer','-PixelStreamingEncoderCodec=H264','-PixelStreamingWebRTCFps=30','-PixelStreamingAllowPixelStreamingCommands=false','-PixelStreamingKeyFilter='+profile.get('key_filter','M,One,Two,Three,Four,Tilde'),'-log','-abslog='+str(directory/'unreal.log')]
     if profile.get('runtime_switch'):argv+=['-AuditorReviewIPC='+str(directory/'review-ipc')]
     argv+=profile.get('game_args',self.c.get('game_args',[]))+profile.get('extra_args',[])
     self.spawn(s,argv,'unreal-stdout.log',str(pathlib.Path(binary).parent),self.c.get('game_env'))
     (directory/'launch.json').write_text(json.dumps({'session_id':sid,'map':map_,'argv':argv,'signal_argv':self.c['signal_argv']},indent=2))
    except Exception:self.stop(sid);raise
    return {'ready':False}
   if op=='switch':
    if not old:raise RuntimeError('Runtime no longer exists')
    source=self.profiles.get(old['map'],{});target=self.profiles.get(map_,{})
    if not source.get('runtime_switch') or not target.get('runtime_switch') or any(source.get(k)!=target.get(k) for k in ('binary','build_sha256','family')):raise ValueError('Cannot reuse this runtime for the target')
    if old['map']!=map_:
     request_id=secrets.token_hex(16);map_path,_,options=map_.partition('?');task=options.removeprefix('Task=') if options else 'baseline'
     ipc=old['directory']/'review-ipc';ipc.mkdir(exist_ok=True)
     command=ipc/'command.json';temp=ipc/'command.json.tmp'
     temp.write_text(json.dumps({'request_id':request_id,'action':'switch','map':map_path,'task':task}));temp.replace(command)
     old.update(map=map_,switch_id=request_id,ready=False)
     self.record(old,'task_switch_requested',map=map_,request_id=request_id,game_pid=old['processes'][1].pid)
   if op=='stop':
    if old:self.stop(sid)
    return {'stopped':sid not in self.sessions}
   if not old:return {'ready':False,'game_running':False,'signalling_running':False,'streamer_registered':False}
   exits=[p.poll() for p in old['processes']]
   if any(code is not None for code in exits):
    self.record(old,'process_exit',exit_codes=exits)
    return {'ready':False,'error':'Runtime process exited','exit_codes':exits,'game_running':exits[1] is None,'signalling_running':exits[0] is None,'streamer_registered':False}
   result=subprocess.run(self.c['probe_argv']+['ws://127.0.0.1:'+str(self.c['player_port']+slot),'DefaultStreamer'],capture_output=True,text=True,timeout=5)
   if result.returncode:
    self.record(old,'probe_failed',returncode=result.returncode,stdout=result.stdout,stderr=result.stderr)
    return {'ready':False,'error':'Streamer readiness probe failed','game_running':True,'signalling_running':True,'streamer_registered':False}
   data=json.loads(result.stdout);old['ready']=data.get('ready') is True
   if self.profiles.get(map_,{}).get('runtime_switch'):
    try:ack=json.loads((old['directory']/'review-ipc/response.json').read_text())
    except (OSError,ValueError):ack={}
    map_path,_,options=map_.partition('?');task=options.removeprefix('Task=') if options else 'baseline'
    scene_ready=ack.get('request_id')==old.get('switch_id','') and ack.get('status')=='ready' and ack.get('map')==map_path and ack.get('task')==task and ack.get('pid')==old['processes'][1].pid
    old['ready']=old['ready'] and scene_ready

   return {'ready':old['ready'],'stream_url':'/stream/'+sid+'/','game_running':True,'signalling_running':True,'streamer_registered':old['ready']}
 def hash_binary(self,binary):
  digest=hashlib.sha256()
  with open(binary,'rb') as f:
   for block in iter(lambda:f.read(8*1024*1024),b''):digest.update(block)
  return digest.hexdigest()
 def record(self,s,event,**details):
  with (s['directory']/'lifecycle.jsonl').open('a') as f:f.write(json.dumps({'time':time.time(),'event':event,**details})+'\n')
 def spawn(self,s,argv,name,cwd,env=None):
  file=(s['directory']/name).open('ab');s['files'].append(file)
  p=subprocess.Popen(argv,cwd=cwd,env=None if env is None else {**os.environ,**env},stdin=subprocess.DEVNULL,stdout=file,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True);s['processes'].append(p)
 def stop(self,sid):
  s=self.sessions[sid]
  self.record(s,'stop_requested',exit_codes=[p.poll() for p in s['processes']])
  for p in reversed(s['processes']):
   if p.poll() is None:
    os.killpg(p.pid,signal.SIGTERM)
    try:p.wait(timeout=3)
    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=3)
  if any(p.poll() is None for p in s['processes']):raise RuntimeError('Teardown not complete')
  for file in s['files']:file.close()
  del self.sessions[sid]
 def close(self):
  with self.lock:
   self.stopping=True
   for sid in list(self.sessions):self.stop(sid)

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  try:
   if self.path!='/runtime' or not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+self.server.config['secret']):raise PermissionError('Unauthorized')
   n=int(self.headers.get('Content-Length','0'))
   if not 0<n<4096:raise ValueError('Invalid size')
   result=self.server.supervisor.run(json.loads(self.rfile.read(n)));status=200
  except PermissionError:result={'error':'Unauthorized'};status=403
  except Exception as e:result={'error':str(e)};status=503
  body=json.dumps(result).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)

def main():
 c=json.loads(pathlib.Path(sys.argv[1]).read_text());supervisor=Supervisor(c);server=ThreadingHTTPServer(('127.0.0.1',c['supervisor_port']),Handler);server.supervisor=supervisor;server.config=c
 def terminate(*args):raise KeyboardInterrupt
 signal.signal(signal.SIGTERM,terminate)
 print('Local runtime supervisor ready',flush=True)
 try:server.serve_forever()
 except KeyboardInterrupt:pass
 finally:server.server_close();supervisor.close()
if __name__=='__main__':main()
