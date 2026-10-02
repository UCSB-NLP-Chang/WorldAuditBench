from pathlib import Path
import datetime,json,os,shutil,sqlite3,subprocess,time,urllib.request
r=Path(__file__).resolve().parent;root=r.parents[1];state=root/'state';oldsub=Path('/home/ubuntu/unreal-auditor/subway-workspace/review/state')
for folder in (state,oldsub):
 db=sqlite3.connect('file:'+str(folder/'review.sqlite3')+'?mode=ro',uri=True)
 active=db.execute("select count(*) from sessions where status in ('queued','starting','ready','resetting','closing')").fetchone()[0];db.close()
 if active:raise SystemExit('Active review exists in '+str(folder)+'; finish it before deploying.')
bak=root/'backups'/datetime.datetime.now(datetime.timezone.utc).strftime('pre-unified-%Y%m%d-%H%M%S');bak.mkdir(parents=True,mode=0o700);os.chmod(bak.parent,0o700)
for label,folder in [('review',state),('subway',oldsub)]:
 dest=bak/label;dest.mkdir(mode=0o700)
 for name in ['tasks.json','runtime.json','service-env.json']:
  shutil.copy2(folder/name,dest/name);os.chmod(dest/name,0o600)
 src=sqlite3.connect(folder/'review.sqlite3');dst=sqlite3.connect(dest/'review.sqlite3');src.backup(dst);dst.close();print(label,'feedback preserved:',src.execute('select count(*) from feedback').fetchone()[0]);src.close()
for unit in ('urban-review-pilot','subway-review'):
 (bak/(unit+'.service')).write_bytes(subprocess.check_output(['systemctl','cat',unit+'.service']))
subprocess.run(['sudo','systemctl','stop','urban-review-pilot.service','subway-review.service'],check=True)
for name in ['runtime.json','service-env.json']:shutil.copy2(r/'prepared-state'/name,state/name)
shutil.copy2(r/'tasks.json',state/'tasks.json');os.chmod(state/'tasks.json',0o600)
for unit,entry in [('urban-review-pilot','start_linux.py '+str(state)),('subway-review','legacy_redirect.py')]:
 content='[Service]\nWorkingDirectory='+str(r)+'\nExecStart=\nExecStart=/usr/bin/python3 '+str(r/'runtime')+'/'+entry+'\n'
 dest='/etc/systemd/system/'+unit+'.service.d';subprocess.run(['sudo','mkdir','-p',dest],check=True);subprocess.run(['sudo','tee',dest+'/50-unified.conf'],input=content,text=True,stdout=subprocess.DEVNULL,check=True)
subprocess.run(['sudo','systemctl','daemon-reload'],check=True);subprocess.run(['sudo','systemctl','start','urban-review-pilot.service','subway-review.service'],check=True)
for i in range(20):
 try:
  with urllib.request.urlopen('http://127.0.0.1:8092/health',timeout=2) as response:assert response.status==200
  break
 except Exception:time.sleep(1)
else:raise SystemExit('Service health failed; preserved backup '+str(bak))
(root/'current-release.txt').write_text(str(r)+'\n');print('Unified review live on 8092; legacy 8093 redirects. Backup:',bak)
