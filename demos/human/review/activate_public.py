from pathlib import Path
import datetime,json,os,shutil,sqlite3,subprocess
r=Path(__file__).resolve().parent;root=r.parents[1];state=root/'state';bundle=root/'public-deployment-20260911'
db=sqlite3.connect(state/'review.sqlite3')
if db.execute("SELECT count(*) FROM sessions WHERE status IN ('queued','starting','ready','resetting','closing')").fetchone()[0]:raise SystemExit('Active review; finish before switching entry.')
backup=root/'backups'/datetime.datetime.now(datetime.timezone.utc).strftime('pre-public-%Y%m%d-%H%M%S');backup.mkdir(mode=0o700)
for name in ('runtime.json','service-env.json','turn.conf','tasks.json'):
 shutil.copy2(state/name,backup/name);os.chmod(backup/name,0o600)
with sqlite3.connect(backup/'review.sqlite3') as out:db.backup(out)
db.close()
for unit in ('urban-review-pilot','subway-review'):(backup/(unit+'.service')).write_bytes(subprocess.check_output(['systemctl','cat',unit+'.service']))
subprocess.run(['sudo','systemctl','stop','urban-review-pilot.service','subway-review.service'],check=True)
for name in ('runtime.json','service-env.json','turn.conf','participants.json'):
 shutil.copy2(bundle/name,state/name);os.chmod(state/name,0o600)
subprocess.run(['sudo','tee','/etc/systemd/system/urban-review-pilot.service.d/50-unified.conf'],input=(bundle/'urban-review-pilot.override.conf').read_text(),text=True,stdout=subprocess.DEVNULL,check=True)
redirect=r/'runtime/legacy_redirect.py';redirect.write_text(redirect.read_text().replace('http://127.0.0.1:8092/','https://review.150-230-45-149.sslip.io/'))
subprocess.run(['sudo','tee','/etc/systemd/system/subway-review.service.d/50-unified.conf'],input='[Service]\nWorkingDirectory='+str(r)+'\nExecStart=\nExecStart=/usr/bin/python3 '+str(redirect)+'\n',text=True,stdout=subprocess.DEVNULL,check=True)
for name in ('caddy-data','caddy-config'):(root/name).mkdir(mode=0o700,exist_ok=True)
unit='''[Unit]
Description=Public HTTPS entry for A10 review
After=network-online.target urban-review-pilot.service
Wants=network-online.target
[Service]
User=ubuntu
Group=ubuntu
UMask=0077
Environment=XDG_DATA_HOME=/home/ubuntu/unreal-auditor/review-service/caddy-data
Environment=XDG_CONFIG_HOME=/home/ubuntu/unreal-auditor/review-service/caddy-config
ExecStart=/home/ubuntu/unreal-auditor/review-service/deps/caddy-2.11.4/caddy run --config /home/ubuntu/unreal-auditor/review-service/public-deployment-20260911/Caddyfile --adapter caddyfile
ExecReload=/home/ubuntu/unreal-auditor/review-service/deps/caddy-2.11.4/caddy reload --config /home/ubuntu/unreal-auditor/review-service/public-deployment-20260911/Caddyfile --adapter caddyfile
AmbientCapabilities=CAP_NET_BIND_SERVICE
NoNewPrivileges=true
Restart=on-failure
RestartSec=5
[Install]
WantedBy=multi-user.target
'''
subprocess.run(['sudo','tee','/etc/systemd/system/review-web.service'],input=unit,text=True,stdout=subprocess.DEVNULL,check=True)
subprocess.run(['sudo','systemctl','daemon-reload'],check=True);subprocess.run(['sudo','systemctl','start','urban-review-pilot.service','subway-review.service'],check=True);subprocess.run(['sudo','systemctl','enable','--now','review-web.service'],check=True)
(root/'current-release.txt').write_text(str(r)+'\n');print('Public candidate activated; certificate and video QA pending. Backup:',backup)
