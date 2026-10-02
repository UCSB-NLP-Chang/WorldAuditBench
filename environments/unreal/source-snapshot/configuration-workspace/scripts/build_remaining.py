from pathlib import Path
import json,subprocess,sys,hashlib,shutil,os
w=Path('/home/ubuntu/unreal-auditor/configuration-workspace');cfg=json.loads((w/'projects.json').read_text());engine=Path('/opt/UnrealEngine_5.6/Engine')
for f in sys.argv[1:]:
 s=cfg[f];p=Path(s['project']);root=Path(s['workspace']);output=root/'dist'/(f+'-configuration-20260913-'+os.getenv('CONFIGURATION_BUILD_REVISION','v1'));assert not output.exists()
 if f=='medieval':
  with (w/'out/author-medieval.log').open('w') as log:subprocess.run([str(engine/'Binaries/Linux/UnrealEditor-Cmd'),str(p),'-run=pythonscript','-script='+str(w/'scripts/author_windmill.py'),'-nullrhi','-nosound','-unattended'],stdout=log,stderr=subprocess.STDOUT,check=True)
 report=json.loads((w/'out'/('author-'+f+'.json')).read_text())
 if f=='urban':maps=[r['map'] for r in report['maps']]
 else:assert report['status']=='PASS';maps=report['maps']
 args=[str(engine/'Build/BatchFiles/RunUAT.sh'),'BuildCookRun','-project='+str(p),'-platform=Linux','-clientconfig=Development','-build','-cook','-stage','-pak','-package','-archive','-archivedirectory='+str(output),'-map='+'+'.join(maps),'-nop4','-utf8output','-unattended','-WaitForUATMutex','-UbtArgs=-WaitMutex -MaxParallelActions=8 -NoUBA']
 print('PACKAGE_START',f,flush=True)
 with (w/'out'/('package-'+f+'.log')).open('w') as log:subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,check=True)
 binary=output/'Linux'/p.stem/'Binaries/Linux'/p.stem;h=hashlib.sha256(binary.read_bytes()).hexdigest();result={'status':'PASS','binary':str(binary),'binary_sha256':h,'maps':maps};(w/'out'/('build-'+f+'.json')).write_text(json.dumps(result,indent=2))
 print('PACKAGE_PASS',f,h,flush=True)
