from pathlib import Path
import json,os,subprocess,sys,hashlib,shutil
w=Path('/home/ubuntu/unreal-auditor/configuration-workspace');cfg=json.loads((w/'projects.json').read_text());engine=Path('/opt/UnrealEngine_5.6/Engine')
for f in sys.argv[1:]:
 s=cfg[f];p=Path(s['project']);root=Path(s['workspace']);envname={'subway':'subway','indoor':'residential-house','ancient':'ancient-chinese-city'}[f];env=dict(os.environ,CONFIGURATION_FAMILY=f)
 log=w/'out'/('author-'+f+'.log');print('AUTHOR_START',f,flush=True)
 with log.open('w') as stream:subprocess.run([str(engine/'Binaries/Linux/UnrealEditor-Cmd'),str(p),'-run=pythonscript','-script='+str(w/'scripts/author_pose_catalogs.py'),'-nullrhi','-nosound','-unattended'],env=env,stdout=stream,stderr=subprocess.STDOUT,check=True)
 assert json.loads((w/'out'/('author-'+f+'.json')).read_text())['status']=='PASS'
 output=root/'dist'/(f+'-configuration-20260913-'+os.getenv('CONFIGURATION_BUILD_REVISION','v1'));assert not output.exists();regs=json.loads((root/'environments'/envname/'regions.json').read_text())['regions'];print('PACKAGE_START',f,flush=True)
 args=[str(engine/'Build/BatchFiles/RunUAT.sh'),'BuildCookRun','-project='+str(p),'-platform=Linux','-clientconfig=Development','-build','-cook','-stage','-pak','-package','-archive','-archivedirectory='+str(output),'-map='+'+'.join(r['map'] for r in regs),'-nop4','-utf8output','-unattended','-WaitForUATMutex','-UbtArgs=-WaitMutex -MaxParallelActions=8 -NoUBA']
 with (w/'out'/('package-'+f+'.log')).open('w') as log:subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,check=True)
 binary=output/'Linux'/p.stem/'Binaries/Linux'/p.stem;h=hashlib.sha256(binary.read_bytes()).hexdigest();result={'status':'PASS','binary':str(binary),'binary_sha256':h,'maps':[r['map'] for r in regs]};(w/'out'/('build-'+f+'.json')).write_text(json.dumps(result,indent=2))
 for n in ['tasks.json','regions.json']:shutil.copy2(root/'environments'/envname/n,output/n)
 print('PACKAGE_PASS',f,h,flush=True)
