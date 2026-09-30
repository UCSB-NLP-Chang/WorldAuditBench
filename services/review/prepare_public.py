#!/usr/bin/env python3
"""Prepare a private, reviewable public deployment bundle; does not activate services."""
import argparse,ipaddress,json,os,re,secrets
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--domain',required=True);p.add_argument('--public-ip',default='150.230.45.149');p.add_argument('--private-ip',default='10.19.48.193');p.add_argument('--roster',type=Path,help='JSON list of {id,name}; omitted allows input/selection of names');p.add_argument('--out',type=Path,required=True);a=p.parse_args()
if not re.fullmatch(r'(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}',a.domain):p.error('Provide a hostname without scheme, port or path')
for addr in (a.public_ip,a.private_ip):ipaddress.IPv4Address(addr)
r=Path(__file__).resolve().parent;root=r.parents[1];state=root/'state';dest=a.out.resolve();dest.mkdir(parents=True,mode=0o700,exist_ok=False);os.chmod(dest,0o700)
def save(name,data):
 path=dest/name;path.write_text(data if isinstance(data,str) else json.dumps(data,ensure_ascii=False,indent=2)+'\n');os.chmod(path,0o600)
roster=json.loads(a.roster.read_text()) if a.roster else []
if not isinstance(roster,list):p.error('Roster must be a JSON list')
from participants import normalized_name
names=[normalized_name(t['name']).casefold() for t in roster];ids=[t['id'] for t in roster]
if len(set(names))!=len(names) or len(set(ids))!=len(ids) or any(not isinstance(i,str) or not i for i in ids):p.error('Roster IDs and names must be unique')
code=secrets.token_urlsafe(18)
save('participants.json',dict(mode='group',access_code=code,reviewers=roster,allow_new_names=not bool(roster)));save('group-access-code.txt',code+'\n')
env=json.loads((state/'service-env.json').read_text());env['REVIEW_PUBLIC_ORIGIN']='https://'+a.domain;env['REVIEW_LOCAL_AUTOLOGIN_OWNER']='';env['REVIEW_PARTICIPANTS_FILE']=str(state/'participants.json');env['REVIEW_RUNNER_JSON']=json.dumps(['/usr/bin/python3',str(r/'runtime/mac_runner.py'),str(state/'runtime.json')]);save('service-env.json',env)
config=json.loads((state/'runtime.json').read_text())
username='review-'+secrets.token_hex(6);password=secrets.token_urlsafe(32)
config['peer_options']={'iceServers':[{'urls':['turn:'+a.domain+':3478?transport=tcp'],'username':username,'credential':password}]};save('runtime.json',config)
turn='\n'.join(['listening-ip='+a.private_ip,'listening-port=3478','relay-ip='+a.private_ip,'external-ip='+a.public_ip+'/'+a.private_ip,'min-port=25000','max-port=25031','no-udp','no-tls','no-dtls','no-cli','no-tcp-relay','fingerprint','lt-cred-mech','realm='+a.domain,'user='+username+':'+password,'user-quota=24','total-quota=32','no-multicast-peers','denied-peer-ip=0.0.0.0-255.255.255.255','allowed-peer-ip='+a.private_ip,'allowed-peer-ip='+a.public_ip,'log-file=stdout','simple-log','pidfile='+str(state/'turn.pid'),'relay-threads=2','userdb='+str(state/'turn.sqlite3')])+'\n';save('turn.conf',turn)
save('Caddyfile',a.domain+''' {
    encode zstd gzip
    request_body {
        max_size 8MB
    }
    @local_only path /api/admin/* /api/local-login /local-open/*
    respond @local_only 404
    reverse_proxy 127.0.0.1:8092
}
''')
save('urban-review-pilot.override.conf','[Service]\nWorkingDirectory='+str(r)+'\nExecStart=\nExecStart=/usr/bin/python3 '+str(r/'runtime/start_linux.py')+' '+str(state)+'\n')
save('deployment.json',{'domain':a.domain,'public_ip':a.public_ip,'release':str(r),'activate':False,'required_inbound':[{'protocol':'tcp','ports':[80,80],'purpose':'HTTPS certificate and HTTP redirect'},{'protocol':'tcp','ports':[443,443],'purpose':'HTTPS/WSS review'},{'protocol':'tcp','ports':[3478,3478],'purpose':'TURN video transport'},{'protocol':'udp','ports':[25000,25031],'purpose':'TURN relay connectivity'}],'dns':{'type':'A','name':a.domain,'value':a.public_ip,'proxy':False}})
print('Prepared private deployment bundle:',dest);print('No services, DNS or cloud firewall rules changed. Group access code is in group-access-code.txt.')
