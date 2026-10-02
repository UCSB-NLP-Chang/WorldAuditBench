from pathlib import Path
import subprocess,json,hashlib
r=Path('/home/ubuntu/unreal-auditor');w=r/'subway-workspace/s20';e=Path('/opt/UnrealEngine_5.6/Engine');p=r/'projects/Subway/Subway.uproject'
def run(name,args):
 print(name,flush=True)
 with (w/'out'/(name+'.log')).open('w') as f:subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,check=True)
run('editor-build',[str(e/'Build/BatchFiles/Linux/Build.sh'),'SubwayEditor','Linux','Development',str(p),'-WaitMutex','-MaxParallelActions=8','-NoUBA'])
run('author',[str(e/'Binaries/Linux/UnrealEditor-Cmd'),str(p),'-run=pythonscript','-script='+str(w/'scripts/author.py'),'-nullrhi','-nosound','-unattended'])
assert json.loads((w/'out/author.json').read_text())['status']=='PASS'
out=r/'subway-workspace/dist/subway-s20-20260913-v1';assert not out.exists();regs=json.loads((r/'subway-workspace/environments/subway/regions.json').read_text())['regions']
run('package',[str(e/'Build/BatchFiles/RunUAT.sh'),'BuildCookRun','-project='+str(p),'-platform=Linux','-clientconfig=Development','-build','-cook','-stage','-pak','-package','-archive','-archivedirectory='+str(out),'-map='+'+'.join(x['map'] for x in regs),'-nop4','-utf8output','-unattended','-WaitForUATMutex','-UbtArgs=-WaitMutex -MaxParallelActions=8 -NoUBA'])
b=out/'Linux/Subway/Binaries/Linux/Subway';(w/'out/build.json').write_text(json.dumps(dict(status='PASS',binary=str(b),binary_sha256=hashlib.sha256(b.read_bytes()).hexdigest()),indent=2));print('BUILD_PASS',flush=True)
