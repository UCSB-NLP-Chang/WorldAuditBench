#!/usr/bin/env python3
"""Provision private config for this single-case UE 5.6.1 SSH pilot. Never prints secrets."""
import hashlib,json,os,pathlib,secrets,sys
root=pathlib.Path(sys.argv[1]).resolve();release=pathlib.Path(sys.argv[2]).resolve();state=root/'state';state.mkdir(exist_ok=True);os.chmod(state,0o700)
if (state/'runtime.json').exists():raise SystemExit('Config already exists; refusing to rotate identities or overwrite state')
deps=root/'deps';infra=deps/'pixelstreaming-ue56';node=str(deps/'node-v22.23.2-linux-x64/bin/node')
build=pathlib.Path('/home/ubuntu/unreal-auditor/builds/core18-u018-ue561-20260910')
binary=build/'package/Linux/NYC_Building_Volume2/Binaries/Linux/NYC_Building_Volume2'
build_sha=hashlib.sha256(binary.read_bytes()).hexdigest()
assert build_sha=='33c64a8cdb3853407d29f5f313138c5f7edcee62520e04a189619c223a6f59e3'
task=next(t for t in json.loads((release/'tasks.json').read_text())['tasks'] if t['id']=='U018')
task.update(map='/Game/Auditor/Migration/UE561/U018/R02/TaskMap_Candidate01',sha256='c844f63e4c19a385b476f88f6b541fa9c4ac9ea4c27680d91ab70e830b8fbe65',case_id='U018-R02-UE561-C01',environment='urban-city / Junction / UE 5.6.1 compatibility candidate')
def private(path,value):
 path.write_text(value);os.chmod(path,0o600)
private(state/'tasks.json',json.dumps({'tasks':[task]},ensure_ascii=False,indent=2))
turn_password=secrets.token_urlsafe(32);token=secrets.token_urlsafe(32);qa=secrets.token_urlsafe(32)
turn_conf='\n'.join(['listening-ip=127.0.0.1','listening-port=23478','relay-ip=10.19.48.193','min-port=25000','max-port=25031','no-udp','no-tls','no-dtls','no-cli','no-tcp-relay','fingerprint','lt-cred-mech','realm=urban-review-ssh','user=review:'+turn_password,'user-quota=6','total-quota=12','no-multicast-peers','denied-peer-ip=0.0.0.0-255.255.255.255','allowed-peer-ip=10.19.48.193','log-file=stdout','simple-log','pidfile='+str(state/'turn.pid'),'relay-threads=2','userdb='+str(state/'turn.sqlite3'),''])
private(state/'turn.conf',turn_conf)
c={'manifest':str(state/'tasks.json'),'state_dir':str(state/'sessions'),'supervisor_port':18992,'secret':secrets.token_urlsafe(32),'streamer_port':18882,'player_port':18082,'sfu_port':18892,'http_root':str(infra/'SignallingWebServer/www'),'signal_argv':[node,str(infra/'SignallingWebServer/dist/index.js')],'signal_cwd':str(infra/'SignallingWebServer'),'binary':str(binary),'probe_argv':[node,str(infra/'local/probe-streamer.cjs')],'game_args':['-vulkan','-sm6','-PixelStreamingWebRTCMaxFps=30','-ExecCmds=t.MaxFPS 30'],'game_env':{'LD_LIBRARY_PATH':str(deps/'nvenc/usr/lib/x86_64-linux-gnu')},'peer_options':{'iceServers':[{'urls':['turn:127.0.0.1:23478?transport=tcp'],'username':'review','credential':turn_password}]},'turn_argv':[str(deps/'turn/usr/bin/turnserver'),'-c',str(state/'turn.conf')],'turn_env':{'LD_LIBRARY_PATH':str(deps/'turn/usr/lib/x86_64-linux-gnu')}}
private(state/'runtime.json',json.dumps(c,indent=2))
env={'REVIEW_MODE':'external','REVIEW_HOST':'127.0.0.1','REVIEW_PORT':'8092','REVIEW_MANIFEST':str(state/'tasks.json'),'REVIEW_DB':str(state/'review.sqlite3'),'REVIEW_CAPACITY':'1','REVIEW_TOKENS_JSON':json.dumps({token:{'id':'linux-pilot-reviewer','reviewer':'本机评审'},qa:{'id':'linux-technical-qa','reviewer':'Linux 技术验证'}}),'REVIEW_ADMIN_TOKEN':secrets.token_urlsafe(32),'REVIEW_RUNNER_JSON':json.dumps(['/usr/bin/python3',str(release/'runtime/mac_runner.py'),str(state/'runtime.json')]),'REVIEW_BUILD_SHA256':build_sha,'REVIEW_PUBLIC_ORIGIN':'http://127.0.0.1:8092','REVIEW_STREAM_PORTS':'[18082]','REVIEW_COOKIE_NAME':'linux_review_session','REVIEW_LOCAL_AUTOLOGIN_OWNER':'linux-pilot-reviewer','REVIEW_FORCE_TURN':'1'}
private(state/'service-env.json',json.dumps(env,ensure_ascii=False,indent=2));private(state/'qa-token',qa)
unit='\n'.join(['[Unit]','Description=Urban U018 SSH review pilot','After=network.target','','[Service]','Type=simple','User=ubuntu','Group=ubuntu','UMask=0077','WorkingDirectory='+str(release),'ExecStart=/usr/bin/python3 '+str(release/'runtime/start_linux.py')+' '+str(state),'Restart=on-failure','RestartSec=5','KillMode=control-group','TimeoutStopSec=75','StandardOutput=append:'+str(root/'logs/service.log'),'StandardError=append:'+str(root/'logs/service.log'),'','[Install]','WantedBy=multi-user.target',''])
(state/'urban-review-pilot.service').write_text(unit)
print(json.dumps({'prepared':True,'manifest':str(state/'tasks.json'),'build_sha256':build_sha,'case':task['case_id']}))
